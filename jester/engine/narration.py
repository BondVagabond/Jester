# ruff: noqa: I001
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from jester.ai.base import ModelError

from jester.corpus.models import CorpusDocument
from jester.domain import ActionResult, ActionType
from jester.processing.sanitizer import sanitize_content
from jester.prompts import load_prompt
from jester.retrieval import (
    BM25RetrievalService,
    HybridRetrievalService,
    QueryRetriever,
    RetrievalQuery,
    RetrievedDocument,
    WeightedRetriever,
)
from jester.validation import OutputValidationPolicy, ValidationIssue, ValidationRule, validate_output


class NarrationGenerationError(RuntimeError):
    """Raised when narration generation cannot complete safely."""


class NarrationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    state_snapshot: dict[str, object]
    action_result: ActionResult
    prompt_name: str = Field(default='narration', min_length=1)
    prompt_version: str = Field(default='v2', min_length=1)


class NarrationResponse(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    text: str = Field(min_length=1)
    prompt_name: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    used_fallback: bool = False
    validation_passed: bool = True
    issues: list[ValidationIssue] = Field(default_factory=list)
    retrieved_documents: list[RetrievedDocument] = Field(default_factory=list)
    state_summary: str = Field(min_length=1)
    action_summary: str = Field(min_length=1)


class ModelGenerationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    prompt_name: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    rendered_prompt: str = Field(min_length=1)
    state_summary: str = Field(min_length=1)
    action_summary: str = Field(min_length=1)
    retrieved_context: str = Field(min_length=1)
    fallback_text: str | None = None


class ModelClient(Protocol):
    def generate(self, request: ModelGenerationRequest) -> str:
        ...


class DeterministicNarrationModel:
    def generate(self, request: ModelGenerationRequest) -> str:
        context_line = request.retrieved_context.splitlines()[0].strip()
        narration = f'{request.action_summary} {context_line}'.strip()
        return sanitize_content(narration)


class StateSnapshotRetriever(QueryRetriever):
    def __init__(self, state_snapshot: Mapping[str, object]) -> None:
        documents = _build_snapshot_documents(state_snapshot)
        self._service = BM25RetrievalService(documents)

    def search(self, query: RetrievalQuery) -> list[RetrievedDocument]:
        return self._service.search(query)


def build_narration(
    request: NarrationRequest,
    *,
    retriever: QueryRetriever | None = None,
    model_client: ModelClient | None = None,
    policy: OutputValidationPolicy | None = None,
    rules: Sequence[ValidationRule] | None = None,
) -> NarrationResponse:
    state_summary = _summarize_state(request.state_snapshot)
    action_summary = _summarize_action(request.state_snapshot, request.action_result)
    state_retriever = StateSnapshotRetriever(request.state_snapshot)
    active_retriever: QueryRetriever
    if retriever is None:
        active_retriever = state_retriever
    else:
        active_retriever = HybridRetrievalService(
            [
                WeightedRetriever(name='state', retriever=state_retriever, weight=1.0),
                WeightedRetriever(name='external', retriever=retriever, weight=1.0),
            ]
        )

    retrieved_documents = active_retriever.search(RetrievalQuery(text=action_summary, k=3))
    retrieved_context = _format_retrieved_context(retrieved_documents, state_summary)
    prompt_spec = load_prompt(request.prompt_name, request.prompt_version)
    rendered_prompt = prompt_spec.template.format(
        state_summary=state_summary,
        action_summary=action_summary,
        retrieved_context=retrieved_context,
    )
    preliminary_request = ModelGenerationRequest(
        prompt_name=request.prompt_name,
        prompt_version=request.prompt_version,
        rendered_prompt=rendered_prompt,
        state_summary=state_summary,
        action_summary=action_summary,
        retrieved_context=retrieved_context,
    )
    fallback_text = DeterministicNarrationModel().generate(preliminary_request).strip()
    model_request = preliminary_request.model_copy(update={'fallback_text': fallback_text})
    if model_client is None:
        return _validated_fallback_response(
            model_request=model_request,
            fallback_text=fallback_text,
            state_summary=state_summary,
            action_summary=action_summary,
            retrieved_documents=retrieved_documents,
            policy=policy,
            rules=rules,
            issues=[],
        )

    try:
        raw_candidate = model_client.generate(model_request).strip()
    except ModelError:
        return _validated_fallback_response(
            model_request=model_request,
            fallback_text=fallback_text,
            state_summary=state_summary,
            action_summary=action_summary,
            retrieved_documents=retrieved_documents,
            policy=policy,
            rules=rules,
            issues=[],
        )
    raw_validation = validate_output(raw_candidate, policy, rules=rules)
    if not raw_validation.is_valid:
        return _validated_fallback_response(
            model_request=model_request,
            fallback_text=fallback_text,
            state_summary=state_summary,
            action_summary=action_summary,
            retrieved_documents=retrieved_documents,
            policy=policy,
            rules=rules,
            issues=raw_validation.issues,
        )

    candidate = sanitize_content(raw_candidate)
    candidate_validation = validate_output(candidate, policy, rules=rules)
    if candidate_validation.is_valid:
        return NarrationResponse(
            text=candidate,
            prompt_name=request.prompt_name,
            prompt_version=request.prompt_version,
            used_fallback=False,
            validation_passed=True,
            issues=candidate_validation.issues,
            retrieved_documents=retrieved_documents,
            state_summary=state_summary,
            action_summary=action_summary,
        )

    return _validated_fallback_response(
        model_request=model_request,
        fallback_text=fallback_text,
        state_summary=state_summary,
        action_summary=action_summary,
        retrieved_documents=retrieved_documents,
        policy=policy,
        rules=rules,
        issues=candidate_validation.issues,
    )


def generate_narration(
    state_snapshot: Mapping[str, object],
    action_result: ActionResult,
    *,
    retriever: QueryRetriever | None = None,
    model_client: ModelClient | None = None,
    policy: OutputValidationPolicy | None = None,
    rules: Sequence[ValidationRule] | None = None,
    prompt_name: str = 'narration',
    prompt_version: str = 'v2',
) -> str:
    response = build_narration(
        NarrationRequest(
            state_snapshot=dict(state_snapshot),
            action_result=action_result,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
        ),
        retriever=retriever,
        model_client=model_client,
        policy=policy,
        rules=rules,
    )
    return response.text


def _validated_fallback_response(
    *,
    model_request: ModelGenerationRequest,
    fallback_text: str,
    state_summary: str,
    action_summary: str,
    retrieved_documents: list[RetrievedDocument],
    policy: OutputValidationPolicy | None,
    rules: Sequence[ValidationRule] | None,
    issues: list[ValidationIssue],
) -> NarrationResponse:
    fallback = sanitize_content(fallback_text)
    validation = validate_output(fallback, policy, rules=rules)
    if not validation.is_valid:
        raise NarrationGenerationError(
            f'Narration fallback failed validation for {model_request.prompt_name}/{model_request.prompt_version}.'
        )
    return NarrationResponse(
        text=fallback,
        prompt_name=model_request.prompt_name,
        prompt_version=model_request.prompt_version,
        used_fallback=True,
        validation_passed=True,
        issues=issues,
        retrieved_documents=retrieved_documents,
        state_summary=state_summary,
        action_summary=action_summary,
    )


def _build_snapshot_documents(state_snapshot: Mapping[str, object]) -> list[CorpusDocument]:
    documents: list[CorpusDocument] = []

    campaign = _as_mapping(state_snapshot.get('campaign'))
    if campaign is not None:
        documents.append(
            CorpusDocument(
                doc_id='snapshot-campaign',
                chunk_id='snapshot-campaign:1',
                title=str(campaign.get('name', 'Campaign')),
                text=sanitize_content(str(campaign.get('description', '')) or 'Campaign state'),
                source='state:campaign',
                corpus='state',
                tags=['campaign'],
            )
        )

    for scene_id, scene_payload in _iter_mapping_items(state_snapshot.get('scenes')):
        documents.append(
            CorpusDocument(
                doc_id=f'scene-{scene_id}',
                chunk_id=f'scene-{scene_id}:1',
                title=str(scene_payload.get('name', scene_id)),
                text=sanitize_content(str(scene_payload.get('summary', 'Active scene'))),
                source=f'state:scene:{scene_id}',
                corpus='state',
                tags=['scene'],
            )
        )

    for location_id, location_payload in _iter_mapping_items(state_snapshot.get('locations')):
        documents.append(
            CorpusDocument(
                doc_id=f'location-{location_id}',
                chunk_id=f'location-{location_id}:1',
                title=str(location_payload.get('name', location_id)),
                text=sanitize_content(str(location_payload.get('description', 'Location state'))),
                source=f'state:location:{location_id}',
                corpus='state',
                tags=['location'],
            )
        )

    for character_id, character_payload in _iter_mapping_items(state_snapshot.get('player_characters')):
        text_parts = [
            f"{character_payload.get('character_class', 'Adventurer')} level {character_payload.get('level', 1)}"
        ]
        private_notes = character_payload.get('private_notes')
        if private_notes:
            text_parts.append(str(private_notes))
        documents.append(
            CorpusDocument(
                doc_id=f'pc-{character_id}',
                chunk_id=f'pc-{character_id}:1',
                title=str(character_payload.get('name', character_id)),
                text=sanitize_content('. '.join(text_parts)),
                source=f'state:pc:{character_id}',
                corpus='state',
                tags=['player_character'],
            )
        )

    for npc_id, npc_payload in _iter_mapping_items(state_snapshot.get('npcs')):
        text_parts = [str(npc_payload.get('faction', 'NPC'))]
        dm_notes = npc_payload.get('dm_notes')
        if dm_notes:
            text_parts.append(str(dm_notes))
        documents.append(
            CorpusDocument(
                doc_id=f'npc-{npc_id}',
                chunk_id=f'npc-{npc_id}:1',
                title=str(npc_payload.get('name', npc_id)),
                text=sanitize_content('. '.join(text_parts)),
                source=f'state:npc:{npc_id}',
                corpus='state',
                tags=['npc'],
            )
        )

    memory = _as_mapping(state_snapshot.get('memory'))
    if memory is not None:
        records = memory.get('records')
        if isinstance(records, list):
            for index, raw_record in enumerate(records, start=1):
                if not isinstance(raw_record, Mapping):
                    continue
                documents.append(
                    CorpusDocument(
                        doc_id=f'memory-{index}',
                        chunk_id=f'memory-{index}:1',
                        title=str(raw_record.get('scope', 'Memory')),
                        text=sanitize_content(str(raw_record.get('content', ''))),
                        source=f'state:memory:{index}',
                        corpus='state',
                        tags=['memory'],
                    )
                )

    if not documents:
        documents.append(
            CorpusDocument(
                doc_id='snapshot-fallback',
                chunk_id='snapshot-fallback:1',
                title='State snapshot',
                text='The scene state is available for narration.',
                source='state:fallback',
                corpus='state',
                tags=['state'],
            )
        )
    return documents


def _format_retrieved_context(
    documents: Sequence[RetrievedDocument],
    fallback: str,
) -> str:
    if not documents:
        return fallback
    return sanitize_content('\n'.join(f'{document.title}: {document.text}' for document in documents))


def _summarize_state(state_snapshot: Mapping[str, object]) -> str:
    current_scene_id = str(state_snapshot.get('current_scene_id', 'scene'))
    scenes = _as_mapping(state_snapshot.get('scenes')) or {}
    scene_payload = _as_mapping(scenes.get(current_scene_id)) or {}
    locations = _as_mapping(state_snapshot.get('locations')) or {}
    location_id = scene_payload.get('location_id')
    location_key = str(location_id) if location_id is not None else ''
    location_payload = _as_mapping(locations.get(location_key)) or {}
    summary = {
        'scene': scene_payload.get('name', current_scene_id),
        'scene_summary': scene_payload.get('summary', ''),
        'location': location_payload.get('name', ''),
        'location_description': location_payload.get('description', ''),
    }
    return sanitize_content(json.dumps(summary, ensure_ascii=False))


def _summarize_action(
    state_snapshot: Mapping[str, object],
    action_result: ActionResult,
) -> str:
    actor_name = _entity_name(state_snapshot, action_result.actor_id)
    if action_result.action_type == ActionType.ATTACK and action_result.attack_result is not None:
        target_name = _entity_name(state_snapshot, action_result.attack_result.target_id)
        hit_or_miss = 'hits' if action_result.attack_result.hit else 'misses'
        return sanitize_content(
            f'{actor_name} attacks {target_name} and {hit_or_miss}. '
            f'Attack roll {action_result.attack_result.attack_total} against armor class '
            f'{action_result.attack_result.target_armor_class}. '
            f'Damage applied {action_result.attack_result.damage_applied}.'
        )
    if action_result.action_type == ActionType.MOVE and action_result.movement_result is not None:
        movement = action_result.movement_result
        return sanitize_content(
            f'{actor_name} moves from slot {movement.previous_position.slot} '
            f'to slot {movement.current_position.slot}.'
        )
    if action_result.action_type == ActionType.END_TURN and action_result.state_delta.turn_change is not None:
        next_actor = _entity_name(
            state_snapshot,
            action_result.state_delta.turn_change.current_combatant_id,
        )
        return sanitize_content(f'{actor_name} ends the turn. {next_actor} is next to act.')
    return sanitize_content(f'{actor_name} takes an action.')


def _entity_name(state_snapshot: Mapping[str, object], entity_id: str) -> str:
    player_characters = _as_mapping(state_snapshot.get('player_characters')) or {}
    if entity_id in player_characters:
        payload = _as_mapping(player_characters[entity_id]) or {}
        return str(payload.get('name', entity_id))

    npcs = _as_mapping(state_snapshot.get('npcs')) or {}
    if entity_id in npcs:
        payload = _as_mapping(npcs[entity_id]) or {}
        return str(payload.get('name', entity_id))
    return entity_id


def _as_mapping(value: object) -> Mapping[str, object] | None:
    if isinstance(value, Mapping):
        return value
    return None


def _iter_mapping_items(value: object) -> list[tuple[str, Mapping[str, object]]]:
    mapping = _as_mapping(value)
    if mapping is None:
        return []
    items: list[tuple[str, Mapping[str, object]]] = []
    for key, item in mapping.items():
        item_mapping = _as_mapping(item)
        if item_mapping is None:
            continue
        items.append((str(key), item_mapping))
    return items





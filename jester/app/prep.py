# ruff: noqa: I001
from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence

from jester.ai import (
    CritiqueArtifact,
    ModelRegistry,
    ModelRole,
    ModelRoleUnavailableError,
    ModelSelectionPolicy,
    ModelTraceRecord,
    ReasoningService,
    RolePromptModelClient,
)
from jester.app.contracts import (
    EncounterOutline,
    NPCBrief,
    PrepArtifactType,
    PrepRequest,
    PrepResponse,
    ProvenanceReference,
    QuestHook,
    SessionPrepPacket,
    TownBrief,
)
from jester.app.orchestration import (
    PrepServiceResult,
    RetrievalContextService,
    ServiceWarning,
    ServiceWarningCode,
    WorkspaceDebugInfo,
    WorkspaceName,
    WorkspaceRoutingPolicy,
    WorkspaceTask,
)
from jester.app.prompting import PromptModelClient, generate_prompt_block
from jester.domain import Location, NPC, Scene, Session
from jester.processing.sanitizer import sanitize_content
from jester.retrieval import QueryRetriever, RetrievalQuery, RetrievedDocument
from jester.validation import OutputValidationPolicy

_MANNERISMS = (
    'Keeps answers short and watches every doorway.',
    'Speaks warmly, then pauses before revealing hard truths.',
    'Uses precise, practical language and notices small details.',
    'Laughs once, then drops back into careful seriousness.',
)
_TENSION_FALLBACKS = (
    'Local factions want the same objective for different reasons.',
    'Supplies are thin enough that one delay could change loyalties.',
    'Rumors are moving faster than reliable information.',
)
_REWARD_FALLBACKS = (
    'A tangible lead that points to the next scene.',
    'A useful piece of equipment tied to the current threat.',
    'Leverage with a local contact who can open the next door.',
)
_COMPLICATION_FALLBACKS = (
    'A rival group reaches the same clue first.',
    'The safest route is closed unless someone makes noise.',
    'The obvious ally is hiding one material fact.',
)


class PrepServiceError(RuntimeError):
    """Raised when prep orchestration cannot complete safely."""


class PrepService:
    def __init__(
        self,
        *,
        retriever: QueryRetriever | None = None,
        model_client: PromptModelClient | None = None,
        policy: OutputValidationPolicy | None = None,
        model_registry: ModelRegistry | None = None,
        selection_policy: ModelSelectionPolicy | None = None,
        reasoning_service: ReasoningService | None = None,
    ) -> None:
        self._retriever = retriever
        self._model_client = model_client
        self._policy = policy
        self._selector = selection_policy or (ModelSelectionPolicy(model_registry) if model_registry else None)
        self._reasoning_service = reasoning_service or ReasoningService(self._selector)
        self._retrieval_context = RetrievalContextService(retriever)

    def create_artifact(
        self,
        request: PrepRequest,
        *,
        session: Session | None = None,
    ) -> PrepResponse:
        traces: list[ModelTraceRecord] = []
        if self._selector is not None:
            try:
                self._selector.require(ModelRole.PRIMARY_GENERATION)
            except ModelRoleUnavailableError as exc:
                raise PrepServiceError(str(exc)) from exc

        retrieved = self._retrieve_documents(request)
        provenance = [_to_provenance_reference(document) for document in retrieved]
        inputs_used = self._build_inputs_used(request, session)
        plan = self._reasoning_service.build_prep_plan(
            artifact_type=request.artifact_type.value,
            topic=request.topic,
            goal=request.goal,
            inputs_used=inputs_used,
            retrieved_context=_retrieved_context_text(retrieved),
            trace_sink=traces,
        )
        prompt_client = self._build_prompt_client(traces)

        artifact: NPCBrief | TownBrief | EncounterOutline | QuestHook | SessionPrepPacket
        if request.artifact_type == PrepArtifactType.NPC_BRIEF:
            artifact = self._build_npc_brief(
                request,
                session,
                inputs_used,
                provenance,
                retrieved,
                prompt_client,
            )
        elif request.artifact_type == PrepArtifactType.TOWN_BRIEF:
            artifact = self._build_town_brief(
                request,
                session,
                inputs_used,
                provenance,
                retrieved,
                prompt_client,
            )
        elif request.artifact_type == PrepArtifactType.ENCOUNTER_OUTLINE:
            artifact = self._build_encounter_outline(
                request,
                session,
                inputs_used,
                provenance,
                retrieved,
                prompt_client,
            )
        elif request.artifact_type == PrepArtifactType.QUEST_HOOK:
            artifact = self._build_quest_hook(
                request,
                inputs_used,
                provenance,
                retrieved,
                prompt_client,
            )
        else:
            artifact = self._build_session_prep_packet(
                request,
                session,
                inputs_used,
                provenance,
                retrieved,
                prompt_client,
            )

        if artifact.prose is not None:
            _append_generation_trace(
                traces,
                prompt_name=artifact.prose.prompt_name,
                prompt_version=artifact.prose.prompt_version,
                used_fallback=artifact.prose.used_fallback,
                validation_passed=artifact.prose.validation_passed,
                provider_name=self._primary_provider_name(),
                model_name=self._primary_model_name(),
                outcome='prep_generation_validated',
            )

        critique = self._reasoning_service.critique_prep_output(
            artifact_type=request.artifact_type.value,
            topic=request.topic,
            goal=request.goal,
            draft_text=_critique_source_text(artifact),
            trace_sink=traces,
        )
        artifact = self._maybe_refine_artifact(
            request,
            artifact,
            critique=critique,
            retrieved=retrieved,
            prompt_client=prompt_client,
            trace_sink=traces,
        )
        return self._build_response(
            request.artifact_type,
            artifact,
            plan=plan,
            critique=critique,
            model_traces=traces,
        )

    def execute(
        self,
        request: PrepRequest,
        *,
        session: Session | None = None,
    ) -> PrepServiceResult:
        retrieval_route = WorkspaceRoutingPolicy.prep_retrieval()
        retrieved_context = self._retrieval_context.fetch(
            retrieval_route,
            query_text=self._prep_query_text(request),
            request_id=request.request_id,
            session_id=request.session_id,
        )
        response = self.create_artifact(request, session=session)
        warnings = _dedupe_warnings(
            [*retrieved_context.warnings, *_warnings_from_model_traces(response.model_traces)]
        )
        routes = [
            retrieval_route,
            WorkspaceRoutingPolicy.prep_plan(),
            WorkspaceRoutingPolicy.prep_prose(request.artifact_type),
            WorkspaceRoutingPolicy.prep_critique(),
        ]
        if response.critique is not None and response.critique.violations:
            routes.append(WorkspaceRoutingPolicy.prep_refine())
        return PrepServiceResult(
            response=response,
            warnings=warnings,
            debug=WorkspaceDebugInfo(
                workspace=WorkspaceName.PREP,
                primary_task=WorkspaceTask.PREP_PROSE,
                routes=routes,
                retrieved=[retrieved_context],
                warnings=warnings,
                notes=[
                    'Prep orchestration runs plan, generation, critique, and optional refinement on the backend.',
                ],
            ),
        )
    def _build_response(
        self,
        artifact_type: PrepArtifactType,
        artifact: NPCBrief | TownBrief | EncounterOutline | QuestHook | SessionPrepPacket,
        *,
        plan: object,
        critique: CritiqueArtifact,
        model_traces: list[ModelTraceRecord],
    ) -> PrepResponse:
        payloads: dict[str, object] = {
            'artifact_type': artifact_type,
            'plan': plan,
            'critique': critique,
            'model_traces': model_traces,
        }
        if isinstance(artifact, NPCBrief):
            payloads['npc_brief'] = artifact
        elif isinstance(artifact, TownBrief):
            payloads['town_brief'] = artifact
        elif isinstance(artifact, EncounterOutline):
            payloads['encounter_outline'] = artifact
        elif isinstance(artifact, QuestHook):
            payloads['quest_hook'] = artifact
        else:
            payloads['session_prep_packet'] = artifact
        return PrepResponse.model_validate(payloads)

    def _build_prompt_client(
        self,
        trace_sink: list[ModelTraceRecord],
    ) -> PromptModelClient | None:
        if self._selector is not None:
            selected = self._selector.require(ModelRole.PRIMARY_GENERATION)
            return RolePromptModelClient(selected, trace_sink=trace_sink)
        return self._model_client

    def _primary_provider_name(self) -> str | None:
        if self._selector is not None:
            return self._selector.resolve(ModelRole.PRIMARY_GENERATION).provider_name
        if self._model_client is not None:
            return 'legacy'
        return None

    def _primary_model_name(self) -> str | None:
        if self._selector is not None:
            return self._selector.resolve(ModelRole.PRIMARY_GENERATION).model_name
        if self._model_client is not None:
            return type(self._model_client).__name__
        return None

    def _retrieve_documents(self, request: PrepRequest) -> list[RetrievedDocument]:
        if self._retriever is None:
            return []
        route = WorkspaceRoutingPolicy.prep_retrieval()
        return self._retriever.search(
            RetrievalQuery(
                text=self._prep_query_text(request),
                corpus=route.corpus_id,
                k=route.retrieval_top_k,
                request_id=request.request_id,
                session_id=request.session_id,
            )
        )

    def _prep_query_text(self, request: PrepRequest) -> str:
        return request.retrieval_query or request.request_text or request.topic or request.goal

    def _build_inputs_used(self, request: PrepRequest, session: Session | None) -> list[str]:
        inputs = [f'topic:{request.topic}', f'goal:{request.goal}']
        if request.request_text:
            inputs.append(f'request:{request.request_text}')
        if request.campaign_id:
            inputs.append(f'campaign:{request.campaign_id}')
        if request.session_id:
            inputs.append(f'session:{request.session_id}')
        if session is not None:
            scene = session.scenes[session.current_scene_id]
            location = session.locations[scene.location_id]
            inputs.append(f'scene:{scene.name}')
            inputs.append(f'location:{location.name}')
        inputs.extend(f'note:{note}' for note in request.context_notes)
        return inputs

    def _build_npc_brief(
        self,
        request: PrepRequest,
        session: Session | None,
        inputs_used: list[str],
        provenance: list[ProvenanceReference],
        retrieved: Sequence[RetrievedDocument],
        prompt_client: PromptModelClient | None,
    ) -> NPCBrief:
        matching_npc = _find_matching_npc(session, request.topic)
        sentence_pool = _document_sentences(retrieved)
        secret_source = matching_npc.dm_notes if matching_npc is not None else _nth_or_default(sentence_pool, 1, '')
        role = (
            matching_npc.faction
            if matching_npc is not None and matching_npc.faction
            else _headline_or_default(retrieved, 'Local contact')
        )
        motivation = _first_or_default(
            sentence_pool,
            f'{request.topic} wants progress on {request.goal.lower()}.',
        )
        secret = _first_sentence(secret_source, 'They know one fact the party does not yet have.')
        mannerism = _stable_choice(request.topic, _MANNERISMS)
        encounter_hooks = _list_or_default(
            [_headline_or_default(retrieved, ''), f'Tie {request.topic} directly to the current objective.'],
            'Use the NPC to complicate the scene without changing the core goal.',
        )

        prose = None
        if request.include_flavor_prose:
            fallback_text = f'{request.topic} is positioned as {role.lower()}. {motivation} {secret}'
            prose = generate_prompt_block(
                prompt_name='prep_npc',
                prompt_version='v1',
                template_values={
                    'topic': request.topic,
                    'goal': request.goal,
                    'structured_summary': (
                        f'Role: {role}. Motivation: {motivation}. Secret: {secret}. '
                        f'Mannerism: {mannerism}.'
                    ),
                    'retrieved_context': _retrieved_context_text(retrieved),
                },
                fallback_text=fallback_text,
                model_client=prompt_client,
                policy=self._policy,
            )

        return NPCBrief(
            artifact_id=f'{request.request_id}-npc',
            purpose=request.goal,
            inputs_used=inputs_used,
            provenance=provenance,
            prose=prose,
            name=matching_npc.name if matching_npc is not None else request.topic.title(),
            role=role,
            motivation=motivation,
            secret=secret,
            mannerism=mannerism,
            encounter_hooks=encounter_hooks,
        )

    def _build_town_brief(
        self,
        request: PrepRequest,
        session: Session | None,
        inputs_used: list[str],
        provenance: list[ProvenanceReference],
        retrieved: Sequence[RetrievedDocument],
        prompt_client: PromptModelClient | None,
    ) -> TownBrief:
        location = _find_matching_location(session, request.topic)
        sentence_pool = _document_sentences(retrieved)
        atmosphere = _first_sentence(
            location.description if location is not None else _first_or_default(sentence_pool, ''),
            f'{request.topic.title()} feels tense, active, and ready to matter immediately.',
        )
        tensions = _list_or_default(
            [
                _nth_or_default(sentence_pool, 0, ''),
                _nth_or_default(sentence_pool, 1, ''),
                _stable_choice(request.topic + request.goal, _TENSION_FALLBACKS),
            ],
            _stable_choice(request.topic, _TENSION_FALLBACKS),
        )
        landmarks = _list_or_default(
            [document.title for document in retrieved],
            location.name if location is not None else f'{request.topic.title()} Square',
        )
        notable_npcs = _list_or_default(
            [npc.name for npc in session.npcs.values()] if session is not None else [],
            'A practical local contact',
        )

        prose = None
        if request.include_flavor_prose:
            structured_summary = (
                f"Atmosphere: {atmosphere}. Tensions: {' | '.join(tensions)}. "
                f"Landmarks: {' | '.join(landmarks)}."
            )
            prose = generate_prompt_block(
                prompt_name='prep_town',
                prompt_version='v1',
                template_values={
                    'topic': request.topic,
                    'goal': request.goal,
                    'structured_summary': structured_summary,
                    'retrieved_context': _retrieved_context_text(retrieved),
                },
                fallback_text=f'{request.topic.title()} feels immediate and playable. {atmosphere}',
                model_client=prompt_client,
                policy=self._policy,
            )

        return TownBrief(
            artifact_id=f'{request.request_id}-town',
            purpose=request.goal,
            inputs_used=inputs_used,
            provenance=provenance,
            prose=prose,
            name=location.name if location is not None else request.topic.title(),
            atmosphere=atmosphere,
            tensions=tensions,
            landmarks=landmarks,
            notable_npcs=notable_npcs,
        )

    def _build_encounter_outline(
        self,
        request: PrepRequest,
        session: Session | None,
        inputs_used: list[str],
        provenance: list[ProvenanceReference],
        retrieved: Sequence[RetrievedDocument],
        prompt_client: PromptModelClient | None,
    ) -> EncounterOutline:
        scene = _current_scene(session)
        location = _current_location(session)
        enemies = _list_or_default(
            [npc.name for npc in session.npcs.values()] if session is not None else [],
            _headline_or_default(retrieved, 'Hostile scout'),
        )
        terrain_features = _list_or_default(
            _terrain_features(
                location.description if location is not None else _first_or_default(_document_sentences(retrieved), '')
            ),
            'Tight lanes that force clear movement choices.',
        )
        escalation = _nth_or_default(
            _document_sentences(retrieved),
            1,
            _stable_choice(request.goal, _COMPLICATION_FALLBACKS),
        )
        rewards = _list_or_default(
            [scene.summary] if scene is not None else [],
            _stable_choice(request.topic, _REWARD_FALLBACKS),
        )

        prose = None
        if request.include_flavor_prose:
            structured_summary = (
                f"Objective: {request.goal}. Enemies: {' | '.join(enemies)}. "
                f"Terrain: {' | '.join(terrain_features)}. Escalation: {escalation}."
            )
            prose = generate_prompt_block(
                prompt_name='prep_encounter',
                prompt_version='v1',
                template_values={
                    'topic': request.topic,
                    'goal': request.goal,
                    'structured_summary': structured_summary,
                    'retrieved_context': _retrieved_context_text(retrieved),
                },
                fallback_text=f'{request.topic.title()} should press on {request.goal.lower()}. {escalation}',
                model_client=prompt_client,
                policy=self._policy,
            )

        return EncounterOutline(
            artifact_id=f'{request.request_id}-encounter',
            purpose=request.goal,
            inputs_used=inputs_used,
            provenance=provenance,
            prose=prose,
            name=f'{request.topic.title()} Encounter',
            objective=request.goal,
            enemies=enemies,
            terrain_features=terrain_features,
            escalation=escalation,
            rewards=rewards,
        )

    def _build_quest_hook(
        self,
        request: PrepRequest,
        inputs_used: list[str],
        provenance: list[ProvenanceReference],
        retrieved: Sequence[RetrievedDocument],
        prompt_client: PromptModelClient | None,
    ) -> QuestHook:
        sentence_pool = _document_sentences(retrieved)
        premise = _first_or_default(
            sentence_pool,
            f'{request.topic.title()} becomes urgent because it directly blocks {request.goal.lower()}.',
        )
        stakes = _nth_or_default(
            sentence_pool,
            1,
            'If the party waits, the next scene becomes materially harder.',
        )
        complication = _stable_choice(request.topic + request.goal, _COMPLICATION_FALLBACKS)

        prose = None
        if request.include_flavor_prose:
            prose = generate_prompt_block(
                prompt_name='prep_quest_hook',
                prompt_version='v1',
                template_values={
                    'topic': request.topic,
                    'goal': request.goal,
                    'structured_summary': (
                        f'Premise: {premise}. Objective: {request.goal}. '
                        f'Stakes: {stakes}. Complication: {complication}.'
                    ),
                    'retrieved_context': _retrieved_context_text(retrieved),
                },
                fallback_text=f'{premise} The immediate complication is that {complication.lower()}',
                model_client=prompt_client,
                policy=self._policy,
            )

        return QuestHook(
            artifact_id=f'{request.request_id}-hook',
            purpose=request.goal,
            inputs_used=inputs_used,
            provenance=provenance,
            prose=prose,
            title=f'{request.topic.title()} Hook',
            premise=premise,
            objective=request.goal,
            stakes=stakes,
            complication=complication,
        )

    def _build_session_prep_packet(
        self,
        request: PrepRequest,
        session: Session | None,
        inputs_used: list[str],
        provenance: list[ProvenanceReference],
        retrieved: Sequence[RetrievedDocument],
        prompt_client: PromptModelClient | None,
    ) -> SessionPrepPacket:
        npc_request = request.model_copy(
            update={
                'artifact_type': PrepArtifactType.NPC_BRIEF,
                'include_flavor_prose': False,
            }
        )
        town_request = request.model_copy(
            update={
                'artifact_type': PrepArtifactType.TOWN_BRIEF,
                'include_flavor_prose': False,
            }
        )
        encounter_request = request.model_copy(
            update={
                'artifact_type': PrepArtifactType.ENCOUNTER_OUTLINE,
                'include_flavor_prose': False,
            }
        )
        hook_request = request.model_copy(
            update={
                'artifact_type': PrepArtifactType.QUEST_HOOK,
                'include_flavor_prose': False,
            }
        )

        npc_brief = self._build_npc_brief(npc_request, session, inputs_used, provenance, retrieved, prompt_client)
        town_brief = self._build_town_brief(town_request, session, inputs_used, provenance, retrieved, prompt_client)
        encounter_outline = self._build_encounter_outline(
            encounter_request,
            session,
            inputs_used,
            provenance,
            retrieved,
            prompt_client,
        )
        quest_hook = self._build_quest_hook(hook_request, inputs_used, provenance, retrieved, prompt_client)
        scene = _current_scene(session)
        outline_steps = [
            f'Open with {town_brief.name} under visible pressure.',
            f'Use {npc_brief.name} to surface a concrete choice.',
            f'Resolve the core beat through {encounter_outline.name}.',
            f'End by pointing at {quest_hook.title}.',
        ]
        fallback_text = ' '.join(outline_steps)
        prose = None
        if request.include_flavor_prose:
            prose = generate_prompt_block(
                prompt_name='prep_session_packet',
                prompt_version='v1',
                template_values={
                    'topic': request.topic,
                    'goal': request.goal,
                    'structured_summary': (
                        f'Opening: {outline_steps[0]} Middle: {outline_steps[1]} '
                        f'Climax: {outline_steps[2]} Close: {outline_steps[3]}'
                    ),
                    'retrieved_context': _retrieved_context_text(retrieved),
                },
                fallback_text=fallback_text,
                model_client=prompt_client,
                policy=self._policy,
            )

        title = scene.name if scene is not None else f'{request.topic.title()} Session'
        return SessionPrepPacket(
            artifact_id=f'{request.request_id}-packet',
            purpose=request.goal,
            inputs_used=inputs_used,
            provenance=provenance,
            prose=prose,
            title=f'{title} Prep Packet',
            outline_steps=outline_steps,
            npc_briefs=[npc_brief],
            town_brief=town_brief,
            encounter_outline=encounter_outline,
            quest_hooks=[quest_hook],
        )

    def _maybe_refine_artifact(
        self,
        request: PrepRequest,
        artifact: NPCBrief | TownBrief | EncounterOutline | QuestHook | SessionPrepPacket,
        *,
        critique: CritiqueArtifact,
        retrieved: Sequence[RetrievedDocument],
        prompt_client: PromptModelClient | None,
        trace_sink: list[ModelTraceRecord],
    ) -> NPCBrief | TownBrief | EncounterOutline | QuestHook | SessionPrepPacket:
        if not critique.violations:
            return artifact
        fallback_text = _artifact_fallback_text(artifact)
        refined = generate_prompt_block(
            prompt_name='prep_refine',
            prompt_version='v1',
            template_values={
                'artifact_type': request.artifact_type.value,
                'topic': request.topic,
                'goal': request.goal,
                'draft_output': artifact.prose.text if artifact.prose is not None else fallback_text,
                'revision_instructions': ' | '.join(critique.revision_instructions),
                'retrieved_context': _retrieved_context_text(retrieved),
            },
            fallback_text=fallback_text,
            model_client=prompt_client,
            policy=self._policy,
        )
        _append_generation_trace(
            trace_sink,
            prompt_name=refined.prompt_name,
            prompt_version=refined.prompt_version,
            used_fallback=refined.used_fallback,
            validation_passed=refined.validation_passed,
            provider_name=self._primary_provider_name(),
            model_name=self._primary_model_name(),
            outcome='prep_refinement_validated',
        )
        return artifact.model_copy(update={'prose': refined})


def _append_generation_trace(
    trace_sink: list[ModelTraceRecord],
    *,
    prompt_name: str,
    prompt_version: str,
    used_fallback: bool,
    validation_passed: bool,
    provider_name: str | None,
    model_name: str | None,
    outcome: str,
) -> None:
    trace_sink.append(
        ModelTraceRecord(
            role=ModelRole.PRIMARY_GENERATION,
            provider_name=provider_name,
            model_name=model_name,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            validation_passed=validation_passed,
            fallback_triggered=used_fallback,
            degraded=False,
            outcome=outcome,
        )
    )



def _critique_source_text(
    artifact: NPCBrief | TownBrief | EncounterOutline | QuestHook | SessionPrepPacket,
) -> str:
    if artifact.prose is not None:
        return artifact.prose.text
    return _artifact_draft_text(artifact)
def _artifact_draft_text(
    artifact: NPCBrief | TownBrief | EncounterOutline | QuestHook | SessionPrepPacket,
) -> str:
    payload = artifact.model_dump(mode='json', exclude={'schema_version', 'artifact_id', 'provenance', 'inputs_used'})
    parts: list[str] = []
    for value in payload.values():
        if value is None:
            continue
        if isinstance(value, str):
            parts.append(value)
            continue
        if isinstance(value, list):
            parts.extend(str(item) for item in value if str(item).strip())
    return sanitize_content(' '.join(parts))


def _artifact_fallback_text(
    artifact: NPCBrief | TownBrief | EncounterOutline | QuestHook | SessionPrepPacket,
) -> str:
    if isinstance(artifact, NPCBrief):
        return f'{artifact.name} serves as {artifact.role.lower()}. {artifact.motivation} {artifact.secret}'
    if isinstance(artifact, TownBrief):
        return f'{artifact.name} feels playable immediately. {artifact.atmosphere}'
    if isinstance(artifact, EncounterOutline):
        return f'{artifact.name} centers on {artifact.objective}. {artifact.escalation}'
    if isinstance(artifact, QuestHook):
        return f'{artifact.premise} The immediate stakes are {artifact.stakes.lower()}'
    return ' '.join(artifact.outline_steps)


def _to_provenance_reference(document: RetrievedDocument) -> ProvenanceReference:
    return ProvenanceReference(
        doc_id=document.doc_id,
        chunk_id=document.chunk_id,
        source=document.source,
        title=document.title,
        score=document.score,
        excerpt=document.text,
    )


def _normalize_name(value: str) -> str:
    return re.sub(r'[^a-z0-9]+', ' ', value.lower()).strip()


def _find_matching_npc(session: Session | None, topic: str) -> NPC | None:
    if session is None:
        return None
    target = _normalize_name(topic)
    for npc in session.npcs.values():
        if _normalize_name(npc.name) == target:
            return npc
    return None


def _find_matching_location(session: Session | None, topic: str) -> Location | None:
    if session is None:
        return None
    target = _normalize_name(topic)
    for location in session.locations.values():
        if _normalize_name(location.name) == target:
            return location
    return None


def _current_scene(session: Session | None) -> Scene | None:
    if session is None:
        return None
    return session.scenes[session.current_scene_id]


def _current_location(session: Session | None) -> Location | None:
    if session is None:
        return None
    scene = session.scenes[session.current_scene_id]
    return session.locations[scene.location_id]


def _document_sentences(documents: Sequence[RetrievedDocument]) -> list[str]:
    sentences: list[str] = []
    for document in documents:
        for sentence in re.split(r'(?<=[.!?])\s+', document.text):
            cleaned = sentence.strip()
            if cleaned:
                sentences.append(cleaned)
    return sentences


def _first_or_default(values: Sequence[str], default: str) -> str:
    for value in values:
        if value.strip():
            return value.strip()
    return default


def _nth_or_default(values: Sequence[str], index: int, default: str) -> str:
    if 0 <= index < len(values):
        value = values[index].strip()
        if value:
            return value
    return default


def _headline_or_default(documents: Sequence[RetrievedDocument], default: str) -> str:
    for document in documents:
        if document.title.strip():
            return document.title.strip()
    return default


def _first_sentence(value: str | None, default: str) -> str:
    if not value:
        return default
    parts = re.split(r'(?<=[.!?])\s+', value.strip())
    for part in parts:
        if part.strip():
            return part.strip()
    return default


def _terrain_features(description: str) -> list[str]:
    if not description.strip():
        return []
    raw_features = re.split(r',| and ', description)
    return [feature.strip().rstrip('.') for feature in raw_features if feature.strip()][:3]


def _list_or_default(values: Sequence[str], default: str) -> list[str]:
    cleaned = [value.strip() for value in values if value.strip()]
    if cleaned:
        seen: set[str] = set()
        unique: list[str] = []
        for value in cleaned:
            if value in seen:
                continue
            seen.add(value)
            unique.append(value)
        return unique[:4]
    return [default]


def _stable_choice(key: str, options: Sequence[str]) -> str:
    digest = hashlib.sha256(key.encode('utf-8')).digest()
    index = digest[0] % len(options)
    return options[index]


def _retrieved_context_text(documents: Sequence[RetrievedDocument]) -> str:
    if not documents:
        return 'No external prep corpus matched the request.'
    return ' '.join(f'{document.title}: {document.text}' for document in documents)




def _warnings_from_model_traces(traces: list[ModelTraceRecord]) -> list[ServiceWarning]:
    warnings: list[ServiceWarning] = []
    for trace in traces:
        if trace.degraded:
            code = (
                ServiceWarningCode.RETRIEVAL_DEGRADED
                if trace.role == ModelRole.REASONING
                else ServiceWarningCode.GENERATION_FALLBACK_USED
            )
            warnings.append(
                ServiceWarning(
                    code=code,
                    message=trace.outcome.replace('_', ' '),
                    degraded=True,
                )
            )
        elif trace.fallback_triggered:
            warnings.append(
                ServiceWarning(
                    code=ServiceWarningCode.GENERATION_FALLBACK_USED,
                    message=trace.outcome.replace('_', ' '),
                    degraded=False,
                )
            )
    deduped: list[ServiceWarning] = []
    seen: set[tuple[str, str]] = set()
    for warning in warnings:
        key = (warning.code.value, warning.message)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(warning)
    return deduped









def _dedupe_warnings(warnings: list[ServiceWarning]) -> list[ServiceWarning]:
    deduped: list[ServiceWarning] = []
    seen: set[tuple[str, str]] = set()
    for warning in warnings:
        key = (warning.code.value, warning.message)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(warning)
    return deduped




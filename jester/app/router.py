from __future__ import annotations

from pydantic import Field

from jester.ai import ModelTraceRecord, SmallFastClassifier
from jester.app.capabilities import first_unsupported_capability
from jester.app.contracts.common import AppDto, Mode


class ModeRoutingError(ValueError):
    """Raised when a request cannot be routed safely to a single mode."""


class UserRequestContext(AppDto):
    request_text: str = Field(min_length=1)
    viewer_id: str | None = None
    session_id: str | None = None
    explicit_mode: Mode | None = None


class ModeDecision(AppDto):
    mode: Mode
    subtask: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(min_length=1)
    model_traces: list[ModelTraceRecord] = Field(default_factory=list)


class _RouteCandidate(AppDto):
    mode: Mode
    subtask: str
    confidence: float
    rationale: str


def route_request(
    request: UserRequestContext,
    *,
    classifier: SmallFastClassifier | None = None,
) -> ModeDecision:
    if request.explicit_mode is not None:
        subtask = _classify_subtask(request.explicit_mode, request.request_text)
        return ModeDecision(
            mode=request.explicit_mode,
            subtask=subtask,
            confidence=0.99,
            rationale='Used explicit mode supplied by caller.',
        )

    candidates: list[_RouteCandidate] = []
    live_candidate = _score_live_dm(request)
    if live_candidate is not None:
        candidates.append(live_candidate)

    prep_candidate = _score_prep(request.request_text)
    if prep_candidate is not None:
        candidates.append(prep_candidate)

    teaching_candidate = _score_teaching(request.request_text)
    if teaching_candidate is not None:
        candidates.append(teaching_candidate)

    if not candidates:
        raise ModeRoutingError('Request did not match any supported Jester mode.')

    ordered = sorted(candidates, key=lambda item: (-item.confidence, item.mode.value, item.subtask))
    ambiguous = len(ordered) > 1 and ordered[0].confidence - ordered[1].confidence < 0.1
    traces: list[ModelTraceRecord] = []

    if classifier is not None:
        artifact = classifier.classify_mode(
            request_text=request.request_text,
            fallback_mode=ordered[0].mode.value,
            fallback_subtask=ordered[0].subtask,
            fallback_confidence=ordered[0].confidence,
            candidates=[f'{candidate.mode.value}:{candidate.subtask}:{candidate.confidence}' for candidate in ordered],
            trace_sink=traces,
        )
        if artifact is not None:
            try:
                classified_mode = Mode(artifact.mode)
            except ValueError:
                classified_mode = ordered[0].mode
            if ambiguous:
                if artifact.confidence >= 0.75:
                    return ModeDecision(
                        mode=classified_mode,
                        subtask=artifact.subtask,
                        confidence=artifact.confidence,
                        rationale=artifact.rationale,
                        model_traces=traces,
                    )
                raise ModeRoutingError(
                    'Request is ambiguous across multiple Jester modes and must be clarified explicitly.'
                )
            if classified_mode == ordered[0].mode:
                return ModeDecision(
                    mode=classified_mode,
                    subtask=artifact.subtask,
                    confidence=max(artifact.confidence, ordered[0].confidence),
                    rationale=artifact.rationale,
                    model_traces=traces,
                )

    if ambiguous:
        raise ModeRoutingError(
            'Request is ambiguous across multiple Jester modes and must be clarified explicitly.'
        )

    winner = ordered[0]
    return ModeDecision(
        mode=winner.mode,
        subtask=winner.subtask,
        confidence=winner.confidence,
        rationale=winner.rationale,
        model_traces=traces,
    )


def _score_live_dm(request: UserRequestContext) -> _RouteCandidate | None:
    normalized = _normalize(request.request_text)
    unsupported = first_unsupported_capability(normalized)
    if unsupported is not None:
        return _RouteCandidate(
            mode=Mode.LIVE_DM,
            subtask='unsupported_capability',
            confidence=0.93,
            rationale=f'Request matched unsupported live-DM capability term {unsupported.matched_term!r}.',
        )

    if any(term in normalized for term in (' attack ', ' move ', ' end turn', ' pass turn')):
        confidence = 0.94 if request.session_id else 0.82
        return _RouteCandidate(
            mode=Mode.LIVE_DM,
            subtask='mechanical_action',
            confidence=confidence,
            rationale='Request uses direct in-session action language.',
        )

    if any(term in normalized for term in ('describe', 'narrate', 'look around', 'what happens')):
        confidence = 0.88 if request.session_id else 0.72
        return _RouteCandidate(
            mode=Mode.LIVE_DM,
            subtask='narrative_request',
            confidence=confidence,
            rationale='Request asks for scene narration tied to live play context.',
        )

    if any(term in normalized for term in ('whose turn', 'what do i see', 'where are we', 'how hurt')):
        confidence = 0.87 if request.session_id else 0.7
        return _RouteCandidate(
            mode=Mode.LIVE_DM,
            subtask='informational_query',
            confidence=confidence,
            rationale='Request asks for live session state or table information.',
        )

    return None


def _score_prep(text: str) -> _RouteCandidate | None:
    normalized = _normalize(text)
    prep_markers = ('prep', 'prepare', 'outline', 'build', 'design', 'generate', 'refine')
    if not any(marker in normalized for marker in prep_markers):
        return None

    subtask = _classify_prep_subtask(normalized)
    return _RouteCandidate(
        mode=Mode.DM_PREP,
        subtask=subtask,
        confidence=0.9,
        rationale='Request uses explicit preparation language for campaign or session materials.',
    )


def _score_teaching(text: str) -> _RouteCandidate | None:
    normalized = _normalize(text)
    teaching_markers = (
        'explain',
        'teach',
        'how do i',
        'how does',
        'what is',
        'clarify',
        'learn',
        'practice',
    )
    if not any(marker in normalized for marker in teaching_markers):
        return None

    subtask = 'practice_scenario' if 'practice' in normalized else 'concept_explanation'
    return _RouteCandidate(
        mode=Mode.PLAYER_TEACHING,
        subtask=subtask,
        confidence=0.89,
        rationale='Request asks for rules explanation or guided learning support.',
    )


def _classify_subtask(mode: Mode, text: str) -> str:
    normalized = _normalize(text)
    if mode == Mode.DM_PREP:
        return _classify_prep_subtask(normalized)
    if mode == Mode.PLAYER_TEACHING:
        return 'practice_scenario' if 'practice' in normalized else 'concept_explanation'
    if first_unsupported_capability(normalized) is not None:
        return 'unsupported_capability'
    if any(term in normalized for term in ('attack', 'move', 'end turn', 'pass turn')):
        return 'mechanical_action'
    if any(term in normalized for term in ('describe', 'narrate', 'look around', 'what happens')):
        return 'narrative_request'
    return 'informational_query'


def _classify_prep_subtask(normalized: str) -> str:
    if 'npc' in normalized or any(term in normalized for term in ('villain', 'innkeeper', 'blacksmith')):
        return 'npc_brief'
    if any(term in normalized for term in ('town', 'village', 'city', 'settlement', 'location')):
        return 'town_brief'
    if any(term in normalized for term in ('encounter', 'ambush', 'battle', 'fight', 'combat')):
        return 'encounter_outline'
    if any(term in normalized for term in ('quest', 'hook', 'rumor', 'lead')):
        return 'quest_hook'
    return 'session_prep_packet'


def _normalize(text: str) -> str:
    return f" {' '.join(text.lower().split())} "

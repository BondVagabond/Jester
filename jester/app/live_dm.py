# ruff: noqa: I001
from __future__ import annotations

import json
import re

from jester.ai import (
    ModelRegistry,
    ModelRole,
    ModelRoleUnavailableError,
    ModelSelectionPolicy,
    ModelTraceRecord,
    RoleNarrationModelClient,
    RolePromptModelClient,
    SmallFastClassifier,
)
from jester.app.capabilities import CapabilityDecision, first_unsupported_capability
from jester.app.contracts import (
    LiveDmRequest,
    LiveDmRequestKind,
    LiveDmTurnResponse,
    NarrationBlock,
    RulesResolutionSummary,
    VisibleNpcView,
    VisiblePlayerCharacterView,
    VisibleSessionView,
)
from jester.app.orchestration import (
    GenerationRequest,
    LiveDmServiceResult,
    RetrievalContextService,
    RetrievedContext,
    RouteSelection,
    ServiceWarning,
    ServiceWarningCode,
    WorkspaceDebugInfo,
    WorkspaceName,
    WorkspacePromptAssembler,
    WorkspaceRoutingPolicy,
    WorkspaceTask,
)
from jester.app.prompting import PromptModelClient, generate_prompt_block
from jester.app.visibility import build_visible_session_view
from jester.domain import ActionIntent, ActionResult, ActionStatus, ActionType, Position, Session
from jester.engine.narration import ModelClient, NarrationRequest, build_narration
from jester.engine.pipeline import process_player_action
from jester.retrieval import QueryRetriever, RetrievalQuery, RetrievedDocument
from jester.state import StateStore
from jester.validation import OutputValidationPolicy


_ATTACK_PATTERN = re.compile(r'\battack\b(?:\s+(?:the\s+)?)?(?P<target>[a-z0-9][a-z0-9 -]+)?', re.IGNORECASE)
_MOVE_PATTERN = re.compile(r'\bmove\b(?:\s+to)?(?:\s+slot)?\s+(?P<slot>-?\d+)\b', re.IGNORECASE)
_END_TURN_PATTERN = re.compile(r'\b(?:end\s+turn|end\s+my\s+turn|pass\s+turn)\b', re.IGNORECASE)


class LiveDmServiceError(RuntimeError):
    """Raised when a live-DM request cannot be handled safely."""


class LiveDmService:
    def __init__(
        self,
        *,
        state_store: StateStore | None = None,
        retriever: QueryRetriever | None = None,
        info_model_client: PromptModelClient | None = None,
        narration_model_client: ModelClient | None = None,
        policy: OutputValidationPolicy | None = None,
        model_registry: ModelRegistry | None = None,
        selection_policy: ModelSelectionPolicy | None = None,
        classifier: SmallFastClassifier | None = None,
    ) -> None:
        self._state_store = state_store
        self._retriever = retriever
        self._info_model_client = info_model_client
        self._narration_model_client = narration_model_client
        self._policy = policy
        self._selector = selection_policy or (ModelSelectionPolicy(model_registry) if model_registry else None)
        self._classifier = classifier or (SmallFastClassifier(self._selector) if self._selector is not None else None)
        self._retrieval_context = RetrievalContextService(retriever)
        self._prompt_assembler = WorkspacePromptAssembler(
            selection_policy=self._selector,
            legacy_model_client=info_model_client,
            policy=self._policy,
        )


    def handle_request(
        self,
        request: LiveDmRequest,
        *,
        session: Session | None = None,
    ) -> LiveDmTurnResponse:
        return self.execute_turn(request, session=session).response

    def execute_turn(
        self,
        request: LiveDmRequest,
        *,
        session: Session | None = None,
    ) -> LiveDmServiceResult:
        active_session = session or self._load_session(request.session_id)
        before_signature = _session_signature(active_session)
        traces: list[ModelTraceRecord] = []
        warnings: list[ServiceWarning] = []
        routes = [WorkspaceRoutingPolicy.live_dm_classification()]

        unsupported = first_unsupported_capability(request.request_text)
        if unsupported is not None:
            warnings.append(
                ServiceWarning(
                    code=ServiceWarningCode.UNSUPPORTED_CAPABILITY,
                    message=unsupported.reason,
                    degraded=False,
                )
            )
            response = self._build_unsupported_response(active_session, request, unsupported, trace_sink=traces)
            self._assert_read_only(active_session, before_signature, request_kind='unsupported')
            deduped = _dedupe_warnings([*warnings, *_warnings_from_model_traces(traces)])
            return LiveDmServiceResult(
                response=response,
                warnings=deduped,
                debug=WorkspaceDebugInfo(
                    workspace=WorkspaceName.LIVE_DM,
                    primary_task=WorkspaceTask.LIVE_DM_RULES_EXPLANATION,
                    routes=routes,
                    warnings=deduped,
                    notes=['Unsupported live DM capabilities remain bounded and read-only.'],
                ),
                state_mutated=False,
            )

        request_kind = self._classify_request_kind(request.request_text, trace_sink=traces)
        if request_kind == LiveDmRequestKind.MECHANICAL_ACTION:
            result = self._execute_mechanical_turn(
                active_session,
                request,
                warnings=warnings,
                trace_sink=traces,
                routes=routes,
            )
            if session is None and result.state_mutated and self._state_store is not None:
                self._state_store.save_session(active_session)
            return result
        if request_kind == LiveDmRequestKind.NARRATIVE_REQUEST:
            return self._execute_narrative_turn(
                active_session,
                request,
                before_signature=before_signature,
                warnings=warnings,
                trace_sink=traces,
                routes=routes,
            )

        return self._execute_info_turn(
            active_session,
            request,
            before_signature=before_signature,
            warnings=warnings,
            trace_sink=traces,
            routes=routes,
        )

    def _execute_mechanical_turn(
        self,
        session: Session,
        request: LiveDmRequest,
        *,
        warnings: list[ServiceWarning],
        trace_sink: list[ModelTraceRecord],
        routes: list[RouteSelection],
    ) -> LiveDmServiceResult:
        routes.append(WorkspaceRoutingPolicy.live_dm_mechanics())
        try:
            actor_id = self._resolve_actor_id(session, request.viewer_id, request.actor_id)
            intent = self._parse_action_intent(session, request.request_id, request.request_text)
        except LiveDmServiceError as exc:
            warnings.append(
                ServiceWarning(
                    code=ServiceWarningCode.INVALID_ACTION,
                    message=str(exc),
                    degraded=False,
                )
            )
            visible_session = build_visible_session_view(session, request.viewer_id)
            explanation_route = WorkspaceRoutingPolicy.live_dm_rules_explanation()
            routes.append(explanation_route)
            retrieved_context = self._retrieval_context.fetch(
                explanation_route,
                query_text=request.request_text,
                request_id=request.request_id,
                session_id=request.session_id,
            )
            warnings.extend(retrieved_context.warnings)
            rules_response = self._prompt_assembler.generate(
                GenerationRequest(
                    route=explanation_route,
                    template_values={
                        'question': request.request_text,
                        'state_summary': _visible_state_summary(visible_session),
                        'retrieved_context': _retrieved_context_text_from_context(retrieved_context),
                        'resolution_summary': str(exc),
                    },
                    fallback_text=str(exc),
                ),
                trace_sink=trace_sink,
            )
            warnings.extend(rules_response.warnings)
            _append_generation_trace(
                trace_sink,
                prompt_name=rules_response.block.prompt_name,
                prompt_version=rules_response.block.prompt_version,
                used_fallback=rules_response.block.used_fallback,
                validation_passed=rules_response.block.validation_passed,
                provider_name=self._provider_name_for_role(explanation_route.model_role),
                model_name=self._model_name_for_role(explanation_route.model_role),
                outcome='live_dm_rules_explanation_validated',
                role=explanation_route.model_role or ModelRole.REASONING,
            )
            deduped = _dedupe_warnings([*warnings, *_warnings_from_model_traces(trace_sink)])
            return LiveDmServiceResult(
                response=LiveDmTurnResponse(
                    request_kind=LiveDmRequestKind.MECHANICAL_ACTION,
                    visible_session=visible_session,
                    resolution=RulesResolutionSummary(
                        request_kind=LiveDmRequestKind.MECHANICAL_ACTION,
                        engine_invoked=False,
                        state_mutated=False,
                        errors=[str(exc)],
                    ),
                    info_response=rules_response.block,
                    model_traces=trace_sink,
                ),
                warnings=deduped,
                debug=WorkspaceDebugInfo(
                    workspace=WorkspaceName.LIVE_DM,
                    primary_task=WorkspaceTask.LIVE_DM_MECHANICS,
                    routes=routes,
                    retrieved=[retrieved_context],
                    warnings=deduped,
                    notes=['Invalid mechanical requests remain read-only and receive a bounded explanation.'],
                ),
                state_mutated=False,
            )

        before_signature = _session_signature(session)
        result = process_player_action(session, actor_id, intent)
        state_mutated = before_signature != _session_signature(session)
        visible_session = build_visible_session_view(session, request.viewer_id)

        explanation_route = WorkspaceRoutingPolicy.live_dm_rules_explanation()
        routes.append(explanation_route)
        retrieved_context = self._retrieval_context.fetch(
            explanation_route,
            query_text=request.request_text,
            request_id=request.request_id,
            session_id=request.session_id,
        )
        warnings.extend(retrieved_context.warnings)
        rules_response = self._prompt_assembler.generate(
            GenerationRequest(
                route=explanation_route,
                template_values={
                    'question': request.request_text,
                    'state_summary': _visible_state_summary(visible_session),
                    'retrieved_context': _retrieved_context_text_from_context(retrieved_context),
                    'resolution_summary': _mechanical_resolution_text(result),
                },
                fallback_text=_mechanical_fallback_text(visible_session, result),
            ),
            trace_sink=trace_sink,
        )
        warnings.extend(rules_response.warnings)
        _append_generation_trace(
            trace_sink,
            prompt_name=rules_response.block.prompt_name,
            prompt_version=rules_response.block.prompt_version,
            used_fallback=rules_response.block.used_fallback,
            validation_passed=rules_response.block.validation_passed,
            provider_name=self._provider_name_for_role(explanation_route.model_role),
            model_name=self._model_name_for_role(explanation_route.model_role),
            outcome='live_dm_rules_explanation_validated',
            role=explanation_route.model_role or ModelRole.REASONING,
        )

        narration = None
        if request.include_narration and result.status == ActionStatus.APPLIED:
            narration_route = WorkspaceRoutingPolicy.live_dm_narration()
            routes.append(narration_route)
            narration_result = build_narration(
                NarrationRequest(
                    state_snapshot=visible_session.model_dump(mode='json'),
                    action_result=result,
                    prompt_name=narration_route.prompt_name or 'live_dm_narration',
                    prompt_version=narration_route.prompt_version or 'v1',
                ),
                retriever=self._retriever,
                model_client=self._resolve_narration_model_client(trace_sink),
                policy=self._policy,
            )
            _append_generation_trace(
                trace_sink,
                prompt_name=narration_result.prompt_name,
                prompt_version=narration_result.prompt_version,
                used_fallback=narration_result.used_fallback,
                validation_passed=narration_result.validation_passed,
                provider_name=self._provider_name_for_role(narration_route.model_role),
                model_name=self._model_name_for_role(narration_route.model_role),
                outcome='live_dm_narration_validated',
                role=narration_route.model_role or ModelRole.PRIMARY_GENERATION,
            )
            narration = NarrationBlock(
                text=narration_result.text,
                prompt_name=narration_result.prompt_name,
                prompt_version=narration_result.prompt_version,
                used_fallback=narration_result.used_fallback,
                validation_passed=narration_result.validation_passed,
                issues=narration_result.issues,
            )

        resolution = RulesResolutionSummary(
            request_kind=LiveDmRequestKind.MECHANICAL_ACTION,
            engine_invoked=True,
            state_mutated=state_mutated,
            action_status=result.status,
            action_type=result.action_type,
            actor_id=actor_id,
            target_id=result.target_id,
            errors=list(result.errors),
        )
        deduped = _dedupe_warnings([*warnings, *_warnings_from_model_traces(trace_sink)])
        return LiveDmServiceResult(
            response=LiveDmTurnResponse(
                request_kind=LiveDmRequestKind.MECHANICAL_ACTION,
                visible_session=visible_session,
                resolution=resolution,
                narration=narration,
                info_response=rules_response.block,
                model_traces=trace_sink,
            ),
            warnings=deduped,
            debug=WorkspaceDebugInfo(
                workspace=WorkspaceName.LIVE_DM,
                primary_task=WorkspaceTask.LIVE_DM_MECHANICS,
                routes=routes,
                retrieved=[retrieved_context],
                warnings=deduped,
                notes=['Mechanics remain deterministic; narration and rules explanation are additive overlays.'],
            ),
            state_mutated=state_mutated,
        )

    def _execute_info_turn(
        self,
        session: Session,
        request: LiveDmRequest,
        *,
        before_signature: str,
        warnings: list[ServiceWarning],
        trace_sink: list[ModelTraceRecord],
        routes: list[RouteSelection],
    ) -> LiveDmServiceResult:
        visible_session = build_visible_session_view(session, request.viewer_id)
        info_route = WorkspaceRoutingPolicy.live_dm_info()
        routes.append(info_route)
        retrieved_context = self._retrieval_context.fetch(
            info_route,
            query_text=request.request_text,
            request_id=request.request_id,
            session_id=request.session_id,
        )
        warnings.extend(retrieved_context.warnings)
        info_response = self._prompt_assembler.generate(
            GenerationRequest(
                route=info_route,
                template_values={
                    'question': request.request_text,
                    'state_summary': _visible_state_summary(visible_session),
                    'retrieved_context': _retrieved_context_text_from_context(retrieved_context),
                },
                fallback_text=self._build_info_fallback_text(visible_session, request.request_text),
            ),
            trace_sink=trace_sink,
        )
        warnings.extend(info_response.warnings)
        _append_generation_trace(
            trace_sink,
            prompt_name=info_response.block.prompt_name,
            prompt_version=info_response.block.prompt_version,
            used_fallback=info_response.block.used_fallback,
            validation_passed=info_response.block.validation_passed,
            provider_name=self._provider_name_for_role(info_route.model_role),
            model_name=self._model_name_for_role(info_route.model_role),
            outcome='live_dm_info_validated',
            role=info_route.model_role or ModelRole.REASONING,
        )
        self._assert_read_only(session, before_signature, request_kind='informational')
        deduped = _dedupe_warnings([*warnings, *_warnings_from_model_traces(trace_sink)])
        return LiveDmServiceResult(
            response=LiveDmTurnResponse(
                request_kind=LiveDmRequestKind.INFORMATIONAL_QUERY,
                visible_session=visible_session,
                resolution=RulesResolutionSummary(
                    request_kind=LiveDmRequestKind.INFORMATIONAL_QUERY,
                    engine_invoked=False,
                    state_mutated=False,
                ),
                info_response=info_response.block,
                model_traces=trace_sink,
            ),
            warnings=deduped,
            debug=WorkspaceDebugInfo(
                workspace=WorkspaceName.LIVE_DM,
                primary_task=WorkspaceTask.LIVE_DM_INFO,
                routes=routes,
                retrieved=[retrieved_context],
                warnings=deduped,
                notes=['Informational live DM responses are read-only and backend-authored.'],
            ),
            state_mutated=False,
        )

    def _execute_narrative_turn(
        self,
        session: Session,
        request: LiveDmRequest,
        *,
        before_signature: str,
        warnings: list[ServiceWarning],
        trace_sink: list[ModelTraceRecord],
        routes: list[RouteSelection],
    ) -> LiveDmServiceResult:
        visible_session = build_visible_session_view(session, request.viewer_id)
        narrative_route = WorkspaceRoutingPolicy.live_dm_narration()
        routes.append(narrative_route)
        retrieved_context = self._retrieval_context.fetch(
            narrative_route,
            query_text=request.request_text,
            request_id=request.request_id,
            session_id=request.session_id,
        )
        warnings.extend(retrieved_context.warnings)
        block = self._prompt_assembler.generate(
            GenerationRequest(
                route=narrative_route,
                template_values={
                    'state_summary': _visible_state_summary(visible_session),
                    'action_summary': f'Narrative focus: {request.request_text}',
                    'retrieved_context': _retrieved_context_text_from_context(retrieved_context),
                },
                fallback_text=self._build_scene_fallback_text(visible_session),
            ),
            trace_sink=trace_sink,
        )
        warnings.extend(block.warnings)
        _append_generation_trace(
            trace_sink,
            prompt_name=block.block.prompt_name,
            prompt_version=block.block.prompt_version,
            used_fallback=block.block.used_fallback,
            validation_passed=block.block.validation_passed,
            provider_name=self._provider_name_for_role(narrative_route.model_role),
            model_name=self._model_name_for_role(narrative_route.model_role),
            outcome='live_dm_scene_narration_validated',
            role=narrative_route.model_role or ModelRole.PRIMARY_GENERATION,
        )
        self._assert_read_only(session, before_signature, request_kind='narrative')
        narration = NarrationBlock(
            text=block.block.text,
            prompt_name=block.block.prompt_name,
            prompt_version=block.block.prompt_version,
            used_fallback=block.block.used_fallback,
            validation_passed=block.block.validation_passed,
            issues=block.block.issues,
        )
        deduped = _dedupe_warnings([*warnings, *_warnings_from_model_traces(trace_sink)])
        return LiveDmServiceResult(
            response=LiveDmTurnResponse(
                request_kind=LiveDmRequestKind.NARRATIVE_REQUEST,
                visible_session=visible_session,
                resolution=RulesResolutionSummary(
                    request_kind=LiveDmRequestKind.NARRATIVE_REQUEST,
                    engine_invoked=False,
                    state_mutated=False,
                ),
                narration=narration,
                model_traces=trace_sink,
            ),
            warnings=deduped,
            debug=WorkspaceDebugInfo(
                workspace=WorkspaceName.LIVE_DM,
                primary_task=WorkspaceTask.LIVE_DM_NARRATION,
                routes=routes,
                retrieved=[retrieved_context],
                warnings=deduped,
                notes=['Narrative live DM requests are read-only overlays on authoritative state.'],
            ),
            state_mutated=False,
        )
    def _load_session(self, session_id: str) -> Session:
        if self._state_store is None:
            raise LiveDmServiceError('A Session instance or StateStore is required for live DM.')
        return self._state_store.load_session(session_id)

    def _classify_request_kind(
        self,
        request_text: str,
        *,
        trace_sink: list[ModelTraceRecord],
    ) -> LiveDmRequestKind:
        fallback_kind, fallback_confidence = _deterministic_request_kind(request_text)
        if self._classifier is None:
            return fallback_kind
        artifact = self._classifier.classify_live_dm_intent(
            request_text=request_text,
            fallback_kind=fallback_kind.value,
            fallback_confidence=fallback_confidence,
            trace_sink=trace_sink,
        )
        if artifact is None:
            return fallback_kind
        try:
            classified = LiveDmRequestKind(artifact.request_kind)
        except ValueError:
            return fallback_kind
        if fallback_kind != LiveDmRequestKind.INFORMATIONAL_QUERY and classified != fallback_kind:
            return fallback_kind
        if artifact.confidence < 0.6:
            return fallback_kind
        return classified

    def _handle_mechanical_request(
        self,
        session: Session,
        request: LiveDmRequest,
        *,
        trace_sink: list[ModelTraceRecord],
    ) -> LiveDmTurnResponse:
        actor_id = self._resolve_actor_id(session, request.viewer_id, request.actor_id)
        intent = self._parse_action_intent(session, request.request_id, request.request_text)
        before_signature = _session_signature(session)
        result = process_player_action(session, actor_id, intent)
        after_signature = _session_signature(session)
        state_mutated = before_signature != after_signature
        visible_session = build_visible_session_view(session, request.viewer_id)
        narration = None
        if request.include_narration and result.status == ActionStatus.APPLIED:
            narration_result = build_narration(
                NarrationRequest(
                    state_snapshot=visible_session.model_dump(mode='json'),
                    action_result=result,
                    prompt_name='live_dm_narration',
                    prompt_version='v1',
                ),
                retriever=self._retriever,
                model_client=self._resolve_narration_model_client(trace_sink),
                policy=self._policy,
            )
            _append_generation_trace(
                trace_sink,
                prompt_name=narration_result.prompt_name,
                prompt_version=narration_result.prompt_version,
                used_fallback=narration_result.used_fallback,
                validation_passed=narration_result.validation_passed,
                provider_name=self._primary_provider_name(),
                model_name=self._primary_model_name(),
                outcome='live_dm_narration_validated',
            )
            narration = NarrationBlock(
                text=narration_result.text,
                prompt_name=narration_result.prompt_name,
                prompt_version=narration_result.prompt_version,
                used_fallback=narration_result.used_fallback,
                validation_passed=narration_result.validation_passed,
                issues=narration_result.issues,
            )

        resolution = RulesResolutionSummary(
            request_kind=LiveDmRequestKind.MECHANICAL_ACTION,
            engine_invoked=True,
            state_mutated=state_mutated,
            action_status=result.status,
            action_type=result.action_type,
            actor_id=actor_id,
            target_id=result.target_id,
            errors=list(result.errors),
        )
        return LiveDmTurnResponse(
            request_kind=LiveDmRequestKind.MECHANICAL_ACTION,
            visible_session=visible_session,
            resolution=resolution,
            narration=narration,
            model_traces=trace_sink,
        )

    def _handle_info_request(
        self,
        session: Session,
        request: LiveDmRequest,
        *,
        trace_sink: list[ModelTraceRecord],
    ) -> LiveDmTurnResponse:
        visible_session = build_visible_session_view(session, request.viewer_id)
        fallback_text = self._build_info_fallback_text(visible_session, request.request_text)
        retrieved = self._retrieve_documents(request.request_text)
        info_response = generate_prompt_block(
            prompt_name='live_dm_info_response',
            prompt_version='v1',
            template_values={
                'question': request.request_text,
                'state_summary': _visible_state_summary(visible_session),
                'retrieved_context': _retrieved_context_text(retrieved),
            },
            fallback_text=fallback_text,
            model_client=self._resolve_info_model_client(trace_sink),
            policy=self._policy,
        )
        _append_generation_trace(
            trace_sink,
            prompt_name=info_response.prompt_name,
            prompt_version=info_response.prompt_version,
            used_fallback=info_response.used_fallback,
            validation_passed=info_response.validation_passed,
            provider_name=self._primary_provider_name(),
            model_name=self._primary_model_name(),
            outcome='live_dm_info_validated',
        )
        resolution = RulesResolutionSummary(
            request_kind=LiveDmRequestKind.INFORMATIONAL_QUERY,
            engine_invoked=False,
            state_mutated=False,
        )
        return LiveDmTurnResponse(
            request_kind=LiveDmRequestKind.INFORMATIONAL_QUERY,
            visible_session=visible_session,
            resolution=resolution,
            info_response=info_response,
            model_traces=trace_sink,
        )

    def _handle_narrative_request(
        self,
        session: Session,
        request: LiveDmRequest,
        *,
        trace_sink: list[ModelTraceRecord],
    ) -> LiveDmTurnResponse:
        visible_session = build_visible_session_view(session, request.viewer_id)
        retrieved = self._retrieve_documents(request.request_text)
        block = generate_prompt_block(
            prompt_name='live_dm_narration',
            prompt_version='v1',
            template_values={
                'state_summary': _visible_state_summary(visible_session),
                'action_summary': f'Narrative focus: {request.request_text}',
                'retrieved_context': _retrieved_context_text(retrieved),
            },
            fallback_text=self._build_scene_fallback_text(visible_session),
            model_client=self._resolve_info_model_client(trace_sink),
            policy=self._policy,
        )
        _append_generation_trace(
            trace_sink,
            prompt_name=block.prompt_name,
            prompt_version=block.prompt_version,
            used_fallback=block.used_fallback,
            validation_passed=block.validation_passed,
            provider_name=self._primary_provider_name(),
            model_name=self._primary_model_name(),
            outcome='live_dm_scene_narration_validated',
        )
        narration = NarrationBlock(
            text=block.text,
            prompt_name=block.prompt_name,
            prompt_version=block.prompt_version,
            used_fallback=block.used_fallback,
            validation_passed=block.validation_passed,
            issues=block.issues,
        )
        resolution = RulesResolutionSummary(
            request_kind=LiveDmRequestKind.NARRATIVE_REQUEST,
            engine_invoked=False,
            state_mutated=False,
        )
        return LiveDmTurnResponse(
            request_kind=LiveDmRequestKind.NARRATIVE_REQUEST,
            visible_session=visible_session,
            resolution=resolution,
            narration=narration,
            model_traces=trace_sink,
        )

    def _build_unsupported_response(
        self,
        session: Session,
        request: LiveDmRequest,
        unsupported: CapabilityDecision,
        *,
        trace_sink: list[ModelTraceRecord],
    ) -> LiveDmTurnResponse:
        visible_session = build_visible_session_view(session, request.viewer_id)
        info_response = generate_prompt_block(
            prompt_name='live_dm_info_response',
            prompt_version='v1',
            template_values={
                'question': request.request_text,
                'state_summary': _visible_state_summary(visible_session),
                'retrieved_context': unsupported.reason,
            },
            fallback_text=unsupported.reason,
            model_client=self._resolve_info_model_client(trace_sink),
            policy=self._policy,
        )
        _append_generation_trace(
            trace_sink,
            prompt_name=info_response.prompt_name,
            prompt_version=info_response.prompt_version,
            used_fallback=info_response.used_fallback,
            validation_passed=info_response.validation_passed,
            provider_name=self._primary_provider_name(),
            model_name=self._primary_model_name(),
            outcome='live_dm_unsupported_validated',
        )
        resolution = RulesResolutionSummary(
            request_kind=LiveDmRequestKind.UNSUPPORTED,
            engine_invoked=False,
            state_mutated=False,
            errors=[unsupported.reason],
            unsupported_capabilities=[unsupported],
        )
        return LiveDmTurnResponse(
            request_kind=LiveDmRequestKind.UNSUPPORTED,
            visible_session=visible_session,
            resolution=resolution,
            info_response=info_response,
            model_traces=trace_sink,
        )

    def _resolve_info_model_client(self, trace_sink: list[ModelTraceRecord]) -> PromptModelClient | None:
        if self._selector is not None:
            try:
                selected = self._selector.require(ModelRole.PRIMARY_GENERATION)
            except ModelRoleUnavailableError as exc:
                raise LiveDmServiceError(str(exc)) from exc
            return RolePromptModelClient(selected, trace_sink=trace_sink)
        return self._info_model_client

    def _resolve_narration_model_client(self, trace_sink: list[ModelTraceRecord]) -> ModelClient | None:
        if self._selector is not None:
            try:
                selected = self._selector.require(ModelRole.PRIMARY_GENERATION)
            except ModelRoleUnavailableError as exc:
                raise LiveDmServiceError(str(exc)) from exc
            return RoleNarrationModelClient(selected, trace_sink=trace_sink)
        return self._narration_model_client

    def _primary_provider_name(self) -> str | None:
        if self._selector is not None:
            return self._selector.resolve(ModelRole.PRIMARY_GENERATION).provider_name
        if self._info_model_client is not None or self._narration_model_client is not None:
            return 'legacy'
        return None

    def _primary_model_name(self) -> str | None:
        if self._selector is not None:
            return self._selector.resolve(ModelRole.PRIMARY_GENERATION).model_name
        if self._info_model_client is not None:
            return type(self._info_model_client).__name__
        if self._narration_model_client is not None:
            return type(self._narration_model_client).__name__
        return None

    def _provider_name_for_role(self, role: ModelRole | None) -> str | None:
        if role is None:
            return None
        if self._selector is not None:
            return self._selector.resolve(role).provider_name
        if self._info_model_client is not None or self._narration_model_client is not None:
            return 'legacy'
        return None

    def _model_name_for_role(self, role: ModelRole | None) -> str | None:
        if role is None:
            return None
        if self._selector is not None:
            return self._selector.resolve(role).model_name
        if self._info_model_client is not None:
            return type(self._info_model_client).__name__
        if self._narration_model_client is not None:
            return type(self._narration_model_client).__name__
        return None

    def _resolve_actor_id(
        self,
        session: Session,
        viewer_id: str,
        actor_id: str | None,
    ) -> str:
        if viewer_id == session.dm_id:
            if actor_id is None:
                raise LiveDmServiceError('DM requests must specify actor_id for mechanical actions.')
            return actor_id

        controlled = [
            pc.entity_id
            for pc in session.player_characters.values()
            if pc.controller_id == viewer_id
        ]
        if actor_id is None:
            if len(controlled) != 1:
                raise LiveDmServiceError(
                    'Player mechanical requests require an explicit actor when control is ambiguous.'
                )
            return controlled[0]
        if actor_id not in controlled:
            raise LiveDmServiceError(f'Viewer {viewer_id!r} cannot act as {actor_id!r}.')
        return actor_id

    def _parse_action_intent(
        self,
        session: Session,
        request_id: str,
        request_text: str,
    ) -> ActionIntent:
        attack_match = _ATTACK_PATTERN.search(request_text)
        if attack_match is not None:
            target_text = attack_match.group('target') or ''
            if not target_text.strip():
                raise LiveDmServiceError('Attack requests must name a target.')
            target_id = _resolve_target_id(session, target_text)
            return ActionIntent(
                intent_id=f'{request_id}-attack',
                action_type=ActionType.ATTACK,
                target_id=target_id,
            )

        move_match = _MOVE_PATTERN.search(request_text)
        if move_match is not None:
            slot = int(move_match.group('slot'))
            return ActionIntent(
                intent_id=f'{request_id}-move',
                action_type=ActionType.MOVE,
                destination=Position(slot=slot),
            )

        if _END_TURN_PATTERN.search(request_text) is not None:
            return ActionIntent(
                intent_id=f'{request_id}-end-turn',
                action_type=ActionType.END_TURN,
            )

        raise LiveDmServiceError(
            'Supported mechanical requests are attack, move to slot N, and end turn.'
        )

    def _retrieve_documents(self, query_text: str) -> list[RetrievedDocument]:
        if self._retriever is None:
            return []
        return self._retriever.search(RetrievalQuery(text=query_text, k=3))

    def _build_info_fallback_text(
        self,
        visible_session: VisibleSessionView,
        question: str,
    ) -> str:
        normalized = question.lower()
        combat_state = visible_session.combat_state
        if combat_state is not None and 'whose turn' in normalized:
            current_actor = combat_state.combatants[combat_state.current_combatant_id].name
            return f'It is {current_actor} turn in round {combat_state.round_number}.'
        if 'how hurt' in normalized or 'hit points' in normalized:
            target = _find_visible_entity(visible_session, question)
            if target is not None:
                return f'{target[0]} has {target[1].current_hp} of {target[1].max_hp} hit points remaining.'
        return self._build_scene_fallback_text(visible_session)

    def _build_scene_fallback_text(self, visible_session: VisibleSessionView) -> str:
        scene = visible_session.scenes[visible_session.current_scene_id]
        location = visible_session.locations[scene.location_id]
        return f'{scene.summary} {location.description}'

    def _assert_read_only(
        self,
        session: Session,
        before_signature: str,
        *,
        request_kind: str,
    ) -> None:
        after_signature = _session_signature(session)
        if before_signature != after_signature:
            raise LiveDmServiceError(f'{request_kind} requests must not mutate canonical state.')


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
    role: ModelRole = ModelRole.PRIMARY_GENERATION,
) -> None:
    trace_sink.append(
        ModelTraceRecord(
            role=role,
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


def _deterministic_request_kind(request_text: str) -> tuple[LiveDmRequestKind, float]:
    normalized = request_text.lower()
    if _ATTACK_PATTERN.search(request_text) or _MOVE_PATTERN.search(request_text):
        return LiveDmRequestKind.MECHANICAL_ACTION, 0.94
    if _END_TURN_PATTERN.search(request_text):
        return LiveDmRequestKind.MECHANICAL_ACTION, 0.94
    if any(term in normalized for term in ('describe', 'narrate', 'look around', 'what happens')):
        return LiveDmRequestKind.NARRATIVE_REQUEST, 0.86
    return LiveDmRequestKind.INFORMATIONAL_QUERY, 0.72


def _session_signature(session: Session) -> str:
    return json.dumps(session.model_dump(mode='json'), sort_keys=True)


def _visible_state_summary(visible_session: VisibleSessionView) -> str:
    scene = visible_session.scenes[visible_session.current_scene_id]
    location = visible_session.locations[scene.location_id]
    payload = {
        'scene': scene.name,
        'scene_summary': scene.summary,
        'location': location.name,
        'location_description': location.description,
    }
    return json.dumps(payload, sort_keys=True)


def _retrieved_context_text(documents: list[RetrievedDocument]) -> str:
    if not documents:
        return 'No external lore matched the current request.'
    return ' '.join(f'{document.title}: {document.text}' for document in documents)


def _normalize_name(value: str) -> str:
    return re.sub(r'[^a-z0-9]+', ' ', value.lower()).strip()


def _resolve_target_id(session: Session, target_text: str) -> str:
    target_key = _normalize_name(target_text)
    candidates: dict[str, str] = {}
    for entity_id, player_character in session.player_characters.items():
        candidates[_normalize_name(player_character.name)] = entity_id
    for entity_id, npc in session.npcs.items():
        candidates[_normalize_name(npc.name)] = entity_id
    if target_key in candidates:
        return candidates[target_key]
    for name_key, entity_id in candidates.items():
        if target_key in name_key or name_key in target_key:
            return entity_id
    raise LiveDmServiceError(f'Could not resolve target from {target_text!r}.')


def _find_visible_entity(
    visible_session: VisibleSessionView,
    question: str,
) -> tuple[str, VisiblePlayerCharacterView | VisibleNpcView] | None:
    target_key = _normalize_name(question)
    for character in visible_session.player_characters.values():
        if _normalize_name(character.name) in target_key:
            return character.name, character
    for npc in visible_session.npcs.values():
        if _normalize_name(npc.name) in target_key:
            return npc.name, npc
    return None






def _retrieved_context_text_from_context(context: RetrievedContext) -> str:
    if not context.hits:
        return 'No additional corpus context matched the request.'
    return ' '.join(f'{item.title}: {item.excerpt}' for item in context.hits)


def _mechanical_resolution_text(result: ActionResult) -> str:
    if result.status == ActionStatus.REJECTED:
        return ' '.join(result.errors) or 'The requested action was rejected.'
    if result.action_type == ActionType.ATTACK and result.attack_result is not None:
        hit_text = 'hit' if result.attack_result.hit else 'miss'
        return (
            f'Attack resolved as a {hit_text}. '
            f'Attack total {result.attack_result.attack_total} against armor class '
            f'{result.attack_result.target_armor_class}. '
            f'Damage applied {result.attack_result.damage_applied}.'
        )
    if result.action_type == ActionType.MOVE and result.movement_result is not None:
        return (
            f'Movement resolved from slot {result.movement_result.previous_position.slot} '
            f'to slot {result.movement_result.current_position.slot}.'
        )
    if result.action_type == ActionType.END_TURN:
        return 'The active turn ended and initiative advanced to the next combatant.'
    return f'{result.action_type.value} resolved through the deterministic engine.'


def _mechanical_fallback_text(visible_session: VisibleSessionView, result: ActionResult) -> str:
    actor_name = _find_actor_name(visible_session, result.actor_id)
    if result.status == ActionStatus.REJECTED:
        return ' '.join(result.errors) or f'{actor_name} could not complete that action.'
    if result.action_type == ActionType.ATTACK and result.attack_result is not None:
        target_name = _find_actor_name(visible_session, result.target_id)
        if result.attack_result.hit:
            return f'{actor_name} hit {target_name} for {result.attack_result.damage_applied} damage.'
        return f'{actor_name} missed {target_name}.'
    if result.action_type == ActionType.MOVE and result.movement_result is not None:
        return f'{actor_name} moved to slot {result.movement_result.current_position.slot}.'
    if result.action_type == ActionType.END_TURN:
        return f'{actor_name} ended the turn.'
    return f'{actor_name} completed a deterministic action.'


def _find_actor_name(visible_session: VisibleSessionView, entity_id: str | None) -> str:
    if entity_id is None:
        return 'The actor'
    if entity_id in visible_session.player_characters:
        return visible_session.player_characters[entity_id].name
    if entity_id in visible_session.npcs:
        return visible_session.npcs[entity_id].name
    combat_state = visible_session.combat_state
    if combat_state is not None and entity_id in combat_state.combatants:
        return combat_state.combatants[entity_id].name
    return entity_id


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










def _warnings_from_model_traces(traces: list[ModelTraceRecord]) -> list[ServiceWarning]:
    warnings: list[ServiceWarning] = []
    for trace in traces:
        if not trace.fallback_triggered and not trace.degraded:
            continue
        message = trace.notes[0] if trace.notes else trace.outcome.replace('_', ' ')
        code = ServiceWarningCode.MODEL_UNAVAILABLE if trace.degraded else ServiceWarningCode.GENERATION_FALLBACK_USED
        warnings.append(
            ServiceWarning(
                code=code,
                message=message,
                degraded=trace.degraded,
            )
        )
    return warnings






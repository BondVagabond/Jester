from __future__ import annotations

from jester.ai import ModelRole, ModelSelectionPolicy, ModelTraceRecord, RolePromptModelClient
from jester.ai.base import ModelError
from jester.app.orchestration.contracts import (
    GenerationRequest,
    GenerationResponse,
    ServiceWarning,
    ServiceWarningCode,
)
from jester.app.prompting import PromptGenerationError, PromptModelClient, generate_prompt_block
from jester.validation import OutputValidationPolicy


class WorkspacePromptAssembler:
    def __init__(
        self,
        *,
        selection_policy: ModelSelectionPolicy | None = None,
        legacy_model_client: PromptModelClient | None = None,
        policy: OutputValidationPolicy | None = None,
    ) -> None:
        self._selection_policy = selection_policy
        self._legacy_model_client = legacy_model_client
        self._policy = policy

    def generate(
        self,
        request: GenerationRequest,
        *,
        trace_sink: list[ModelTraceRecord],
    ) -> GenerationResponse:
        warnings: list[ServiceWarning] = []
        model_client = self._legacy_model_client
        role = request.route.model_role or ModelRole.PRIMARY_GENERATION
        selection_warning: str | None = None

        if request.route.model_role is not None and self._selection_policy is not None:
            selected = self._selection_policy.optional(request.route.model_role)
            if selected is None:
                selection = self._selection_policy.resolve(request.route.model_role)
                selection_warning = selection.warning or f'Model role {request.route.model_role.value} is unavailable.'
                warnings.append(
                    ServiceWarning(
                        code=ServiceWarningCode.MODEL_UNAVAILABLE,
                        message=selection_warning,
                        degraded=True,
                    )
                )
                trace_sink.append(
                    ModelTraceRecord(
                        role=role,
                        prompt_name=request.route.prompt_name,
                        prompt_version=request.route.prompt_version,
                        fallback_triggered=True,
                        degraded=True,
                        outcome='model_unavailable_fallback',
                        notes=[selection_warning],
                    )
                )
                model_client = None
            else:
                model_client = RolePromptModelClient(
                    selected,
                    role=request.route.model_role,
                    trace_sink=trace_sink,
                )

        if request.route.prompt_name is None or request.route.prompt_version is None:
            raise ValueError('Prompt generation requires a prompt_name and prompt_version route.')

        try:
            block = generate_prompt_block(
                prompt_name=request.route.prompt_name,
                prompt_version=request.route.prompt_version,
                template_values=request.template_values,
                fallback_text=request.fallback_text,
                model_client=model_client,
                policy=self._policy,
            )
        except ModelError as exc:
            warnings.append(
                ServiceWarning(
                    code=ServiceWarningCode.MODEL_UNAVAILABLE,
                    message=str(exc),
                    degraded=True,
                )
            )
            trace_sink.append(
                ModelTraceRecord(
                    role=role,
                    prompt_name=request.route.prompt_name,
                    prompt_version=request.route.prompt_version,
                    fallback_triggered=True,
                    degraded=True,
                    outcome='model_request_failed',
                    notes=[str(exc)],
                )
            )
            block = generate_prompt_block(
                prompt_name=request.route.prompt_name,
                prompt_version=request.route.prompt_version,
                template_values=request.template_values,
                fallback_text=request.fallback_text,
                model_client=None,
                policy=self._policy,
            )
        except PromptGenerationError:
            raise

        if block.used_fallback:
            warnings.append(
                ServiceWarning(
                    code=ServiceWarningCode.GENERATION_FALLBACK_USED,
                    message=f'Prompt {block.prompt_name}/{block.prompt_version} used validated fallback text.',
                    degraded=False,
                )
            )
        return GenerationResponse(
            route=request.route,
            block=block,
            warnings=warnings,
            traces=[],
        )


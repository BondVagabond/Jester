from __future__ import annotations

from jester.ai.contracts import ModelRequest, ModelRole, ModelTraceRecord
from jester.ai.selection import SelectedModelClient
from jester.app.prompting import PromptModelClient, PromptRenderRequest
from jester.engine.narration import ModelClient as NarrationModelClient
from jester.engine.narration import ModelGenerationRequest


class RolePromptModelClient(PromptModelClient):
    def __init__(
        self,
        selected: SelectedModelClient,
        *,
        role: ModelRole = ModelRole.PRIMARY_GENERATION,
        trace_sink: list[ModelTraceRecord] | None = None,
    ) -> None:
        self._selected = selected
        self._role = role
        self._trace_sink = trace_sink

    def generate(self, request: PromptRenderRequest) -> str:
        response = self._selected.client.generate(
            ModelRequest(
                role=self._role,
                prompt=request.rendered_prompt,
                temperature=0.2,
                max_tokens=512,
                metadata={
                    'prompt_name': request.prompt_name,
                    'prompt_version': request.prompt_version,
                    'template_values': request.template_values,
                    'fallback_text': request.fallback_text,
                },
                prompt_name=request.prompt_name,
                prompt_version=request.prompt_version,
            )
        )
        if self._trace_sink is not None:
            self._trace_sink.append(
                ModelTraceRecord(
                    role=self._role,
                    provider_name=response.provider_name,
                    model_name=response.model_name,
                    prompt_name=request.prompt_name,
                    prompt_version=request.prompt_version,
                    latency_ms=response.latency_ms,
                    outcome='generation_requested',
                )
            )
        return response.content


class RoleNarrationModelClient(NarrationModelClient):
    def __init__(
        self,
        selected: SelectedModelClient,
        *,
        trace_sink: list[ModelTraceRecord] | None = None,
    ) -> None:
        self._selected = selected
        self._trace_sink = trace_sink

    def generate(self, request: ModelGenerationRequest) -> str:
        response = self._selected.client.generate(
            ModelRequest(
                role=ModelRole.PRIMARY_GENERATION,
                prompt=request.rendered_prompt,
                temperature=0.2,
                max_tokens=384,
                metadata={
                    'state_summary': request.state_summary,
                    'action_summary': request.action_summary,
                    'retrieved_context': request.retrieved_context,
                    'fallback_text': request.fallback_text,
                },
                prompt_name=request.prompt_name,
                prompt_version=request.prompt_version,
            )
        )
        if self._trace_sink is not None:
            self._trace_sink.append(
                ModelTraceRecord(
                    role=ModelRole.PRIMARY_GENERATION,
                    provider_name=response.provider_name,
                    model_name=response.model_name,
                    prompt_name=request.prompt_name,
                    prompt_version=request.prompt_version,
                    latency_ms=response.latency_ms,
                    outcome='narration_requested',
                )
            )
        return response.content

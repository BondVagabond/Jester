from __future__ import annotations

from collections.abc import Sequence

from pydantic import ValidationError

from jester.ai.base import ModelError
from jester.ai.contracts import (
    CritiqueArtifact,
    ModelRequest,
    ModelRole,
    ModelTraceRecord,
    PlanArtifact,
    TeachingPlanArtifact,
)
from jester.ai.selection import ModelSelectionPolicy
from jester.processing.sanitizer import sanitize_content
from jester.prompts import load_prompt


class ReasoningService:
    def __init__(self, selector: ModelSelectionPolicy | None = None) -> None:
        self._selector = selector

    def build_prep_plan(
        self,
        *,
        artifact_type: str,
        topic: str,
        goal: str,
        inputs_used: Sequence[str],
        retrieved_context: str,
        trace_sink: list[ModelTraceRecord] | None = None,
    ) -> PlanArtifact:
        fallback = PlanArtifact(
            objective=f'Produce a reusable {artifact_type.lower().replace("_", " ")} for {goal}.',
            assumptions=[
                f'Topic focus: {topic}.',
                'The artifact must stay inside retrieved lore and structured constraints.',
            ],
            steps=[
                'Anchor the output to the requested topic.',
                'Add one actionable table-facing detail.',
                'Keep the artifact concise and easy to edit.',
            ],
            success_criteria=[
                'The artifact stays aligned to the requested goal.',
                'The artifact is immediately usable by a DM.',
            ],
        )
        if self._selector is None:
            _append_reasoning_trace(
                trace_sink,
                outcome='plan_fallback',
                fallback_triggered=True,
                degraded=True,
                notes=['No selection policy is configured.'],
            )
            return fallback

        selected = self._selector.optional(ModelRole.REASONING)
        if selected is None:
            _append_reasoning_trace(
                trace_sink,
                outcome='plan_fallback',
                fallback_triggered=True,
                degraded=True,
                notes=[self._selector.resolve(ModelRole.REASONING).warning or 'Reasoning model unavailable.'],
            )
            return fallback

        prompt_name = 'prep_plan'
        prompt_version = 'v1'
        rendered_prompt = load_prompt(prompt_name, prompt_version).template.format(
            artifact_type=artifact_type,
            topic=topic,
            goal=goal,
            inputs_used=' | '.join(inputs_used),
            retrieved_context=retrieved_context,
        )
        try:
            response = selected.client.generate(
                ModelRequest(
                    role=ModelRole.REASONING,
                    prompt=rendered_prompt,
                    temperature=0.0,
                    max_tokens=256,
                    metadata={
                        'artifact_type': artifact_type,
                        'topic': topic,
                        'goal': goal,
                        'objective': fallback.objective,
                        'inputs_used': list(inputs_used),
                    },
                    prompt_name=prompt_name,
                    prompt_version=prompt_version,
                )
            )
        except ModelError as exc:
            _append_reasoning_trace(
                trace_sink,
                prompt_name=prompt_name,
                prompt_version=prompt_version,
                fallback_triggered=True,
                degraded=True,
                outcome='plan_model_failed',
                notes=[str(exc)],
            )
            return fallback
        try:
            artifact = PlanArtifact.model_validate_json(response.content)
        except ValidationError as exc:
            _append_reasoning_trace(
                trace_sink,
                provider_name=response.provider_name,
                model_name=response.model_name,
                prompt_name=prompt_name,
                prompt_version=prompt_version,
                latency_ms=response.latency_ms,
                validation_passed=False,
                fallback_triggered=True,
                degraded=False,
                outcome='plan_invalid',
                notes=[str(exc)],
            )
            return fallback

        _append_reasoning_trace(
            trace_sink,
            provider_name=response.provider_name,
            model_name=response.model_name,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            latency_ms=response.latency_ms,
            validation_passed=True,
            fallback_triggered=False,
            degraded=False,
            outcome='plan_generated',
        )
        return artifact

    def critique_prep_output(
        self,
        *,
        artifact_type: str,
        topic: str,
        goal: str,
        draft_text: str,
        trace_sink: list[ModelTraceRecord] | None = None,
    ) -> CritiqueArtifact:
        fallback = _fallback_prep_critique(topic=topic, goal=goal, draft_text=draft_text)
        if self._selector is None:
            _append_reasoning_trace(
                trace_sink,
                outcome='critique_fallback',
                fallback_triggered=True,
                degraded=True,
                notes=['No selection policy is configured.'],
            )
            return fallback

        selected = self._selector.optional(ModelRole.REASONING)
        if selected is None:
            _append_reasoning_trace(
                trace_sink,
                outcome='critique_fallback',
                fallback_triggered=True,
                degraded=True,
                notes=[self._selector.resolve(ModelRole.REASONING).warning or 'Reasoning model unavailable.'],
            )
            return fallback

        prompt_name = 'prep_critique'
        prompt_version = 'v1'
        rendered_prompt = load_prompt(prompt_name, prompt_version).template.format(
            artifact_type=artifact_type,
            topic=topic,
            goal=goal,
            draft_text=draft_text,
        )
        try:
            response = selected.client.generate(
                ModelRequest(
                    role=ModelRole.REASONING,
                    prompt=rendered_prompt,
                    temperature=0.0,
                    max_tokens=256,
                    metadata={
                        'artifact_type': artifact_type,
                        'topic': topic,
                        'goal': goal,
                        'draft_text': draft_text,
                    },
                    prompt_name=prompt_name,
                    prompt_version=prompt_version,
                )
            )
        except ModelError as exc:
            _append_reasoning_trace(
                trace_sink,
                prompt_name=prompt_name,
                prompt_version=prompt_version,
                fallback_triggered=True,
                degraded=True,
                outcome='critique_model_failed',
                notes=[str(exc)],
            )
            return fallback
        try:
            artifact = CritiqueArtifact.model_validate_json(response.content)
        except ValidationError as exc:
            _append_reasoning_trace(
                trace_sink,
                provider_name=response.provider_name,
                model_name=response.model_name,
                prompt_name=prompt_name,
                prompt_version=prompt_version,
                latency_ms=response.latency_ms,
                validation_passed=False,
                fallback_triggered=True,
                degraded=False,
                outcome='critique_invalid',
                notes=[str(exc)],
            )
            return fallback

        _append_reasoning_trace(
            trace_sink,
            provider_name=response.provider_name,
            model_name=response.model_name,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            latency_ms=response.latency_ms,
            validation_passed=True,
            fallback_triggered=bool(artifact.violations),
            degraded=False,
            outcome='critique_generated',
        )
        return artifact

    def build_teaching_plan(
        self,
        *,
        concept: str,
        depth: str,
        prerequisites: Sequence[str],
        misconceptions: Sequence[str],
        trace_sink: list[ModelTraceRecord] | None = None,
    ) -> TeachingPlanArtifact:
        fallback = TeachingPlanArtifact(
            concept=concept,
            depth=depth,
            prerequisites=list(prerequisites),
            learning_objectives=[
                f'Explain {concept.lower().replace("_", " ")} in concise, table-usable terms.',
                'Show the mechanical order of operations clearly.',
            ],
            explanation_sections=[
                'Purpose',
                'Resolution steps',
                'Worked example',
            ],
            misconception_focus=list(misconceptions),
        )
        if self._selector is None:
            _append_reasoning_trace(
                trace_sink,
                outcome='teaching_plan_fallback',
                fallback_triggered=True,
                degraded=True,
                notes=['No selection policy is configured.'],
            )
            return fallback

        selected = self._selector.optional(ModelRole.REASONING)
        if selected is None:
            _append_reasoning_trace(
                trace_sink,
                outcome='teaching_plan_fallback',
                fallback_triggered=True,
                degraded=True,
                notes=[self._selector.resolve(ModelRole.REASONING).warning or 'Reasoning model unavailable.'],
            )
            return fallback

        prompt_name = 'teaching_structure'
        prompt_version = 'v1'
        rendered_prompt = load_prompt(prompt_name, prompt_version).template.format(
            concept=concept,
            depth=depth,
            prerequisites=' | '.join(prerequisites) or 'None',
            misconceptions=' | '.join(misconceptions) or 'None',
        )
        try:
            response = selected.client.generate(
                ModelRequest(
                    role=ModelRole.REASONING,
                    prompt=rendered_prompt,
                    temperature=0.0,
                    max_tokens=256,
                    metadata={
                        'concept': concept,
                        'depth': depth,
                        'prerequisites': list(prerequisites),
                        'misconceptions': list(misconceptions),
                    },
                    prompt_name=prompt_name,
                    prompt_version=prompt_version,
                )
            )
        except ModelError as exc:
            _append_reasoning_trace(
                trace_sink,
                prompt_name=prompt_name,
                prompt_version=prompt_version,
                fallback_triggered=True,
                degraded=True,
                outcome='teaching_plan_model_failed',
                notes=[str(exc)],
            )
            return fallback
        try:
            artifact = TeachingPlanArtifact.model_validate_json(response.content)
        except ValidationError as exc:
            _append_reasoning_trace(
                trace_sink,
                provider_name=response.provider_name,
                model_name=response.model_name,
                prompt_name=prompt_name,
                prompt_version=prompt_version,
                latency_ms=response.latency_ms,
                validation_passed=False,
                fallback_triggered=True,
                degraded=False,
                outcome='teaching_plan_invalid',
                notes=[str(exc)],
            )
            return fallback

        _append_reasoning_trace(
            trace_sink,
            provider_name=response.provider_name,
            model_name=response.model_name,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            latency_ms=response.latency_ms,
            validation_passed=True,
            fallback_triggered=False,
            degraded=False,
            outcome='teaching_plan_generated',
        )
        return artifact


def _fallback_prep_critique(*, topic: str, goal: str, draft_text: str) -> CritiqueArtifact:
    normalized = sanitize_content(draft_text).lower()
    violations: list[str] = []
    instructions: list[str] = []
    if topic.lower() not in normalized:
        violations.append('The draft does not clearly identify the requested topic.')
        instructions.append(f'Make {topic} explicit in the artifact body.')
    if goal.lower() not in normalized:
        violations.append('The draft does not explicitly connect itself to the requested goal.')
        instructions.append(f'Tie the artifact directly to {goal}.')
    if len(draft_text.split()) < 14:
        violations.append('The draft is too sparse to reuse without further editing.')
        instructions.append('Add one specific scene detail and one concrete decision point.')

    weaknesses = ['The current draft may need stronger table-facing specificity.']
    strengths = ['The output stays inside the declared artifact scope.']
    return CritiqueArtifact(
        strengths=strengths,
        weaknesses=weaknesses,
        violations=violations,
        revision_instructions=instructions,
    )


def _append_reasoning_trace(
    trace_sink: list[ModelTraceRecord] | None,
    *,
    outcome: str,
    provider_name: str | None = None,
    model_name: str | None = None,
    prompt_name: str | None = None,
    prompt_version: str | None = None,
    latency_ms: int | None = None,
    validation_passed: bool | None = None,
    fallback_triggered: bool,
    degraded: bool,
    notes: list[str] | None = None,
) -> None:
    if trace_sink is None:
        return
    trace_sink.append(
        ModelTraceRecord(
            role=ModelRole.REASONING,
            provider_name=provider_name,
            model_name=model_name,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            latency_ms=latency_ms,
            validation_passed=validation_passed,
            fallback_triggered=fallback_triggered,
            degraded=degraded,
            outcome=outcome,
            notes=notes or [],
        )
    )

from __future__ import annotations

from pydantic import Field

from jester.ai.contracts import ModelTraceRecord, TeachingPlanArtifact
from jester.app.contracts.common import (
    AppDto,
    GeneratedTextBlock,
    ProvenanceReference,
    TeachingConcept,
    TeachingDepth,
)


class TeachingRequest(AppDto):
    request_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    concept: TeachingConcept | None = None
    depth: TeachingDepth | None = None
    include_practice: bool = True


class RulesConceptExplanation(AppDto):
    concept: TeachingConcept
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    prerequisites: list[TeachingConcept] = Field(default_factory=list)
    key_points: list[str] = Field(default_factory=list)
    worked_example: list[str] = Field(default_factory=list)


class MisconceptionHint(AppDto):
    misconception: str = Field(min_length=1)
    correction: str = Field(min_length=1)
    why_it_matters: str = Field(min_length=1)


class QuizItem(AppDto):
    question: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    explanation: str = Field(min_length=1)


class PracticeScenario(AppDto):
    title: str = Field(min_length=1)
    setup: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    expected_steps: list[str] = Field(default_factory=list)
    sample_resolution: list[str] = Field(default_factory=list)
    prose: GeneratedTextBlock | None = None


class LessonResponse(AppDto):
    question: str = Field(min_length=1)
    concept: TeachingConcept
    depth: TeachingDepth
    explanation: RulesConceptExplanation
    misconceptions: list[MisconceptionHint] = Field(default_factory=list)
    practice_scenario: PracticeScenario | None = None
    quiz_items: list[QuizItem] = Field(default_factory=list)
    provenance: list[ProvenanceReference] = Field(default_factory=list)
    prose: GeneratedTextBlock | None = None
    teaching_plan: TeachingPlanArtifact | None = None
    model_traces: list[ModelTraceRecord] = Field(default_factory=list)


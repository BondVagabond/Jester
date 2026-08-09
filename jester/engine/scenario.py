from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from jester.domain import ActionIntent, ActionResult, Session
from jester.engine.pipeline import process_player_action


class ScenarioStep(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    actor_id: str = Field(min_length=1)
    intent: ActionIntent


class ScenarioRunResult(BaseModel):
    model_config = ConfigDict(extra='forbid')

    results: list[ActionResult] = Field(default_factory=list)
    final_session: Session


class DeterministicScenarioEngine:
    def run(self, session: Session, steps: list[ScenarioStep]) -> ScenarioRunResult:
        working = session.model_copy(deep=True)
        results: list[ActionResult] = []
        for step in steps:
            results.append(process_player_action(working, step.actor_id, step.intent))
        return ScenarioRunResult(results=results, final_session=working)

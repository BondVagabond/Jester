from __future__ import annotations

import hashlib

from pydantic import BaseModel, ConfigDict, Field

from jester.domain import DiceExpression


class DiceRollOutcome(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    expression: DiceExpression
    individual_rolls: list[int] = Field(default_factory=list)
    total: int


class DeterministicDiceRoller:
    @staticmethod
    def roll(expression: DiceExpression, *, seed: int, namespace: str) -> DiceRollOutcome:
        rolls: list[int] = []
        total = expression.modifier
        for index in range(expression.count):
            digest = hashlib.sha256(f'{seed}:{namespace}:{index}'.encode()).digest()
            roll_value = int.from_bytes(digest[:8], byteorder='big') % expression.sides + 1
            rolls.append(roll_value)
            total += roll_value
        return DiceRollOutcome(expression=expression, individual_rolls=rolls, total=total)

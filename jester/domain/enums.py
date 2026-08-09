from enum import StrEnum


class MemoryScope(StrEnum):
    PUBLIC = "PUBLIC"
    PARTY = "PARTY"
    PLAYER_PRIVATE = "PLAYER_PRIVATE"
    DM_PRIVATE = "DM_PRIVATE"


class ConditionType(StrEnum):
    PRONE = "PRONE"
    UNCONSCIOUS = "UNCONSCIOUS"


class ActionType(StrEnum):
    ATTACK = "ATTACK"
    MOVE = "MOVE"
    END_TURN = "END_TURN"


class ActionStatus(StrEnum):
    APPLIED = "APPLIED"
    REJECTED = "REJECTED"

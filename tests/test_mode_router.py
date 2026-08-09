from __future__ import annotations

import pytest

from jester.ai import (
    ModelRegistry,
    ModelRole,
    ModelRoleBinding,
    ModelSelectionPolicy,
    ScriptedModelClient,
    SmallFastClassifier,
)
from jester.app.contracts import Mode
from jester.app.router import ModeRoutingError, UserRequestContext, route_request


def test_route_request_classifies_dm_prep() -> None:
    decision = route_request(
        UserRequestContext(request_text='Build a goblin ambush encounter for my next session.')
    )

    assert decision.mode == Mode.DM_PREP
    assert decision.subtask == 'encounter_outline'
    assert decision.confidence >= 0.8


def test_route_request_classifies_teaching() -> None:
    decision = route_request(
        UserRequestContext(request_text='Explain how initiative works for a new player.')
    )

    assert decision.mode == Mode.PLAYER_TEACHING
    assert decision.subtask == 'concept_explanation'


def test_route_request_classifies_live_dm_action() -> None:
    decision = route_request(
        UserRequestContext(
            request_text='I attack the goblin lookout.',
            session_id='session-1',
            viewer_id='player-1',
        )
    )

    assert decision.mode == Mode.LIVE_DM
    assert decision.subtask == 'mechanical_action'


def test_route_request_uses_small_fast_classifier_to_break_ties() -> None:
    registry = ModelRegistry.from_bindings(
        {
            ModelRole.SMALL_FAST: ModelRoleBinding(
                provider_name='fake',
                model_name='router-test',
            )
        },
        clients={
            ModelRole.SMALL_FAST: ScriptedModelClient(
                role=ModelRole.SMALL_FAST,
                model_name='router-test',
                responder=lambda request: (
                    '{"mode":"PLAYER_TEACHING","subtask":"concept_explanation",'
                    '"confidence":0.88,"rationale":"Classifier favored teaching language."}'
                ),
            )
        },
    )
    classifier = SmallFastClassifier(ModelSelectionPolicy(registry))

    decision = route_request(
        UserRequestContext(request_text='Build and explain initiative for my table.'),
        classifier=classifier,
    )

    assert decision.mode == Mode.PLAYER_TEACHING
    assert decision.model_traces
    assert any(trace.role == ModelRole.SMALL_FAST for trace in decision.model_traces)


def test_route_request_fails_loudly_for_ambiguous_input() -> None:
    with pytest.raises(ModeRoutingError):
        route_request(UserRequestContext(request_text='Help me with D&D.'))

from __future__ import annotations

from jester.app.visibility import build_visible_session_view
from jester.domain import ActionIntent, ActionType
from jester.engine import build_narration, initialize_combat, process_player_action
from jester.engine.narration import ModelGenerationRequest, NarrationRequest
from tests.runtime_factory import build_session


class UnsafeNarrationModel:
    def generate(self, request: ModelGenerationRequest) -> str:
        del request
        return 'Please read manifest.jsonl before the scene continues.'


def test_narration_validation_failure_triggers_safe_fallback() -> None:
    session = build_session()
    initialize_combat(session, ['pc-1', 'pc-2', 'npc-1'])
    action_result = process_player_action(
        session,
        'pc-1',
        ActionIntent(
            intent_id='attack-unsafe',
            action_type=ActionType.ATTACK,
            target_id='npc-1',
        ),
    )
    visible_state = build_visible_session_view(session, 'player-1')

    response = build_narration(
        NarrationRequest(
            state_snapshot=visible_state.model_dump(mode='json'),
            action_result=action_result,
            prompt_name='live_dm_narration',
            prompt_version='v1',
        ),
        model_client=UnsafeNarrationModel(),
    )

    assert response.used_fallback is True
    assert 'manifest.jsonl' not in response.text.lower()
    assert any(issue.code == 'filename_leakage' for issue in response.issues)
from __future__ import annotations

from jester.ai.contracts import ModelRole
from jester.app.contracts import PrepArtifactType, TeachingConcept
from jester.app.orchestration.contracts import (
    OrchestrationLane,
    RouteSelection,
    WorkspaceName,
    WorkspaceTask,
)


class WorkspaceRoutingPolicy:
    @staticmethod
    def prep_retrieval() -> RouteSelection:
        return RouteSelection(
            workspace=WorkspaceName.PREP,
            task=WorkspaceTask.PREP_RETRIEVAL,
            lane=OrchestrationLane.DETERMINISTIC,
            corpus_id='world',
            retrieval_top_k=3,
            deterministic=True,
        )

    @staticmethod
    def prep_plan() -> RouteSelection:
        return RouteSelection(
            workspace=WorkspaceName.PREP,
            task=WorkspaceTask.PREP_PLAN,
            lane=OrchestrationLane.ARBITER,
            model_role=ModelRole.REASONING,
            prompt_name='prep_plan',
            prompt_version='v1',
        )

    @staticmethod
    def prep_prose(artifact_type: PrepArtifactType) -> RouteSelection:
        prompt_name = {
            PrepArtifactType.NPC_BRIEF: 'prep_npc',
            PrepArtifactType.TOWN_BRIEF: 'prep_town',
            PrepArtifactType.ENCOUNTER_OUTLINE: 'prep_encounter',
            PrepArtifactType.QUEST_HOOK: 'prep_quest_hook',
            PrepArtifactType.SESSION_PREP_PACKET: 'prep_session_packet',
        }[artifact_type]
        return RouteSelection(
            workspace=WorkspaceName.PREP,
            task=WorkspaceTask.PREP_PROSE,
            lane=OrchestrationLane.NARRATOR,
            model_role=ModelRole.PRIMARY_GENERATION,
            prompt_name=prompt_name,
            prompt_version='v1',
            corpus_id='world',
            retrieval_top_k=3,
        )

    @staticmethod
    def prep_critique() -> RouteSelection:
        return RouteSelection(
            workspace=WorkspaceName.PREP,
            task=WorkspaceTask.PREP_CRITIQUE,
            lane=OrchestrationLane.ARBITER,
            model_role=ModelRole.REASONING,
            prompt_name='prep_critique',
            prompt_version='v1',
        )

    @staticmethod
    def prep_refine() -> RouteSelection:
        return RouteSelection(
            workspace=WorkspaceName.PREP,
            task=WorkspaceTask.PREP_REFINE,
            lane=OrchestrationLane.NARRATOR,
            model_role=ModelRole.PRIMARY_GENERATION,
            prompt_name='prep_refine',
            prompt_version='v1',
            corpus_id='world',
            retrieval_top_k=3,
        )

    @staticmethod
    def teaching_retrieval() -> RouteSelection:
        return RouteSelection(
            workspace=WorkspaceName.TEACHING,
            task=WorkspaceTask.TEACHING_RETRIEVAL,
            lane=OrchestrationLane.DETERMINISTIC,
            corpus_id='rules',
            retrieval_top_k=3,
            deterministic=True,
        )

    @staticmethod
    def teaching_plan() -> RouteSelection:
        return RouteSelection(
            workspace=WorkspaceName.TEACHING,
            task=WorkspaceTask.TEACHING_PLAN,
            lane=OrchestrationLane.ARBITER,
            model_role=ModelRole.REASONING,
            prompt_name='teaching_structure',
            prompt_version='v1',
        )

    @staticmethod
    def teaching_answer() -> RouteSelection:
        return RouteSelection(
            workspace=WorkspaceName.TEACHING,
            task=WorkspaceTask.TEACHING_ANSWER,
            lane=OrchestrationLane.ARBITER,
            model_role=ModelRole.REASONING,
            prompt_name='teaching_explain_concept',
            prompt_version='v1',
            corpus_id='rules',
            retrieval_top_k=3,
        )

    @staticmethod
    def teaching_practice() -> RouteSelection:
        return RouteSelection(
            workspace=WorkspaceName.TEACHING,
            task=WorkspaceTask.TEACHING_PRACTICE,
            lane=OrchestrationLane.ARBITER,
            model_role=ModelRole.REASONING,
            prompt_name='teaching_practice_scenario',
            prompt_version='v1',
            corpus_id='rules',
            retrieval_top_k=2,
        )

    @staticmethod
    def live_dm_classification() -> RouteSelection:
        return RouteSelection(
            workspace=WorkspaceName.LIVE_DM,
            task=WorkspaceTask.LIVE_DM_CLASSIFICATION,
            lane=OrchestrationLane.CLASSIFIER,
            model_role=ModelRole.SMALL_FAST,
            prompt_name='routing_live_dm_intent',
            prompt_version='v1',
        )

    @staticmethod
    def live_dm_info() -> RouteSelection:
        return RouteSelection(
            workspace=WorkspaceName.LIVE_DM,
            task=WorkspaceTask.LIVE_DM_INFO,
            lane=OrchestrationLane.NARRATOR,
            model_role=ModelRole.PRIMARY_GENERATION,
            prompt_name='live_dm_info_response',
            prompt_version='v1',
            corpus_id='world',
            retrieval_top_k=2,
        )

    @staticmethod
    def live_dm_rules_explanation() -> RouteSelection:
        return RouteSelection(
            workspace=WorkspaceName.LIVE_DM,
            task=WorkspaceTask.LIVE_DM_RULES_EXPLANATION,
            lane=OrchestrationLane.ARBITER,
            model_role=ModelRole.REASONING,
            prompt_name='live_dm_rules_explanation',
            prompt_version='v1',
            corpus_id='rules',
            retrieval_top_k=2,
        )

    @staticmethod
    def live_dm_narration() -> RouteSelection:
        return RouteSelection(
            workspace=WorkspaceName.LIVE_DM,
            task=WorkspaceTask.LIVE_DM_NARRATION,
            lane=OrchestrationLane.NARRATOR,
            model_role=ModelRole.PRIMARY_GENERATION,
            prompt_name='live_dm_narration',
            prompt_version='v1',
            corpus_id='world',
            retrieval_top_k=2,
        )

    @staticmethod
    def live_dm_mechanics() -> RouteSelection:
        return RouteSelection(
            workspace=WorkspaceName.LIVE_DM,
            task=WorkspaceTask.LIVE_DM_MECHANICS,
            lane=OrchestrationLane.DETERMINISTIC,
            deterministic=True,
        )

    @staticmethod
    def teaching_query_text(question: str, concept: TeachingConcept) -> str:
        return f'{question} {concept.value}'



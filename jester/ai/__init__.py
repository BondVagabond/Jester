"""Provider-agnostic model role orchestration for Jester."""

from jester.ai.adapters import RoleNarrationModelClient, RolePromptModelClient
from jester.ai.base import (
    FakeModelClient,
    ModelClient,
    ModelError,
    ModelRoleUnavailableError,
    ScriptedModelClient,
)
from jester.ai.classification import (
    IntentClassificationArtifact,
    ModeRoutingArtifact,
    SmallFastClassifier,
    TeachingDepthArtifact,
)
from jester.ai.contracts import (
    CritiqueArtifact,
    ModelRequest,
    ModelResponse,
    ModelRole,
    ModelRoleBinding,
    ModelSelection,
    ModelTraceRecord,
    PlanArtifact,
    TeachingPlanArtifact,
)
from jester.ai.providers import (
    AIProvider,
    OllamaChatClient,
    OllamaProvider,
    OpenAIChatCompletionsClient,
    OpenAIProvider,
    ProviderConfigurationError,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderTimeoutError,
    build_model_registry,
)
from jester.ai.reasoning import ReasoningService
from jester.ai.registry import ModelRegistry
from jester.ai.selection import ModelSelectionPolicy, SelectedModelClient

__all__ = [
    'AIProvider',
    'CritiqueArtifact',
    'FakeModelClient',
    'IntentClassificationArtifact',
    'ModeRoutingArtifact',
    'ModelClient',
    'ModelError',
    'ModelRegistry',
    'ModelRequest',
    'ModelResponse',
    'ModelRole',
    'ModelRoleBinding',
    'ModelRoleUnavailableError',
    'ModelSelection',
    'ModelSelectionPolicy',
    'ModelTraceRecord',
    'OllamaChatClient',
    'OllamaProvider',
    'OpenAIChatCompletionsClient',
    'OpenAIProvider',
    'PlanArtifact',
    'ProviderConfigurationError',
    'ProviderRateLimitError',
    'ProviderRequestError',
    'ProviderTimeoutError',
    'ReasoningService',
    'RoleNarrationModelClient',
    'RolePromptModelClient',
    'ScriptedModelClient',
    'SelectedModelClient',
    'SmallFastClassifier',
    'TeachingDepthArtifact',
    'TeachingPlanArtifact',
    'build_model_registry',
]

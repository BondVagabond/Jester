from __future__ import annotations

from dataclasses import dataclass

from jester.ai.base import ModelClient, ModelRoleUnavailableError
from jester.ai.contracts import ModelRole, ModelSelection
from jester.ai.registry import ModelRegistry


@dataclass(frozen=True, slots=True)
class SelectedModelClient:
    selection: ModelSelection
    client: ModelClient


class ModelSelectionPolicy:
    def __init__(self, registry: ModelRegistry | None = None) -> None:
        self._registry = registry

    def resolve(self, role: ModelRole) -> ModelSelection:
        if self._registry is None:
            return ModelSelection(
                role=role,
                configured=False,
                enabled=False,
                available=False,
                degraded=True,
                warning='No model registry is configured.',
            )

        binding = self._registry.binding_for(role)
        if binding is None:
            return ModelSelection(
                role=role,
                configured=False,
                enabled=False,
                available=False,
                degraded=True,
                warning=f'No binding is configured for role {role.value}.',
            )

        if not binding.enabled:
            return ModelSelection(
                role=role,
                configured=True,
                enabled=False,
                available=False,
                provider_name=binding.provider_name,
                model_name=binding.model_name,
                degraded=True,
                warning=f'Model role {role.value} is disabled by configuration.',
            )

        client = self._registry.client_for(role)
        if client is None:
            return ModelSelection(
                role=role,
                configured=True,
                enabled=True,
                available=False,
                provider_name=binding.provider_name,
                model_name=binding.model_name,
                degraded=True,
                warning=f'Model role {role.value} is configured but no client is registered.',
            )

        return ModelSelection(
            role=role,
            configured=True,
            enabled=True,
            available=True,
            provider_name=binding.provider_name,
            model_name=binding.model_name,
            degraded=False,
        )

    def optional(self, role: ModelRole) -> SelectedModelClient | None:
        selection = self.resolve(role)
        if not selection.available or self._registry is None:
            return None
        client = self._registry.client_for(role)
        if client is None:
            return None
        return SelectedModelClient(selection=selection, client=client)

    def require(self, role: ModelRole) -> SelectedModelClient:
        selected = self.optional(role)
        if selected is None:
            warning = self.resolve(role).warning or f'Model role {role.value} is unavailable.'
            raise ModelRoleUnavailableError(warning)
        return selected

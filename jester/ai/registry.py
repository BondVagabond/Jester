from __future__ import annotations

from collections.abc import Mapping

from jester.ai.base import FakeModelClient, ModelClient
from jester.ai.contracts import ModelRole, ModelRoleBinding


class ModelRegistry:
    def __init__(
        self,
        *,
        bindings: Mapping[ModelRole, ModelRoleBinding] | None = None,
        clients: Mapping[ModelRole, ModelClient] | None = None,
    ) -> None:
        self._bindings: dict[ModelRole, ModelRoleBinding] = dict(bindings or {})
        self._clients: dict[ModelRole, ModelClient] = {}

        for role, client in dict(clients or {}).items():
            self.register_client(role, client)

        for role, binding in self._bindings.items():
            if role in self._clients or not binding.enabled:
                continue
            if binding.provider_name.lower() == 'fake':
                self._clients[role] = FakeModelClient(
                    role=role,
                    provider_name=binding.provider_name,
                    model_name=binding.model_name,
                )

    @classmethod
    def from_bindings(
        cls,
        bindings: Mapping[ModelRole, ModelRoleBinding],
        *,
        clients: Mapping[ModelRole, ModelClient] | None = None,
    ) -> ModelRegistry:
        return cls(bindings=bindings, clients=clients)

    def register_binding(self, role: ModelRole, binding: ModelRoleBinding) -> None:
        self._bindings[role] = binding
        if role not in self._clients and binding.enabled and binding.provider_name.lower() == 'fake':
            self._clients[role] = FakeModelClient(
                role=role,
                provider_name=binding.provider_name,
                model_name=binding.model_name,
            )

    def register_client(self, role: ModelRole, client: ModelClient) -> None:
        self._clients[role] = client

    def binding_for(self, role: ModelRole) -> ModelRoleBinding | None:
        return self._bindings.get(role)

    def client_for(self, role: ModelRole) -> ModelClient | None:
        return self._clients.get(role)

    def bindings(self) -> dict[ModelRole, ModelRoleBinding]:
        return dict(self._bindings)

# Model Input Contracts

## Goal

The backend should call the future local runtime through a stable provider-neutral request envelope. The backend assembles context and constraints before invoking the runtime.

## Generic request envelope

```json
{
  "task_family": "teaching",
  "role": "arbiter",
  "instruction": "Explain opportunity attacks simply.",
  "context": {
    "retrieved_facts": [
      {
        "context_id": "rule-12",
        "text": "A creature provokes an opportunity attack when it leaves your reach."
      }
    ],
    "session_state": {},
    "tone": "beginner_friendly"
  },
  "constraints": {
    "max_tokens": 400,
    "must_cite_context": true,
    "structured_output": false
  },
  "request_id": "req-0001",
  "contract_version": "1.0"
}
```

## Required fields

- `task_family`: one of `narration`, `teaching`, `reasoning`, `routing`
- `role`: one of `narrator`, `arbiter`, `router`
- `instruction`: the backend-approved user or system ask after validation and prompt assembly
- `context`: normalized context block supplied by the backend
- `constraints`: hard limits and safety requirements
- `request_id`: backend trace identifier
- `contract_version`: runtime contract version

## Context rules

- Retrieval is assembled by the backend, not by the model runtime.
- Context items should carry stable IDs when later citations are required.
- Session state should only include data already cleared for model exposure.

## Constraint rules

- `must_cite_context=true` is mandatory for reasoning-heavy tasks.
- `structured_output=true` means the backend expects a machine-validated shape and may reject plain prose.
- `max_tokens` is a ceiling, not a suggestion.

## Runtime rule

The runtime may adapt this envelope to a provider-specific prompt format, but it must preserve the backend's task family, role, context IDs, and hard constraints.

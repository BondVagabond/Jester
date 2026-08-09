# Model Output Contracts

## Goal

The local runtime must return a normalized response envelope that the backend can validate without knowing provider-specific details.

## Generic response envelope

```json
{
  "answer": "An opportunity attack happens when a creature leaves your reach...",
  "confidence": 0.83,
  "used_context_ids": ["rule-12"],
  "warnings": [],
  "task_family": "teaching",
  "role": "arbiter",
  "provider": {
    "runtime": "ollama",
    "model_name": "future-arbiter-model"
  },
  "latency_ms": 182,
  "request_id": "req-0001",
  "contract_version": "1.0"
}
```

## Required fields

- `answer`: primary text output or serialized structured payload
- `task_family`
- `role`
- `request_id`
- `contract_version`

## Strongly recommended fields

- `confidence`
- `used_context_ids`
- `warnings`
- `provider.runtime`
- `provider.model_name`
- `latency_ms`

## Task-specific rules

- `reasoning` outputs should include `used_context_ids` whenever citations were required.
- `routing` outputs may use a structured `answer` object, but the envelope still carries `role`, `task_family`, and trace metadata.
- `narration` outputs may omit context IDs if the request did not require explicit citations.

## Backend validation expectations

The backend may reject or downgrade a response when:

- required fields are missing
- `used_context_ids` references unknown context
- `confidence` is outside the `0.0` to `1.0` range
- the output shape does not match a structured request
- warnings indicate the runtime could not honor a hard constraint

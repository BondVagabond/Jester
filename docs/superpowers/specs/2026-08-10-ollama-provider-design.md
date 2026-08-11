# Ollama Local Model Provider — Design

**Date:** 2026-08-10
**Status:** Approved, pending implementation plan
**Context:** Spike to de-risk the offline desktop profile before Wave R1 remediation.

## Problem

Jester's shipped configuration binds all three model roles to `FakeModelClient`, which returns the
caller's own fallback string and is labelled `used_fallback=False, validation_passed=True`
(audit findings CQ-002, RC-1). Nobody knows whether a locally-served model produces DM-quality output,
and that unknown gates the entire offline desktop profile.

`docs/training_platform_sprint1.md` already commits to a local-first strategy: three role models —
`Narrator` (prose), `Arbiter` (rules reasoning and teaching), `Router` (small-fast classification) —
served through "a provider-neutral request and response envelope." The provider seam exists
(`jester/ai/providers.py`, `AIProvider` protocol). No local provider implements it.

## Goal

Answer, with evidence on this hardware: **can a locally-served model do each of the three roles well
enough to build the offline product on?** Produce a per-role go/no-go rather than an overall verdict.

Secondary goal: leave behind a real, tested provider if the answer is yes.

## Decisions

| # | Decision | Choice |
|---|---|---|
| 1 | Runtime | Ollama — retained. Local is now a product requirement, not a cost tactic |
| 2 | Integration | Native `/api/chat` client, additive only. Not the OpenAI `/v1` compat path |
| 3 | Scope | Real provider, spike-first sequencing |
| 4 | Judgement | Objective pass-rates and latency, plus prose samples for human reading |
| 5 | Model | `qwen3.5:9b` primary, `qwen3.5:4b` fallback, `mistral:latest` as baseline |
| 6 | Role/model mapping | One model serves all three roles |
| 7 | Mixed-provider guard | Left untouched — that is audit finding D2-17, Wave R5 |

### Why native `/api/chat`, not the OpenAI-compatible endpoint

Ollama serves `/v1/chat/completions`, which would let `OpenAIChatCompletionsClient` talk to it with
almost no new code. Rejected for three reasons:

1. `OpenAIProvider.__init__` (`providers.py:50`) raises without an `api_key`. Reusing it means inventing
   a fake credential to satisfy a real check.
2. Every `ModelResponse` would report `provider_name='openai'` for a locally-served model — a new
   instance of the honesty inversion the audit identified as root cause RC-1.
3. JSON output would route through OpenAI's `response_format: json_object`, whose support on Ollama's
   compat layer is partial and model-dependent. Native `format: "json"` constrains generation at the
   sampler, which is the strongest available lever on the Arbiter role's structured-output risk.

A shared `ChatCompletionsClient` base extracted from both clients is the correct end state, but it
refactors working, tested OpenAI code before the spike has justified it. Deferred.

### Why one model for all three roles

`ModelRoleBinding.model_name` is per role, so per-role models are expressible. With 8 GB VRAM two
resident models do not fit, so Ollama evicts and reloads on every role switch — measured at roughly
15 s per load. A single live-DM turn issues 2–3 calls across roles. One model avoids swap thrash.

## Hardware baseline (measured 2026-08-10)

RTX 3060 Ti, 8 GB VRAM, 20 logical cores. During measurement the GPU was contended by an unrelated
application, leaving 311 MiB free; Ollama logged `offloaded 0/33 layers to GPU` and ran on CPU.

| Condition | Result |
|---|---|
| Cold start, short JSON prompt | 49.9 s total (`load_duration` 15.0 s) |
| Warm, short JSON prompt (21 in / 17 out) | 3.3 s |
| Warm, realistic narration (814 in / 220 out) | **130 s** — prompt eval 7.8 tok/s, generation 8.5 tok/s |
| `num_ctx` 32768 vs 8192 | model footprint 8.9 GB vs 5.6 GB |

These are worst-case CPU-only figures and must not be treated as representative. They yield three
binding design constraints:

1. **`num_ctx` is a first-class setting** — KV cache size determines whether the model fits in VRAM.
2. **Timeouts need a far higher ceiling than OpenAI's** — `OpenAIProviderSettings.timeout_seconds` caps
   at `le=120.0`, which the 130 s call would have failed.
3. **The harness must record GPU placement with every measurement**, or a "too slow" verdict is
   unfalsifiable.

## 1. Settings

New `OllamaProviderSettings`, added beside `openai` in `ProviderSettings`:

| Field | Default | Env var |
|---|---|---|
| `base_url` | `http://127.0.0.1:11434` | `JESTER_OLLAMA_BASE_URL` |
| `timeout_seconds` | `300.0` (ge 1.0, le 1800.0) | `JESTER_OLLAMA_TIMEOUT_SECONDS` |
| `num_ctx` | `None` (server default) | `JESTER_OLLAMA_NUM_CTX` |
| `keep_alive` | `None` | `JESTER_OLLAMA_KEEP_ALIVE` |

No `api_key` field — there is no credential to hold, and adding an unused one would invite the same
fake-value pattern this design rejects. The existing openai-key assertion in
`AppSettings.validate_runtime_guards` stays openai-specific.

## 2. Provider and client

```
OllamaProvider(name='ollama')
  build_client(role, model_name) -> OllamaChatClient
```

Implements the existing two-member `AIProvider` protocol and registers in `_resolve_real_providers`
under `'ollama'`. `OpenAIProvider` and its client are not modified.

`OllamaChatClient.generate()` POSTs to `/api/chat`:

```json
{
  "model": "<model_name>",
  "stream": false,
  "messages": [
    {"role": "system", "content": "<_system_message_for_role(role)>"},
    {"role": "user", "content": "<request.prompt>"}
  ],
  "options": {"temperature": ..., "num_predict": ..., "num_ctx": ...},
  "format": "json",
  "keep_alive": "..."
}
```

`format` is set only when `_expects_json_response(request.prompt_name)` is true. `keep_alive` and
`num_ctx` are omitted when unset.

**Both helpers are reused, not copied.** `_system_message_for_role()` and `_expects_json_response()`
already exist in `providers.py`. Duplicating them would turn audit finding D2-14 (prompt policy encoded
in the provider layer) from one site into two.

### Response mapping

| Ollama field | `ModelResponse` |
|---|---|
| `message.content` (stripped) | `content` — raises if empty |
| `prompt_eval_count` | `token_usage['prompt_tokens']` |
| `eval_count` | `token_usage['completion_tokens']` |
| sum of the two | `token_usage['total_tokens']` |
| wall-clock | `latency_ms` — consistent with the OpenAI client |
| — | `provider_name='ollama'`, `model_name=<model_name>` |

Ollama reports durations in nanoseconds. `latency_ms` uses wall-clock rather than `total_duration` so
the two providers remain comparable; the finer-grained Ollama timings are consumed by the harness, not
the client.

### Error mapping

| Condition | Raises | Rationale |
|---|---|---|
| `httpx.ConnectError` | `ProviderRequestError` — "Ollama not reachable at `{base_url}` — is the service running?" | Most common local failure; a generic message wastes the operator's time |
| HTTP 404, model not found | `ProviderConfigurationError` | A model that was never pulled is a configuration fault, not a request fault. No OpenAI analogue |
| `httpx.TimeoutException` | `ProviderTimeoutError` | Expected on cold loads and CPU fallback |
| status >= 400 | `ProviderRequestError` from Ollama's `{"error": ...}` body | — |
| role mismatch | `ModelError` | Mirrors `OpenAIChatCompletionsClient` |

No 429 path — Ollama does not rate limit. No retry or backoff: that is audit finding D2-13 (the provider
error taxonomy is declared but never caught by type, and no retry layer exists) and is out of scope here.

## 3. Spike harness

`scripts/spike/ollama_eval.py`. New directory, outside the packaged trees — `pyproject.toml`
`packages.find` includes only `jester*`, `pipeline*`, `training*`, so spike code cannot ship.

Prompts are loaded through `jester.prompts.registry` with realistic template values. Invented prompts
would not answer the question.

| Role | Prompts | Checked by |
|---|---|---|
| Router | `routing_live_dm_intent`, `teaching_depth` | JSON parses; `output_contract` keys present |
| Arbiter | `prep_plan`, `prep_critique`, `teaching_structure` | JSON parses; `output_contract` keys present |
| Narrator | `live_dm_narration`, `live_dm_info_response`, `prep_npc`, `teaching_explain_concept` | `jester/validation/output_validator.py` |

Each prompt runs N times (default 3) to expose nondeterminism.

**Recorded per call:** wall-clock latency; `load_duration`; `prompt_eval_count` and duration;
`eval_count` and duration; derived tokens/sec in both directions; the role's pass/fail check.

**Recorded per run, at start and end:** `ollama ps` placement percentage, free VRAM, model tag,
resolved `num_ctx`. Without these the results are not interpretable.

**Outputs:** `report.md` — per-role pass rates and latency percentiles; `samples.md` — prose grouped by
prompt for human reading. A `--model` flag reruns the identical suite against another tag so
comparisons are like-for-like.

### Go/no-go thresholds

Proposed, to be confirmed against the first run rather than asserted now:

- Router and Arbiter: JSON validity >= 95%, required keys present >= 95%
- Narrator: `output_validator` pass >= 90%
- Latency: reported, not gated — the threshold depends on the deployment posture, and the first run's
  numbers should inform it

## 4. Testing

`tests/test_ollama_provider.py`, using `httpx.MockTransport` in the pattern already established by
`tests/test_ai_data_runtime.py`:

1. Happy path — content, token usage, and `provider_name='ollama'` mapped correctly
2. Empty `message.content` raises `ProviderRequestError`
3. HTTP 404 model-not-found raises `ProviderConfigurationError`
4. `httpx.ConnectError` produces the reachability message
5. `httpx.TimeoutException` raises `ProviderTimeoutError`
6. `format: "json"` present for a JSON prompt, absent for a prose prompt
7. `options` mapping — temperature, `num_predict`, `num_ctx`
8. Role mismatch raises `ModelError`

**No live-Ollama test enters the suite.** It stays hermetic and fast; the existing suite completes in
~2.1 s and that property is worth protecting. Live inference is the harness's job.

## 5. Out of scope

Streaming · retry and backoff (D2-13) · health-endpoint integration · relaxing the mixed fake/real
provider guard (D2-17) · per-role provider splitting · extracting a shared `ChatCompletionsClient`
base · any Wave R1 remediation.

Note that CQ-011 — `/health/dependencies` reporting `ok` while the AI stack is the fake provider — is
*adjacent* but not fixed here. This design adds a real provider; it does not change how health is
computed. Wiring `provider_name` into the health verdict remains Wave R2.

## 6. Risks

| Risk | Mitigation |
|---|---|
| GPU contention makes results unrepresentative | Harness records placement and free VRAM per run; verdicts state the observed placement |
| `qwen3.5:9b` (6.6 GB) does not fit alongside desktop VRAM use | Fall back to `qwen3.5:4b` (3.4 GB); both measured against `mistral:latest` as baseline |
| Arbiter JSON adherence fails | `format: "json"` constrains at the sampler; if it still fails, that is a genuine per-role no-go and the harness will say which checks failed |
| Latency unacceptable for live play | Reported per role; prep and teaching tolerate latency that live narration does not, so a partial go is a valid outcome |

## 7. Success criteria

The spike succeeds when a per-role go/no-go can be stated from `report.md` with the hardware placement
that produced it — not when the numbers are good. A well-evidenced "no" for the Arbiter role is a
successful spike.

# Base Model Selection Policy

## Purpose

Sprint 1 does not choose a winning base model. It defines the evaluation framework Jester will use before any adapter training or runtime binding is finalized.

## Mandatory criteria

Every candidate base model must be evaluated against:

- commercial usability and redistribution terms
- local inference viability on target Jester hardware
- context window adequacy for retrieval-backed prompts
- maturity of the fine-tuning ecosystem
- quantization support and deployment stability
- structured output reliability
- reasoning quality for rules-heavy tasks
- prose quality for narration and prep tasks
- compatibility with Ollama or a similar local runtime

## Evaluation method

Each candidate should be scored with a short written judgment and a numeric band such as `strong`, `acceptable`, or `weak` for each criterion. Do not collapse prose quality and reasoning quality into one score; Jester needs both and may select different bases for each.

## Shortlist slots

Sprint 1 maintains three evaluation slots rather than a final recommendation:

- `Narrator shortlist slot`: target a local instruct model in the 7B-9B class optimized for long-form prose and style control
- `Arbiter shortlist slot`: target a local instruct model in the 7B-9B class optimized for grounded reasoning and structured answers
- `Router shortlist slot`: target a small 1B-3B class model optimized for fast classification and low-latency routing

These slots are product roles, not vendor endorsements.

## Disqualifiers

A candidate should be rejected if any of the following are true:

- the license is ambiguous for commercial local deployment
- the model is too large for practical local serving in Jester's expected environment
- structured outputs are unreliable enough to break backend contracts
- quantized variants materially collapse the target workload quality
- the runtime cannot be hosted behind a stable local contract

## Decision output for Sprint 2

When Jester is ready to select bases, each shortlist slot should produce:

- one preferred candidate
- one fallback candidate
- one-paragraph rationale tied to Jester task families
- measurement notes from the same prompt/eval harness used across all candidates

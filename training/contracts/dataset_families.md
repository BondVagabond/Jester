# Dataset Families

## Narration

- Purpose: support evocative scene writing, prep prose, NPC voice, and world-detail expansion
- Input fields: `instruction`, optional `retrieved_context`, `tone`, `domain`, `style_targets`
- Output fields: `answer` or task-specific prose payload
- Quality bar: vivid but controlled prose, no contradiction of supplied facts, low filler
- Disallowed contamination: copied commercial flavor text, fan-wiki paraphrase, unsupported lore claims
- Evaluation style: human rubric on coherence, groundedness, tone fit, and usefulness
- Citations required: no, unless the request is explicitly rules-grounded
- Retrieval assumed: optional but often helpful

## Teaching

- Purpose: explain concepts clearly to a player or GM at a selected depth
- Input fields: `instruction`, `retrieved_facts`, `depth`, `audience`, `tone`
- Output fields: `answer`, optional `misconceptions`, optional `practice_prompts`
- Quality bar: accurate, beginner-friendly, well-structured, no unnecessary jargon
- Disallowed contamination: unsupported rules summaries, copied proprietary text, hidden chain-of-thought dumps
- Evaluation style: accuracy and pedagogical clarity review, plus misconception coverage checks
- Citations required: yes when rule interpretation depends on retrieved material
- Retrieval assumed: yes for official rules-heavy prompts

## Reasoning

- Purpose: provide grounded interpretation support for ambiguous rules or arbitration questions
- Input fields: `instruction`, `retrieved_facts`, `question_type`, `session_state`, `constraints`
- Output fields: `answer`, `confidence`, `used_context_ids`, optional `warnings`
- Quality bar: concise rationale, explicit uncertainty, no unsupported certainty
- Disallowed contamination: hallucinated citations, unsupported legalistic certainty, deterministic-state invention
- Evaluation style: groundedness review against source context and confidence calibration checks
- Citations required: yes
- Retrieval assumed: yes

## Routing

- Purpose: classify the request so the backend can choose the correct workspace, tone, and role
- Input fields: `instruction`, optional `session_state`, optional `retrieval_hint`
- Output fields: `task_family`, `role`, `response_style`, `confidence`
- Quality bar: stable bounded labels with low latency and strong calibration
- Disallowed contamination: open-ended prose generation, unsupported labels, leaking blocked source text into prompts
- Evaluation style: label accuracy, confidence calibration, and latency tests
- Citations required: no
- Retrieval assumed: no

# Model Roles

## Purpose

Jester will train and serve role-specific local models instead of treating one model as the whole backend. Roles are product abstractions first and runtime bindings second.

## Roles

### Narrator

- Primary use: prep generation, live narration, stylistic prose, NPC/world content
- Default task families: `narration`, `teaching` for prose examples only
- Strengths required: coherent scene writing, tone control, concise expansions, context-grounded creativity
- Failure mode to avoid: inventing canonical facts not present in backend or retrieval context
- Current backend mapping: aligns with the existing primary-generation lane

### Arbiter

- Primary use: rules reasoning, teaching explanations, structured answers, ambiguity handling
- Default task families: `teaching`, `reasoning`
- Strengths required: grounded explanation, citation discipline, confidence reporting, clean structured outputs
- Failure mode to avoid: presenting uncertain interpretations as authoritative rulings
- Current backend mapping: aligns with the existing reasoning lane

### Router

- Primary use: cheap, fast classification, intent labeling, workspace routing, tone/depth selection
- Default task families: `routing`
- Strengths required: low latency, stable labels, high calibration on confidence
- Failure mode to avoid: leaking into long-form generation or unsupported freeform reasoning
- Current backend mapping: aligns with the existing small-fast or classifier lane

## Role boundary rules

- `Narrator` does not own final mechanics.
- `Arbiter` does not mutate canonical state.
- `Router` does not produce user-facing long-form content unless explicitly wrapped by another role contract.

## Runtime binding

Future Ollama integration should bind backend task families to roles, then bind roles to concrete local models. The backend should never hardcode a specific provider's request format into product logic.

# Backend Task Contracts

## Purpose

The local model layer exists to serve backend-defined tasks. The backend owns routing, retrieval, state integrity, and fallback behavior. The model only produces language or classifications inside a bounded contract.

## Approved task families

### A. Prep generation

- Backend surfaces: `POST /api/v1/prep`
- Primary role: `narrator`
- Outputs: encounter ideas, setting details, quest hooks, NPC summaries, worldbuilding expansions
- Backend guarantees: validated request shape, optional retrieved world context, output validation, authored fallback text
- Model constraints: no authority over canonical game state; prose must remain consistent with supplied context

### B. Teaching / explanation

- Backend surfaces: `POST /api/v1/teaching`
- Primary role: `arbiter`
- Outputs: beginner-friendly explanations, concept walkthroughs, misconceptions, clarifications, examples, practice prompts
- Backend guarantees: rules/context retrieval, response shaping, safety filtering
- Model constraints: must prefer retrieved rule context over unsupported speculation

### C. Live DM narrative support

- Backend surfaces: `POST /api/v1/live-dm/turns`
- Primary role: `narrator`
- Outputs: scene narration, sensory detail, NPC voice drafts, consequence framing
- Backend guarantees: deterministic state mutation, resolved mechanics, current session context
- Model constraints: cannot invent state transitions that contradict deterministic outputs

### D. Rules reasoning support

- Backend surfaces: `POST /api/v1/teaching`, `POST /api/v1/live-dm/turns`, and internal arbitration helpers
- Primary role: `arbiter`
- Outputs: likely interpretation, concise rationale, confidence, citation targets from retrieved rules context
- Backend guarantees: retrieved rules snippets and the final authority to accept or reject the interpretation
- Model constraints: reasoning must be grounded in retrieved context IDs; low-confidence answers should say so

### E. Small-fast routing / classification

- Backend surfaces: internal orchestration only
- Primary role: `router`
- Outputs: task type, response style, workspace intent, confidence
- Backend guarantees: bounded labels, a deterministic fallback route, and post-classification validation
- Model constraints: classification output is advisory; backend routing policy remains authoritative

## Non-goals

The model contract explicitly excludes:

- direct canonical state mutation
- raw database writes
- auth decisions
- permission grants
- final safety policy decisions
- final artifact/version resolution

## Contract rule

If a task cannot be expressed as a bounded request with clear backend ownership, it is not a valid local-model task for Sprint 1.

# Backlog v0.0.2

## Goal
Deliver a feature-focused upgrade that leverages modern Ollama capabilities for better UX, reliability, and extensibility:
- Chat API-based orchestration (`/api/chat`)
- Tool calling
- Structured outputs
- Vision input support
- Embeddings-powered semantic memory
- Smarter model routing and runtime controls
- Better observability and safety controls

## Scope
### In scope
- New Telegram UX commands/actions needed for these capabilities
- Ollama client extensions and runtime options support
- Persistence updates for per-user settings and semantic memory metadata
- Operational metrics and logs for model performance

### Out of scope (v0.0.2)
- Full web dashboard
- Multi-tenant billing/quotas
- Advanced agent orchestration across multiple external providers

## Release Strategy
- **v0.0.2-alpha**: Chat API migration + structured output foundation
- **v0.0.2-beta**: Tool calling + vision support
- **v0.0.2-rc**: Embeddings memory + model routing + runtime controls
- **v0.0.2**: Hardening, docs, tests, production rollout

---

## Epic A — Migrate to Ollama Chat API (Priority: P0)
### Outcome
Use `POST /api/chat` as the primary inference endpoint with role-based messages.

### Tasks
- [ ] Add `chat()` method in Ollama client for `messages`, `tools`, `format`, `options`, `keep_alive`.
- [ ] Introduce internal message schema (`system`, `user`, `assistant`, `tool`).
- [ ] Refactor current conversation assembly to role-based message history.
- [ ] Keep backward-safe adapter for current generate path (temporary fallback).
- [ ] Add config flags:
  - `OLLAMA_USE_CHAT_API=true`
  - `OLLAMA_KEEP_ALIVE=5m`

### Acceptance Criteria
- [ ] Normal chat flow uses `/api/chat` successfully.
- [ ] Existing commands still work (`/start`, `/help`, `/models`, `/currentmodel`, `/clear`, `/health`).
- [ ] Fallback path is available when chat call fails unexpectedly.

---

## Epic B — Structured Outputs for Command-like Flows (Priority: P0)
### Outcome
Support deterministic JSON responses for automatable tasks.

### Tasks
- [ ] Add structured-output request helper (`format: json` and JSON Schema).
- [ ] Add Telegram commands:
  - [ ] `/extract` (entity extraction from free text)
  - [ ] `/classify` (intent/topic classification)
  - [ ] `/plan` (step-by-step task plan as JSON)
- [ ] Validate and parse JSON safely with explicit error handling.
- [ ] Add per-command schema definitions and parser unit tests.

### Acceptance Criteria
- [ ] Structured commands return valid parsed JSON objects.
- [ ] Invalid model JSON returns user-safe error and retry guidance.
- [ ] Logs include schema name, parse success/failure, and latency.

---

## Epic C — Tool Calling (Priority: P0)
### Outcome
Allow model-driven function/tool invocation with strict guardrails.

### Tasks
- [ ] Add `tools` payload support to chat requests.
- [ ] Implement tool execution runtime with strict allowlist and argument validation.
- [ ] Implement first-party tools:
  - [ ] `get_bot_health`
  - [ ] `list_available_models`
  - [ ] `get_current_model`
- [ ] Optional external tool adapter interface:
  - [ ] `web_search` (feature-flagged)
- [ ] Append tool results as `role=tool` messages and continue chat turn.

### Acceptance Criteria
- [ ] Model can request tool calls and receive tool outputs in same conversation.
- [ ] Unknown tool requests are blocked and logged.
- [ ] Tool errors are recoverable and visible as user-friendly warnings.

---

## Epic D — Vision Input Support (Priority: P1)
### Outcome
Users can send image + prompt and get visual analysis via multimodal models.

### Tasks
- [ ] Handle Telegram photo/document images in handlers.
- [ ] Download and convert images to base64 for Ollama `images` field.
- [ ] Add `/vision` mode command and auto-detect flow for image messages.
- [ ] Add max image size/count limits to avoid memory spikes.
- [ ] Add user guidance when selected model lacks vision capability.

### Acceptance Criteria
- [ ] User can send image and receive answer from vision-capable model.
- [ ] Non-vision model path returns clear suggestion to switch model.
- [ ] Logs include image size, processing latency, and model used.

---

## Epic E — Embeddings + Semantic Memory (Priority: P1)
### Outcome
Improve contextual quality with semantic recall using `/api/embed`.

### Tasks
- [ ] Add embeddings client support for `POST /api/embed`.
- [ ] Create persistence for semantic snippets + vectors metadata.
- [ ] Add retrieval step before chat completion (top-k relevant memories).
- [ ] Add commands:
  - [ ] `/memory on|off`
  - [ ] `/memory clear`
- [ ] Add configurable limits:
  - `EMBED_MODEL`
  - `MEMORY_TOP_K`
  - `MEMORY_MAX_ITEMS_PER_USER`

### Acceptance Criteria
- [ ] Retrieved memory improves continuity across sessions.
- [ ] Users can opt-out and clear memory.
- [ ] Memory retrieval is bounded and does not degrade response times excessively.

---

## Epic F — Model Capability Discovery + Auto Routing (Priority: P1)
### Outcome
Route tasks to the most suitable local model and adapt UX to model capabilities.

### Tasks
- [ ] Use `POST /api/show` to fetch model `capabilities` and details.
- [ ] Cache capability metadata with TTL.
- [ ] Build routing policy:
  - [ ] chat/general -> default chat model
  - [ ] structured/tool tasks -> tool-capable model
  - [ ] vision tasks -> vision-capable model
  - [ ] memory retrieval -> embedding model
- [ ] Show capability hints in `/models` output.

### Acceptance Criteria
- [ ] Task routing chooses compatible model automatically.
- [ ] Manual model override still works per user.
- [ ] UX warns when user-selected model cannot execute requested feature.

---

## Epic G — Runtime Controls & Model Lifecycle (Priority: P2)
### Outcome
Lower latency and better resource management with model load behavior controls.

### Tasks
- [ ] Support configurable `keep_alive` per request path.
- [ ] Add prewarm command `/prewarm <model>`.
- [ ] Add optional unload command `/unload <model>` (`keep_alive=0` behavior).
- [ ] Integrate `GET /api/ps` to inspect running models in `/health` or `/runtime`.

### Acceptance Criteria
- [ ] Cold-start latency reduced after prewarm.
- [ ] Runtime status exposes loaded models and expiry information.
- [ ] Unload action is permission-gated and logged.

---

## Epic H — Observability Enhancements (Priority: P1)
### Outcome
Production observability for model quality/performance tracking.

### Tasks
- [ ] Record Ollama generation stats from final responses:
  - `total_duration`, `load_duration`, `prompt_eval_count`, `eval_count`, `eval_duration`
- [ ] Add derived metric logging (`tokens_per_second`).
- [ ] Add request correlation id per Telegram update.
- [ ] Add structured event names for all major actions.

### Acceptance Criteria
- [ ] Every model response logs core performance fields.
- [ ] Correlation id links user event -> model call -> response.
- [ ] `/health` includes lightweight runtime metric snapshot.

---

## Epic I — Safety Layer (Priority: P2)
### Outcome
Optional pre/post moderation step for safer outputs.

### Tasks
- [ ] Add optional safety classifier hook (feature-flagged model check).
- [ ] Pre-input and post-output checks with configurable actions (warn/block).
- [ ] Add secure logging mode that avoids sensitive prompt leakage.

### Acceptance Criteria
- [ ] Safety checks can be enabled/disabled via environment config.
- [ ] Blocked responses are user-friendly and auditable in logs.

---

## Epic J — Experimental Image Generation (Priority: P3)
### Outcome
Optional `/imagine` command powered by Ollama experimental image generation.

### Tasks
- [ ] Add `/imagine` command with prompt and optional size/steps.
- [ ] Handle progress updates and final base64 image decode.
- [ ] Send generated image back to Telegram as photo.
- [ ] Guard behind feature flag due API experimental status.

### Acceptance Criteria
- [ ] Feature works only when enabled and model supports it.
- [ ] Errors clearly indicate experimental availability constraints.

---

## Cross-Cutting Engineering Tasks
- [ ] Add/update tests for each epic (unit + integration-level mocks).
- [ ] Expand `.env.example` with all new options and comments.
- [ ] Update README command list and operational sections.
- [ ] Add migration notes for config changes in `CHANGELOG.md`.
- [ ] Add release checklist for v0.0.2 deployment and rollback.

## Proposed New Commands (v0.0.2)
- [ ] `/health` (enhanced with runtime/model stats)
- [ ] `/extract`
- [ ] `/classify`
- [ ] `/plan`
- [ ] `/vision`
- [ ] `/memory on|off`
- [ ] `/memory clear`
- [ ] `/prewarm <model>`
- [ ] `/unload <model>` (optional, admin-gated)
- [ ] `/imagine` (experimental, feature-flagged)

## Suggested Environment Variables
- [ ] `OLLAMA_USE_CHAT_API=true`
- [ ] `OLLAMA_KEEP_ALIVE=5m`
- [ ] `ENABLE_TOOL_CALLING=true`
- [ ] `ENABLE_VISION=true`
- [ ] `ENABLE_SEMANTIC_MEMORY=true`
- [ ] `EMBED_MODEL=nomic-embed-text`
- [ ] `MEMORY_TOP_K=5`
- [ ] `MEMORY_MAX_ITEMS_PER_USER=200`
- [ ] `ENABLE_IMAGE_GENERATION=false`
- [ ] `ENABLE_WEB_SEARCH_TOOL=false`
- [ ] `ENABLE_SAFETY_FILTER=false`

## Dependency Order (Implementation Sequence)
1. Epic A (Chat API migration)
2. Epic B (Structured outputs)
3. Epic C (Tool calling)
4. Epic D (Vision)
5. Epic F (Capability discovery + routing)
6. Epic E (Embeddings memory)
7. Epic H (Observability enhancements)
8. Epic G (Runtime controls)
9. Epic I (Safety layer)
10. Epic J (Experimental image generation)

## Definition of Done (v0.0.2)
- [ ] All P0 epics completed and tested.
- [ ] At least 2 P1 epics completed.
- [ ] README, `.env.example`, and changelog fully updated.
- [ ] No critical errors in diagnostics for changed files.
- [ ] Manual verification in Telegram for chat, tools, and one advanced mode.

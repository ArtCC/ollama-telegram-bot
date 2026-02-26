## Phase 1 (MVP) ✅

- [x] Core bot architecture and environment-based configuration.
- [x] Docker-first deployment with Compose and GHCR publish workflow.
- [x] Core conversation flow with contextual chat and error-safe Ollama calls.
- [x] Base command set and UX (`/start`, `/help`, `/health`, `/clear`, `/models`, `/webmodels`, `/files`, `/askfile`, `/currentmodel`).
- [x] Unified bot UI (slash commands + persistent quick buttons + inline actions).
- [x] Unified status messaging (`ℹ️ info`, `✅ success`, `⚠️ warning`, `❌ error`).
- [x] Per-user model management with SQLite persistence.
- [x] Access control with user whitelist (`ALLOWED_USER_IDS`).
- [x] Basic per-user rate limiting.
- [x] Healthcheck command and operational status checks.
- [x] Logging hardening for production observability.

## Phase 2 ✅

- [x] Primary inference migration to Ollama Chat API (`/api/chat`).
- [x] Automatic fallback to `/api/generate` for compatibility and resilience.
- [x] Runtime feature flags for chat migration:
  - `OLLAMA_USE_CHAT_API`
  - `OLLAMA_KEEP_ALIVE`
- [x] Configuration and deployment docs updated for new Chat API controls.
- [x] Internal agent routing (planner/analyzer/chat) with natural-language responses only.
- [x] Persistent SQLite conversation context across restarts.
- [x] Natural-language-first UX: no extra technical commands required for advanced behavior.
- [x] Image input support (photo/image document + optional caption instruction) using the selected model.
- [x] Document upload and review support (TXT / MD / CSV / JSON / YAML / PDF / DOCX / XLSX) using the selected model.
- [x] Optional cloud-ready Ollama auth configuration (`OLLAMA_API_KEY`, `OLLAMA_AUTH_SCHEME`).
- [x] Localization support with user Telegram language resolution and English fallback.
- [x] Locale files available for `en`, `es`, `de`, `fr`, and `it`.

## Phase 3 ✅

- [x] `/models` model browser with inline pagination (previous/next) and name filtering via `/models <query>`.
- [x] `/models` pagination updates in-place on the same message, including inline close action to remove the list message.
- [x] `/webmodels` independent browser for Ollama web catalog models available to install, with its own search, pagination, and inline close action.
- [x] MVP file memory workflow: uploaded documents/images are persisted per user and can be listed from `/files`.
- [x] `/files` inline management: select/deselect files for context and delete files.
- [x] Selected files are injected as context for model responses (RAG-lite retrieval over selected user files).
- [x] `/cancel` command to exit any pending interaction mode (e.g. inline Ask).
- [x] Inline `💬 Ask` button per file in `/files` for direct single-file questioning.
- [x] Asset deduplication: identical file content is stored only once per user (SHA-256 hash).
- [x] Automatic asset TTL purge at startup (configurable via `ASSET_TTL_DAYS`, default 30 days).
- [x] RAG context limits configurable via `FILES_CONTEXT_MAX_ITEMS` and `FILES_CONTEXT_MAX_CHARS`.
- [x] Improved image ingestion prompt: detailed description covering objects, text, colours, and scene context.
- [x] Image-related RAG instructions always injected when image assets are in context (no keyword dependency).
- [x] Document confirmation message includes asset ID and `/askfile` hint for immediate use.
- [x] Image RAG aligned with Ollama `/api/chat` spec: stored image bytes are re-sent in the `images` field of the conversation history message, giving the model actual pixel data instead of a text label when answering follow-up questions.
- [x] Upload-only mode in `/files`: press **📤 Add file** to save an image without triggering model analysis.
- [x] Image preview in `/files`: press **🖼️ Preview** on any saved image to see a thumbnail inline.
- [x] **Model orchestrator**: automatic local model selection per request type — vision model for images, code-specialised model for programming questions, user-preferred model for everything else.
- [x] Pre-flight vision capability check: warns user immediately if no vision-capable model is installed, instead of forwarding to a blind model.
- [x] Ollama Vision API compliance: `images` field correctly placed inside the user message object for `/api/chat`; `images`, `system`, and `keep_alive` at root level for `/api/generate`.
- [x] Multilingual `_looks_like_missing_image_response` detection covering EN/ES/DE/FR/IT with narrowed patterns to eliminate false positives.
- [x] Full observability logging across the image pipeline (task detection, model selection, payload details, raw response preview, fallback reasons).
- [x] **`/webmodels` download flow**: tapping a model in the web catalog now opens a detail card with two inline buttons — **⬇️ Download** (triggers `ollama pull` via `POST /api/pull` in the background) and **🌐 Web** (opens the Ollama.com library page for that model).
- [x] Background model download with in-progress guard: duplicate download attempts are rejected with an inline alert, and the result (success or error) is sent as a new chat message on completion.
- [x] **Rich web model catalog**: `/webmodels` now scrapes `https://ollama.com/search` to extract per-model description, capability badges (👁 vision, 🔧 tools, 💭 thinking, 📊 embedding, ☁️ cloud), available sizes, pull count, tag count and last-updated time.
- [x] Model detail card shows all structured metadata before the user decides to download.
- [x] **Size selection keyboard**: when a model has multiple downloadable sizes (e.g. `1b`, `3b`, `70b`) the Download button opens a size picker; single-size or unknown-size models go straight to download.
- [x] 5-minute in-memory web model list cache to avoid redundant web fetches across rapid interactions.
- [x] `/webmodels` filter now searches across name, description, capabilities and sizes.
- [x] **Real-time web model search button**: the `/webmodels` list now includes a 🔍 Search button; tapping it enters search mode so the user's next message is treated as a filter query, without needing to retype `/webmodels <query>`.
- [x] **`/websearch <query>`**: performs a live web search via the Ollama Cloud Web Search API (`POST https://ollama.com/api/web_search`), injects up to 5 results as grounded context, queries the local model with the enriched prompt, and returns the model's answer followed by a clickable sources list. Requires `OLLAMA_API_KEY`.
- [x] **`/deletemodel <name>`**: prompts for confirmation before calling `DELETE /api/delete`; handles 404 and generic errors with localized messages.
- [x] **`/info [model]`**: shows a rich HTML card with family, parameter count, quantization, architecture, disk size (MB) and the first 200 characters of the system prompt. Falls back to the user's current model when no argument is given.
- [x] Real-time download progress bar during `ollama pull` with throttled message edits (every 2 s) and a ❌ Cancel inline button.

## Phase 4

- Upload a **document** (TXT / MD / CSV / JSON / YAML / PDF / DOCX / XLSX) or an **image** as usual.
- Uploaded files are stored per user and are selected by default for contextual use. Identical content is deduplicated automatically.
- Open `/files` to:
  - list saved files,
  - select/deselect files to include in context,
  - delete files you no longer want to keep,
  - ask directly from one file using the inline `💬 Ask` button.
- After pressing `💬 Ask`, send your question as a plain message. Use `/cancel` to exit Ask mode without asking.
- Use `/askfile <id> <question>` to force a response based on one specific file.
- The model uses selected files as additional context when answering new requests.
- For documents with caption, the bot also performs immediate review while keeping the file saved.
- For images, the original bytes are stored alongside the analysis so the model receives real pixel data (not just a description) when you ask follow-up questions later.
- Stored assets are automatically purged after `ASSET_TTL_DAYS` days (default: 30).
- Use `/websearch <query>` to search the live internet and get a model-synthesised answer grounded in real results.
- Requires `OLLAMA_API_KEY` (a free [Ollama account](https://ollama.com/settings/keys) is enough).
- The bot calls `POST https://ollama.com/api/web_search`, injects up to 5 results as context for your local model, and appends a clickable sources list below the answer.
- Results are automatically truncated to fit the model's practical context window (~4 000 characters of web content).
- The model's reply and the sources are saved to your conversation context so you can ask follow-up questions.
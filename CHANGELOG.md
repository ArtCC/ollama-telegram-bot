# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project follows Semantic Versioning.

## [0.0.6] - 2026-02-26

### Added
- Added paginated `/models` browsing with inline previous/next navigation buttons.
- Added `/models <query>` filtering support to search available models by name.
- Added dedicated `/webmodels` command to browse Ollama web catalog models available to install (separate from local `/models`).
- Added independent web-model pagination and search flow (`/webmodels <query>`) with inline previous/next navigation.
- Added direct web catalog links per model and install guidance (`ollama pull <model>`) in bot responses.
- Added inline close action for both `/models` and `/webmodels` lists, removing the list message from chat.
- Added persistent user file storage (documents and analyzed images) in SQLite for reusable context.
- Added `/files` command with inline pagination, select/deselect actions, and delete action per file.
- Added selected-files context injection in chat/image prompts (RAG-lite retrieval over selected user files).

### Changed
- Updated local and web model pagination to render over the same message (no new message per page when edit is possible).
- Updated command registry, quick actions keyboard, and localized help text to clearly separate local models and web catalog models.
- Updated localized command/button/error catalog to support file-management workflow.

## [0.0.5] - 2026-02-26

### Added
- Added `OLLAMA_CLOUD_BASE_URL` runtime configuration to route `*-cloud` model requests directly to cloud API endpoints.
- Added cloud-model selection fallback so `*-cloud` models can be selected even if they are not listed by local `/api/tags`.

### Changed
- Changed image handling flow to always attempt model inference and rely on Ollama runtime response instead of pre-blocking with capability checks.
- Updated configuration/docs for cloud usage without daemon-level `ollama signin`.

## [0.0.4] - 2026-02-16

### Added
- Added full German locale file `locales/de.json`.
- Added full French locale file `locales/fr.json`.
- Added full Italian locale file `locales/it.json`.
- Added startup diagnostics logging for container bootstrap (i18n locales, storage, Ollama config and runtime limits).
- Added document ingestion and review support using the selected model (TXT/MD/CSV/JSON and PDF).
- Added document limits configuration with `DOCUMENT_MAX_BYTES` and `DOCUMENT_MAX_CHARS`.
- Added optional Ollama cloud/auth configuration using `OLLAMA_API_KEY` and `OLLAMA_AUTH_SCHEME`.
- Added direct cloud routing for `*-cloud` models via `OLLAMA_CLOUD_BASE_URL` + API key, allowing cloud usage without daemon-level `ollama signin`.

### Fixed
- Included the `locales/` directory in Docker image build to prevent startup failures in containers.

### Changed
- Updated README locale documentation and project structure to include all available locales (`en`, `es`, `de`, `fr`, `it`).

## [0.0.3] - 2026-02-16

### Added
- Added image understanding support for photo/image-document messages using the user-selected model and optional caption instructions.
- Added vision-capability guard for selected models with user-friendly fallback guidance when the model cannot process images.
- Added configurable image-size protection (`IMAGE_MAX_BYTES`) with friendly feedback when files exceed the limit.
- Added separate user feedback for unreadable/corrupt image files versus model-processing failures.
- Added i18n foundation with `locales/en.json`, user-language resolution from Telegram, and fallback to English for unsupported locales.
- Added full Spanish (Spain) locale file `locales/es.json` with translated user-facing messages, commands, buttons, and prompts.
- Added locale-aware command registration and keyboard labels per user locale.
- Added `BOT_DEFAULT_LOCALE` runtime configuration and synchronized it across `.env.example`, `docker-compose.yml`, and `README.md`.
- Added startup diagnostic logs for container troubleshooting (version, i18n locales, storage path, Ollama config, runtime limits, and rate-limit status).
- Enforced no-voice interaction mode at runtime: voice, audio, and video-note messages are blocked with a user-facing guidance message.
- Updated documentation to reflect text+image behavior and disabled voice/audio inputs.

## [0.0.2] - 2026-02-14

### Added
- Migrated primary inference flow to Ollama Chat API (`/api/chat`) with role-based message payloads.
- Added automatic fallback to `/api/generate` when chat requests fail.
- Added `OLLAMA_USE_CHAT_API` and `OLLAMA_KEEP_ALIVE` runtime configuration flags.
- Updated deployment/docs configuration to expose Chat API migration settings.
- Added internal natural-language agent routing (planner/analyzer/chat) inside message flow without exposing technical commands.
- Added persistent SQLite-based conversation context to preserve chat memory across bot restarts.
- Consolidated natural-language-first UX so advanced orchestration happens internally without extra user commands.

## [0.0.1] - 2026-02-14

### Added
- Initial project structure for a Telegram bot integrated with Ollama.
- Docker deployment base with environment-driven configuration.
- GitHub Actions workflow to publish container images to GHCR.
- Core bot bootstrap with long polling and command registration.
- MVP commands: `/start`, `/help`, `/clear`.
- In-memory conversation context management per user.
- Ollama client integration with timeout, retry, and categorized error handling.
- User-facing error handling for Telegram interactions.
- Message chunking utility for Telegram 4096 character limit.
- `/models` command to list available Ollama models and select an active model per user.
- `/currentmodel` command to show the active model for the current user.
- Persist selected `/models` value per user in SQLite database.
- Persistent in-chat quick action buttons for models, current model, clear context, and help.
- Inline model selection buttons in `/models` using callback actions.
- Inline confirmation flow for `/clear` and quick model actions from `/currentmodel`.
- Unified status message style with fixed iconography for info/success/warning/error.
- Access control with `ALLOWED_USER_IDS` whitelist validation for commands, callbacks, and messages.
- Sliding-window per-user rate limiting for chat messages using `RATE_LIMIT_MAX_MESSAGES` and `RATE_LIMIT_WINDOW_SECONDS`.
- Enforced `ALLOWED_USER_IDS` as mandatory and non-empty during startup configuration validation.
- `/health` command with operational checks for bot runtime, SQLite connectivity, and Ollama availability.
- Production-oriented logging hardening (UTC timestamps, stdout handler, warning capture, forced logger setup, and contextual event logs).
- Base developer tooling: Ruff, MyPy, and Pytest configuration.
- Initial test suite for context store and Telegram message splitting.
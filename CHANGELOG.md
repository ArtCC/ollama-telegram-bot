# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project follows Semantic Versioning.

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
- Base developer tooling: Ruff, MyPy, and Pytest configuration.
- Initial test suite for context store and Telegram message splitting.
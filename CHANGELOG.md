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
- Base developer tooling: Ruff, MyPy, and Pytest configuration.
- Initial test suite for context store and Telegram message splitting.

# Ollama Telegram Bot

[![Docker Publish](https://github.com/ArtCC/ollama-telegram-bot/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/ArtCC/ollama-telegram-bot/actions/workflows/docker-publish.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Docker Compose](https://img.shields.io/badge/Docker%20Compose-Ready-2496ED?logo=docker&logoColor=white)](docker-compose.yml)
[![GHCR](https://img.shields.io/badge/GHCR-ghcr.io%2Fartcc%2Follama--telegram--bot-181717?logo=github)](https://ghcr.io/artcc/ollama-telegram-bot)

<p align="left">
  <img src="assets/ollama-telegram-bot.png" alt="Ollama Telegram Bot Avatar" width="150">
</p>

Open-source Telegram bot to chat with Ollama models running on your server.

## Overview

- Telegram bot with async handlers and user-friendly error responses.
- Ollama integration with timeout, retries, and categorized failures.
- Docker-first deployment with environment-driven configuration.
- CI workflow for publishing container images to GHCR.
- Text + image + document interaction mode: voice/audio messages are intentionally disabled.

## Project Structure

```text
ollama-telegram-bot/
├── .github/
│   └── workflows/
│       └── docker-publish.yml
├── locales/
│   ├── de.json
│   ├── en.json
│   ├── es.json
│   ├── fr.json
│   └── it.json
├── src/
│   ├── app.py
│   ├── bot/
│   │   ├── handlers.py
│   │   └── error_handler.py
│   ├── config/
│   │   └── settings.py
│   ├── core/
│   │   ├── context_store.py
│   │   ├── model_preferences_store.py
│   │   └── rate_limiter.py
│   ├── i18n/
│   │   ├── __init__.py
│   │   └── service.py
│   ├── services/
│   │   └── ollama_client.py
│   └── utils/
│       ├── logging.py
│       └── telegram.py
├── tests/
│   ├── test_context_store.py
│   ├── test_context_store_sqlite.py
│   ├── test_i18n_service.py
│   ├── test_model_preferences_store.py
│   ├── test_rate_limiter.py
│   ├── test_settings.py
│   └── test_telegram_utils.py
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── CHANGELOG.md
├── CONTRIBUTING.md
└── pyproject.toml
```

## Phase 1 (MVP)

- [x] Core bot architecture and environment-based configuration.
- [x] Docker-first deployment with Compose and GHCR publish workflow.
- [x] Core conversation flow with contextual chat and error-safe Ollama calls.
- [x] Base command set and UX (`/start`, `/help`, `/health`, `/clear`, `/models`, `/currentmodel`).
- [x] Unified bot UI (slash commands + persistent quick buttons + inline actions).
- [x] Unified status messaging (`ℹ️ info`, `✅ success`, `⚠️ warning`, `❌ error`).
- [x] Per-user model management with SQLite persistence.
- [x] Access control with user whitelist (`ALLOWED_USER_IDS`).
- [x] Basic per-user rate limiting.
- [x] Healthcheck command and operational status checks.
- [x] Logging hardening for production observability.

## Phase 2: New features

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
- [x] Document upload and review support (TXT/MD/CSV/JSON/PDF) using the selected model.
- [x] Optional cloud-ready Ollama auth configuration (`OLLAMA_API_KEY`, `OLLAMA_AUTH_SCHEME`).
- [x] Localization support with user Telegram language resolution and English fallback.
- [x] Locale files available for `en`, `es`, `de`, `fr`, and `it`.

## Configuration

The stack configuration file is `docker-compose.yml`.

```yaml
services:
  bot:
    image: ${BOT_IMAGE}
    container_name: ${BOT_CONTAINER_NAME:-ollama-telegram-bot}
    restart: unless-stopped
    volumes:
      - ${BOT_DATA_DIR:-./data}:/data
    environment:
      TELEGRAM_BOT_TOKEN: ${TELEGRAM_BOT_TOKEN}
      OLLAMA_BASE_URL: ${OLLAMA_BASE_URL}
      OLLAMA_API_KEY: ${OLLAMA_API_KEY:-}
      OLLAMA_AUTH_SCHEME: ${OLLAMA_AUTH_SCHEME:-Bearer}
      OLLAMA_DEFAULT_MODEL: ${OLLAMA_DEFAULT_MODEL}
      OLLAMA_USE_CHAT_API: ${OLLAMA_USE_CHAT_API:-true}
      OLLAMA_KEEP_ALIVE: ${OLLAMA_KEEP_ALIVE:-5m}
      MODEL_PREFS_DB_PATH: ${MODEL_PREFS_DB_PATH:-/data/bot.db}
      ALLOWED_USER_IDS: ${ALLOWED_USER_IDS}
      LOG_LEVEL: ${LOG_LEVEL:-INFO}
      REQUEST_TIMEOUT_SECONDS: ${REQUEST_TIMEOUT_SECONDS:-60}
      MAX_CONTEXT_MESSAGES: ${MAX_CONTEXT_MESSAGES:-12}
      RATE_LIMIT_MAX_MESSAGES: ${RATE_LIMIT_MAX_MESSAGES:-8}
      RATE_LIMIT_WINDOW_SECONDS: ${RATE_LIMIT_WINDOW_SECONDS:-30}
      IMAGE_MAX_BYTES: ${IMAGE_MAX_BYTES:-5242880}
      DOCUMENT_MAX_BYTES: ${DOCUMENT_MAX_BYTES:-10485760}
      DOCUMENT_MAX_CHARS: ${DOCUMENT_MAX_CHARS:-12000}
      BOT_DEFAULT_LOCALE: ${BOT_DEFAULT_LOCALE:-en}
      TZ: ${TZ:-Europe/Madrid}
```

See `.env.example` for the complete list and example values.

- `BOT_IMAGE`: Docker image reference used by Compose (`registry/repo:tag`).
- `BOT_CONTAINER_NAME`: Name assigned to the running container.
- `TELEGRAM_BOT_TOKEN`: Bot token generated by `@BotFather`.
- `OLLAMA_BASE_URL`: Base URL of Ollama (for example `http://ollama:11434`, no `/v1`).
- `OLLAMA_API_KEY`: Optional API key for cloud/API-gateway Ollama endpoints.
- `OLLAMA_AUTH_SCHEME`: Authorization scheme for `OLLAMA_API_KEY` (default `Bearer`).
- `OLLAMA_DEFAULT_MODEL`: Model used by default when user has no custom selection.
- `OLLAMA_USE_CHAT_API`: Enables `/api/chat` as primary path with automatic generate fallback.
- `OLLAMA_KEEP_ALIVE`: Chat keep-alive hint sent to Ollama (for example `5m`).
- `MODEL_PREFS_DB_PATH`: SQLite database path inside container.
- `BOT_DATA_DIR`: Host path mounted to `/data` for persistence.
- `ALLOWED_USER_IDS`: Required comma-separated numeric Telegram user IDs.
- `LOG_LEVEL`: Logging verbosity (`DEBUG|INFO|WARNING|ERROR|CRITICAL`).
- `REQUEST_TIMEOUT_SECONDS`: Timeout for Ollama requests.
- `MAX_CONTEXT_MESSAGES`: Number of recent turns kept in memory per user.
- `RATE_LIMIT_MAX_MESSAGES`: Max user messages allowed inside the rate-limit window.
- `RATE_LIMIT_WINDOW_SECONDS`: Sliding window size (seconds) for rate limiting.
- `IMAGE_MAX_BYTES`: Maximum accepted image size in bytes for image analysis requests.
- `DOCUMENT_MAX_BYTES`: Maximum accepted document size in bytes.
- `DOCUMENT_MAX_CHARS`: Maximum extracted document characters sent to model context/review.
- `BOT_DEFAULT_LOCALE`: Fallback locale when user Telegram language is not available in bot locales.
- `TZ`: Timezone in IANA format (for example `Europe/Madrid`).

`ALLOWED_USER_IDS` is required and must contain at least one numeric Telegram user ID.
Bot replies are localized using each user's Telegram language when available; unsupported locales automatically fallback to English (`en`).
Current locale files: `locales/en.json`, `locales/es.json`, `locales/de.json`, `locales/fr.json`, and `locales/it.json`.
When uploading a document, you can add a caption instruction to review it immediately, or upload it without caption to keep it in context for later questions.

## Docker Compose (Fully Variable-Driven)

Deployment is designed to use:

- `.env` locally.
- Environment variables in Portainer (Stack > Environment variables).

### 1) Configure variables

```bash
cp .env.example .env
```

Edit `.env` with your values.

### 2) Start the stack

```bash
docker compose pull
docker compose up -d
```

## Local Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
python3 -m src.app
```

## Lint, Type Check, Tests

```bash
ruff check .
ruff format .
mypy src
python3 -m pytest -q
```

## GHCR Publish

The workflow in `.github/workflows/docker-publish.yml` publishes:

- `ghcr.io/artcc/ollama-telegram-bot:latest` (main branch)
- `ghcr.io/artcc/ollama-telegram-bot:sha-<commit>`
- `ghcr.io/artcc/ollama-telegram-bot:vX.Y.Z` (tags)

For private image pulls on server/Portainer:

```bash
echo "$GITHUB_TOKEN" | docker login ghcr.io -u YOUR_GITHUB_USER --password-stdin
```

The token must include at least `read:packages` permission.

## Documents

- [CHANGELOG.md](CHANGELOG.md)
- [CONTRIBUTING.md](CONTRIBUTING.md)

## 🎨 Bot Avatar

You can use the official bot avatar for your own instance:

<p align="left">
  <img src="https://github.com/ArtCC/ollama-telegram-bot/blob/main/assets/ollama-telegram-bot.png" alt="Ollama Telegram Bot Avatar" width="200">
</p>

To set this image as your bot's profile picture:
1. Right-click the image above and save it
2. Open [@BotFather](https://t.me/botfather) on Telegram
3. Send `/setuserpic`
4. Select your bot
5. Upload the downloaded image

## License

This project is licensed under the Apache License 2.0. See [LICENSE](LICENSE).

## Author

Arturo Carretero Calvo ([ArtCC](https://github.com/ArtCC))
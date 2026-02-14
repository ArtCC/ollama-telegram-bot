# Ollama Telegram Bot

[![Docker Publish](https://github.com/ArtCC/ollama-telegram-bot/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/ArtCC/ollama-telegram-bot/actions/workflows/docker-publish.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Docker Compose](https://img.shields.io/badge/Docker%20Compose-Ready-2496ED?logo=docker&logoColor=white)](docker-compose.yml)
[![GHCR](https://img.shields.io/badge/GHCR-ghcr.io%2Fartcc%2Follama--telegram--bot-181717?logo=github)](https://ghcr.io/artcc/ollama-telegram-bot)

Open-source Telegram bot to chat with Ollama models running on your server.

## Overview

- Telegram bot with async handlers and user-friendly error responses.
- Ollama integration with timeout, retries, and categorized failures.
- Docker-first deployment with environment-driven configuration.
- CI workflow for publishing container images to GHCR.

## Project Structure

```text
ollama-telegram-bot/
├── .github/
│   └── workflows/
│       └── docker-publish.yml
├── src/
│   ├── app.py
│   ├── bot/
│   │   ├── handlers.py
│   │   └── error_handler.py
│   ├── config/
│   │   └── settings.py
│   ├── core/
│   │   └── context_store.py
│   ├── services/
│   │   └── ollama_client.py
│   └── utils/
│       ├── logging.py
│       └── telegram.py
├── tests/
│   ├── test_context_store.py
│   └── test_telegram_utils.py
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── CHANGELOG.md
├── CONTRIBUTING.md
└── pyproject.toml
```

## Phase 1 (MVP)

Use this checklist to track Phase 1 progress.

- [x] Bot foundation and strict environment-based configuration.
- [x] Core commands: `/start`, `/help`, `/clear`.
- [x] Ollama integration with timeout, retry, and user-facing error handling.
- [x] Basic per-user in-memory conversation context.
- [ ] `/models` command for model listing and selection.
- [ ] User whitelist and basic rate limiting.
- [ ] Logging improvements and healthcheck endpoint/command.

## Telegram API Choices (MVP)

- Long polling (`run_polling`) for simpler deployment.
- Command registration with `set_my_commands`.
- `sendChatAction(typing)` before calling Ollama.
- Global error handler via `Application.add_error_handler`.
- Message splitting for Telegram's 4096-char limit.
- `drop_pending_updates=True` on startup to avoid stale backlog.

## Configuration

See `.env.example` for the complete list and example values.

Main variables:

- `TELEGRAM_BOT_TOKEN`
- `OLLAMA_BASE_URL`
- `OLLAMA_DEFAULT_MODEL`
- `REQUEST_TIMEOUT_SECONDS`
- `MAX_CONTEXT_MESSAGES`
- `LOG_LEVEL`

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
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
python -m src.app
```

## Lint, Type Check, Tests

```bash
ruff check .
ruff format .
mypy src
pytest -q
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

## License

This project is licensed under the Apache License 2.0. See [LICENSE](LICENSE).

## Author

Arturo Carretero Calvo ([ArtCC](https://github.com/ArtCC))
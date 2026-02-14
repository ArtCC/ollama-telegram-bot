# Contributing

Thanks for your interest in contributing.

## Getting started

1. Fork the repository.
2. Create a feature branch from `main`.
3. Set up a Python 3.12 virtual environment.
4. Install dependencies in editable mode with development tools.
5. Run linting, type checks, and tests before opening a pull request.

## Branch naming

Use clear branch names, for example:
- `feature/add-model-selection`
- `fix/ollama-timeout-message`
- `docs/update-deployment-guide`

## Commit messages

Use short, descriptive commits in imperative mood.

Examples:
- `Add retry handling for Ollama HTTP errors`
- `Update README deployment section`
- `Add tests for context trimming`

## Pull request checklist

Before submitting a pull request, please ensure:
- Code follows the existing project structure and style.
- Linting passes.
- Type checking passes.
- Tests pass.
- Documentation is updated when behavior changes.
- New environment variables are documented in `.env.example` and `README.md`.
- Changelog is updated under the appropriate version section.

## Coding guidelines

- Keep changes focused and minimal.
- Prefer clear names over short names.
- Handle user-facing errors with actionable messages.
- Avoid adding unrelated refactors in the same pull request.

## Reporting issues

When opening an issue, include:
- Expected behavior.
- Actual behavior.
- Steps to reproduce.
- Logs or screenshots if applicable.
- Environment details (OS, Docker/Portainer setup, Python version).

## Security

Please do not open public issues for sensitive vulnerabilities.
If you find a security issue, contact the maintainer privately first.

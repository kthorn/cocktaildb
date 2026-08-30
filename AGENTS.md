# Repository Guidelines

## Project Structure & Module Organization
- `api/` holds the FastAPI backend, including routes, models, and database layer (`api/db/`).
- `src/web/` contains the static frontend (HTML/CSS/JS) served via Caddy on EC2.
- `tests/` includes pytest suites plus fixtures.
- `packages/barcart/` is a standalone analytics package with its own tests and tooling.
- `infrastructure/` contains Ansible playbooks, Caddy config, PostgreSQL schema, and systemd services.
- `scripts/` provides deployment, config generation, and test DB helpers.
- `template.yaml` is a CloudFormation template for shared AWS resources (Cognito, S3, IAM).

## Build, Test, and Development Commands
- `aws cloudformation deploy --template-file template.yaml --stack-name cocktaildb-dev --capabilities CAPABILITY_NAMED_IAM` deploys AWS resources.
- `./scripts/local-config.sh` generates `src/web/js/config.js` for local dev.
- `./scripts/serve.sh` serves the frontend at `http://localhost:8000`.
- `npx live-server src/web --port=8000` runs live-reload for UI changes.
- `python -m pytest tests/ -v` runs API and integration tests.
- `pytest packages/barcart/tests/` runs analytics package tests.

## Formatting

- Requires Node 22.7 or newer; Node 22.22.2 is the tested version. The floor is required so `node --check` detects ESM syntax without a root `package.json`.
- Install hooks with `~/miniforge3/envs/cocktaildb/bin/python -m pip install pre-commit==4.6.2 && ~/miniforge3/envs/cocktaildb/bin/python -m pre_commit install`.
- Run every formatter check with `~/miniforge3/envs/cocktaildb/bin/python -m pre_commit run --all-files`.
- Format/check Python only with `~/miniforge3/envs/cocktaildb/bin/python -m pre_commit run ruff-format --all-files`.
- Format/check static frontend JS/MJS/HTML only with `~/miniforge3/envs/cocktaildb/bin/python -m pre_commit run prettier --all-files`.
- Ruff and Prettier editor extensions use `ruff.toml` and `.prettierrc`; CI is authoritative.

## Coding Style & Naming Conventions
- Python: Ruff formats code with 4-space indentation; use `snake_case` for functions/variables and `PascalCase` for classes.
- JavaScript: Prettier formats static frontend code; follow existing vanilla JS style and naming in `src/web/js/`.
- Barcart uses `ruff` for lint/format (`packages/barcart/pyproject.toml`).
- Prefer small, focused modules and keep API responses in `api/models/`.

## Testing Guidelines
- Framework: `pytest` with unit, integration, and CRUD suites in `tests/`.
- Integration/CRUD tests expect a fixture DB at `tests/fixtures/test_cocktaildb.db`.
- Name new tests as `test_*.py` and keep fixtures in `tests/conftest.py`.

## Commit & Pull Request Guidelines
- Commit messages follow a conventional style like `feat: ...`, `refactor: ...`, `docs: ...`.
- Use `PR_DESCRIPTION.md` as the PR template; include a brief summary and test plan.
- If you run `./scripts/local-config.sh`, revert `src/web/js/config.js` before committing.

## Security & Configuration Tips
- AWS credentials must remain local; do not commit secrets or `.env` files.
- Migrations that reinitialize the DB (e.g., `--force-init`) are destructive; confirm intent.
- EC2 SSH keys should be stored securely in `~/.ssh/` with 600 permissions.

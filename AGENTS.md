# Repository Guidelines

## Project Structure & Module Organization
- `api/` holds the FastAPI backend, including routes, models, and database layer (`api/db/`).
- `src/web/` contains the vanilla multi-page frontend source; Vite builds it into ignored `dist/web/` for Caddy.
- `tests/` includes pytest suites plus fixtures.
- `packages/barcart/` is a standalone analytics package with its own tests and tooling.
- `infrastructure/` contains Ansible playbooks, Caddy config, PostgreSQL schema, and systemd services.
- `scripts/` provides artifact build/preview, deployment, config generation, and test DB helpers.
- `template.yaml` is a CloudFormation template for shared AWS resources (Cognito, S3, IAM).

## Build, Test, and Development Commands
- `aws cloudformation deploy --template-file template.yaml --stack-name cocktaildb-dev --capabilities CAPABILITY_NAMED_IAM` deploys AWS resources.
- Node 22.22.2 is the tested frontend runtime. The root package is intentionally typeless: existing CommonJS `.js` scripts remain executable while Node syntax detection handles frontend ESM.
- `npm ci && npm run build && npm run test:build` builds and checks the configuration-free artifact with the committed lockfile.
- `./scripts/local-config.sh` generates `src/web/js/config.js` for local dev.
- `./scripts/serve.sh` runs Vite at strict `http://localhost:8000`.
- Optional SSR development runs FastAPI on port 8001 with `FRONTEND_ASSET_MODE=development`; browse recipe/ingredient/sitemap routes through Vite on port 8000.
- `npm run preview -- dist /path/to/config.js` previews a disposable config-injected copy without mutating `dist/`.
- `/home/kurtt/miniforge3/envs/cocktaildb/bin/python -m pytest tests/ -v` runs API and integration tests.
- `/home/kurtt/miniforge3/envs/cocktaildb/bin/python -m pytest packages/barcart/tests/` runs analytics package tests.

## Formatting

- Frontend builds require Node 22.12.0 or newer because the pinned Vite 8.3.0 declares that floor; Node 22.22.2 is the tested version. The root package remains typeless so existing CommonJS scripts and Node's formatter-era 22.7+ syntax detection for frontend ESM continue to execute; the build/artifact test asserts both modes.
- Install hooks with `~/miniforge3/envs/cocktaildb/bin/python -m pip install pre-commit==4.6.2 && ~/miniforge3/envs/cocktaildb/bin/python -m pre_commit install`.
- Run every formatter check with `~/miniforge3/envs/cocktaildb/bin/python -m pre_commit run --all-files`.
- Format/check Python only with `~/miniforge3/envs/cocktaildb/bin/python -m pre_commit run ruff-format --all-files`.
- Format/check static frontend JS/MJS/HTML and all YAML (Ansible, Compose, CloudFormation, CI) with `~/miniforge3/envs/cocktaildb/bin/python -m pre_commit run prettier --all-files`. `api/templates/*.html` is excluded because those are Jinja2 templates.
- Format/check shell with `~/miniforge3/envs/cocktaildb/bin/python -m pre_commit run shfmt --all-files`. Its style comes from the hook's own args, not `.prettierrc`: `-i 4 -ci` matches `tabWidth: 4` and indents `case` bodies. Do not add `*.md` to the prettier hook yet — the specs under `docs/superpowers/` are under active edit and a repo-wide markdown reformat would conflict with every open workstream.
- Ruff and Prettier editor extensions use `ruff.toml` and `.prettierrc`; CI is authoritative. `.prettierrc` governs every format Prettier touches, including YAML: 4-space indent, single quotes, 100-column print width.

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

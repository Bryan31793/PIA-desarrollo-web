# Repository Guidelines

## Project Structure & Module Organization

This client-server gym application uses a Python 3.14 FastAPI backend and a React/TypeScript client; current endpoints provide role-based JWT authentication for members and employees, public member registration, membership registration with mandatory cash payment by staff, temporary QR passes for gym check-ins, and ADMIN-only plan management and employee registration.

- `client/`: React + TypeScript SPA with Vite, role-specific screens, QR generation/scanning, and a typed API client with token rotation. Development proxies /auth and /api to BACKEND_URL; production Nginx proxies to backend:8000.
- `scripts/client_e2e_server.py`: isolated backend fixture server for browser tests; requires TEST_DATABASE_URL and cleans its schema/Redis namespace on shutdown.
- `app/main.py`: application setup and PostgreSQL pool lifespan. Token validation and authorization run through endpoint dependencies, without authentication middleware.
- `app/routers/`: HTTP endpoints and shared error handlers.
- `app/services/`: authentication logic and token rotation.
- `app/infrastructure/auth/`: JWT operations and Redis token persistence.
- `app/infrastructure/members/`: PostgreSQL member persistence through Psycopg.
- `app/infrastructure/employees/`: PostgreSQL employee registration, credentials, and role lookup.
- `app/routers/plans.py` and `app/services/plan_service.py`: ADMIN-only plan creation and partial PATCH updates; price validation is in backend schemas. Migration `006_plan_price_validation_backend.sql` removes the old price CHECK.
- `app/routers/employees.py` and `app/services/employee_service.py`: ADMIN-only registration of ADMIN/STAFF employees with Argon2 passwords and fixed roles.
- `app/infrastructure/memberships/`, `app/infrastructure/plans/`, and `app/infrastructure/payments/`: membership persistence, plan price/duration lookup, and payment persistence.
- `app/services/membership_service.py`: registers membership and payment in one shared PostgreSQL transaction. Start date is today in America/Monterrey; `end_date = start_date + duration_days`. The service charges the exact positive plan price; no client-supplied amounts or discounts.
- `app/services/access_service.py` and `app/infrastructure/access/`: 120-second single-use passes, regeneration invalidation, and atomic check-in logging in PostgreSQL. Both generation and scanning require an active member account and current membership; only one check-in per member per America/Monterrey calendar day is allowed; both generation and scanning check the history under the member lock.
- `app/routers/access.py`: MEMBER-only `POST /api/access-passes` and STAFF-only `POST /api/check-ins`; migration `005_access_passes.sql` creates the required tables.
- `app/routers/memberships.py`: `POST /api/memberships`, restricted to `Role.STAFF` (not `ADMIN`).
- `app/core/roles.py` and `app/core/identity.py`: fixed roles and authenticated identities.
- `app/infrastructure/database/db.py`: process-wide synchronous Psycopg pool with explicit open/close lifecycle; `get_connection()` borrows connections and commits/rolls back before returning them. Shared transactions across repositories remain unchanged.
- `app/core/` and `app/schemas/`: configuration, domain exceptions, and Pydantic request/response models.
- `tests/`: pytest tests; `migrations/`: numbered SQL scripts such as `001_init.sql`.
- `Dockerfile`, `client/Dockerfile`, and `compose.yaml`: backend, client/Nginx, PostgreSQL, and Redis setup. Client runs on port 5173 and API on 8000.

## Build, Test, and Development Commands

Run commands from the repository root:

- `poetry install`: install runtime and development dependencies into `.venv`.
- `docker compose up --build`: build the backend image and start all services with backend reload enabled.
- `poetry run uvicorn app.main:app --reload`: run locally after exporting `JWT_SECRET`; provide Redis for token persistence.
- `poetry run python -m pytest`: run the test suite.
- `poetry run ruff check .`: lint Python code.
- `poetry run ruff format .`: format Python code; review the resulting diff.

Client commands (Node.js 24), also from the repository root:

- `npm --prefix client ci`: install locked client dependencies.
- `npm --prefix client run dev`: start Vite on port 5173 with API proxy.
- `npm --prefix client run build`: check TypeScript and build production assets.
- `npm --prefix client test`: run API client tests with Vitest.
- `npm --prefix client run test:e2e`: run Playwright against the isolated backend/Vite servers documented in `client/README.md`.
- `npm --prefix client run format:check`: check client formatting.

The API runs on port 8000; interactive documentation is available at `/docs`.

## Coding Style & Naming Conventions

Use four-space indentation, `snake_case` for functions/modules, `PascalCase` for classes, and `UPPER_SNAKE_CASE` for constants. Follow existing type annotations and explicit Pydantic models. Keep HTTP handling in routers, business rules in services, and persistence in infrastructure. Ruff is included without repository-specific configuration.

## Testing Guidelines

Name files `tests/test_*.py` and functions `test_*`. Tests exercise the ASGI stack directly or through FastAPI's TestClient and use pytest fixtures, parametrization, and monkeypatching without a running server or Redis. PostgreSQL registration and membership integration tests are optional: set `TEST_DATABASE_URL` to a migrated test database; they create and remove an isolated schema. Cover authentication failures, token expiry, role restrictions, refresh rotation, validation responses, and successful access when changing these flows. Membership tests also cover inclusive date overlap, concurrent insert conflicts, foreign keys, duration calculation, exact plan pricing, and rollback of membership/payment together. QR tests cover pass expiration/replacement, daily entry limits and midnight reset, eligibility, transactional rollback, and concurrent generation/scanning. Admin tests cover partial updates, price validation before persistence, authorization, duplicate names/emails, employee login, and preservation of membership/payment history. Pool tests cover connection reuse, commit/rollback, exhaustion, stale connection replacement, lifecycle, and 503 responses. Unit fixtures avoid real pools; integration fixtures close each schema-specific pool before dropping its schema. Client tests cover token rotation, failure handling, exact price/PATCH payloads, and a real-browser MEMBER/STAFF/ADMIN flow against isolated PostgreSQL/Redis data. Use the configured test backend for browser tests, never production accounts. No coverage threshold is configured.

## Commit & Pull Request Guidelines

History contains short messages such as `refresh auth` and `gitignore`; no formal convention is established. Write concise, action-oriented subjects. PRs should describe changed behavior, link relevant issues, and report test/lint results. Include request/response examples for API changes and configuration or migration instructions when applicable.

## Security & Configuration

Copy `.env.example` to `.env` and set `DB_PASSWORD` and a `JWT_SECRET` of at least 32 bytes. Compose reads these values; local execution requires exported variables, including `DATABASE_URL` for member registration and login. Apply SQL migrations before registering members. Never commit secrets. Registration hashes passwords with Argon2; login authenticates active accounts by email (the OAuth2 form's `username` field) against PostgreSQL and requires Redis to persist issued tokens. `POST /auth/login` is for members; `POST /auth/employees/login` is for employees. Access tokens include a server-assigned `Role` (`admin`, `staff`, or `member`) and a stable `sub` (`member:<id>` or `employee:<id>`). Refresh checks the account is still active and rotates tokens. Roles are fixed: migration `003_immutable_employee_roles.sql` prevents changing an employee's role or renaming a role. Protect each private endpoint with `verify_access_token` or `require_roles`; the `/api` prefix does not provide automatic protection. See `docs/authentication.md` for examples and compatibility changes. `POST /api/memberships` accepts only member_id and plan_id, derives employee_id from the STAFF token, and records mandatory cash payment at the plan price. See `docs/membership-registration.md`. QR access returns opaque QR content for the frontend, never JWT credentials; only SHA-256 token hashes are stored. See `docs/gym-access.md`. ADMIN-only `POST /api/plans`, `PATCH /api/plans/{plan_id}`, and `POST /api/employees` are documented in `docs/admin.md`.

## Documentation maintenance

- Keep AGENTS.md aligned with the current project architecture.
- When making significant architectural changes, review
  whether AGENTS.md needs updating.
- Do not update AGENTS.md for minor implementation changes.
- Preserve existing instructions unless they are obsolete.

## Client architecture

Keep UI in `client/src/components` and `client/src/pages`, API contracts/session handling in `client/src/lib`, and business authorization in FastAPI. The client uses existing endpoints; the API has no member/plan list endpoints, so staff and admin forms use IDs. Tokens stay in memory and tab-scoped sessionStorage; never store passwords. Do not persist QR codes or tokens in logs. Use relative /auth and /api URLs through the same-origin proxy. Price strings preserve decimal precision and PATCH omits empty fields. Camera usage requires HTTPS or localhost; image/manual scanning remains available. See `client/README.md`.

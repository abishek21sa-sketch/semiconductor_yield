# Security

## Scope and posture

This is a portfolio/demo decision-intelligence app, not a hardened production service. It's designed to run locally or in a controlled demo environment (career fair laptop, local Docker). See `DEPLOYMENT.md` for what's explicitly not production-ready (single shared API key rather than real user auth, no rate limiting, no TLS).

## Data

Both datasets bundled in `data/` are public research data with no PII and no secrets:

- **SECOM** (UCI ML Repository #179): anonymized semiconductor fab sensor readings and pass/fail outcomes. No identifying information of any kind -- sensors are numbered, not named.
- **SMT2020** (`data/smt2020_lvhm/`): a published academic semiconductor-fab simulation benchmark (Kopp, Hassoun, Kalir & Mönch, *IEEE TSM*, 2020). Synthetic/benchmark routing and reliability data representing a fab archetype, not a real company's operational data. See `data/smt2020_lvhm/ATTRIBUTION.md`.

Neither dataset requires or should ever be paired with real credentials, customer data, or proprietary fab data.

## Secrets

None are committed to this repository:

- `gurobi.lic` (a Gurobi license file, if you use a real one instead of the bundled free tier) is explicitly gitignored -- it's tied to your personal/academic license terms.
- `API_KEY` (see below) and `fab_app.db` (the local SQLite file) are also gitignored. `API_KEY` is read from an environment variable only; it is never logged, and the request-timing middleware in `api/main.py` logs the path and status code, never headers or bodies.
- `docker-compose.yml`'s Postgres credentials (`fab`/`fab`) are a local-dev-only default for the containerized demo, not a real secret -- don't reuse them anywhere that matters, and override `DATABASE_URL` for any deployment beyond a local demo.

## Authentication

`/api/*` routes are open by default (no `API_KEY` env var set) so a local run or a career-fair laptop demo needs zero setup. Setting `API_KEY` turns on a real check (`api/auth.py`): every request must carry a matching `X-API-Key` header or gets a 401. This is a single shared secret, not user-level authentication or authorization -- adequate for gating one demo instance, not a substitute for real auth (OAuth/JWT, per-user identity) if this ever serves multiple distinct users or untrusted traffic. `/api/health` is always unauthenticated (it's what Docker's `HEALTHCHECK` polls, which has no key).

## Known limitations

- Every `/api/*` endpoint is unrate-limited even when `API_KEY` is set. Fine for `localhost` or a trusted local network; do not expose to the public internet as-is.
- Input validation exists only on `/api/yield/theory`'s numeric parameters and `/api/history`'s `limit` (clamped server-side to 200). Other endpoints take no user input beyond a path parameter validated against a fixed allowlist (`/api/scenario/{name}`), so injection surface is minimal, but this hasn't been through a formal security review.
- The Docker image runs as the default root user (no `USER` directive). For a demo/local image this is a minor concern; hardening it (non-root user, read-only filesystem) would be a reasonable next step before any internet-facing deployment.

## Reporting

This is a personal portfolio project. If you find something concerning, open an issue on the repository.

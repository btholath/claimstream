# Spec: Frontend (Streamlit)

## Purpose
Provides a browser UI over the claims microservices for demoing and manually
exercising the pipeline: submit a claim, watch it move through the event
trail, review AI-generated RCA reports, and check service health.

This service owns no business logic and no state. It is a thin client that
talks to backend services exclusively over REST/HTTP, exactly as any
external caller would. It must remain replaceable without touching any
backend service.

## Dependencies (external services called)

| Env var | Points to | Used for |
|---|---|---|
| `INTAKE_URL` | intake service | Submitting claims, polling claim status |
| `PAYOUT_URL` | payout service | Health check only (for now) |
| `GRAFANA_URL` | Grafana | Outbound link only, not called from the backend |
| `RCA_REPORTS_DIR` | mounted volume, read-only | Reading generated RCA markdown files |

No service URL is hardcoded in the app — all come from environment
variables set in `docker-compose.yml`, so the frontend can point at a
different environment (e.g. a future staging stack) without a code change.

## Pages / tabs

### Submit claim
A form collecting `policy_number`, `claimant_name`, `amount`, `claim_type`,
and an optional `description`. On submit, POSTs to `{INTAKE_URL}/claims`.

- On success (`200`/`201`/`202`): show the returned `claim_id`, store it in
  session state, and prompt the user to switch to the Track tab.
- On a non-2xx response: show the response body as an error, not a raw
  exception.
- On a connection failure: show which URL was unreachable, not a stack trace.

### Track claim
Takes a claim ID (pre-filled from the last submission if available) and
GETs `{INTAKE_URL}/claims/{id}`.

- Renders the raw claim JSON and a human-readable event timeline built from
  the claim's `events` array.
- Optional auto-refresh (every 3s) so a claim's progress through
  intake → validate → fraud → payout is visible without manual re-clicking.
- A claim ID that returns 404 shows a clear "not found" message, not a
  crash.

### RCA reports
Lists `.md` files in `RCA_REPORTS_DIR`, most recent first, and renders the
selected one as markdown.

- If no reports exist yet, shows instructions for generating one
  (`chaos/inject_fault.py` then `rca/generate_rca.py`) rather than an empty
  page.
- Read-only — this tab never writes to the reports directory.

### Operations
Health-check panel hitting `{INTAKE_URL}/health` and `{PAYOUT_URL}/health`,
rendered as up/down indicators. Includes an outbound link to Grafana.

- A service that's down or unreachable shows "down," not an unhandled
  exception that breaks the page.

## Acceptance criteria
- [ ] No backend URL is hardcoded — all four come from environment variables with sane defaults for local dev.
- [ ] Every backend call is wrapped so a connection failure renders a readable error in the UI instead of a Streamlit crash/traceback.
- [ ] Submitting a claim with the intake service down shows a clear error, not a silent failure.
- [ ] The Track tab correctly renders zero, one, and many events without layout breaking.
- [ ] The RCA tab handles an empty `rca/reports/` directory gracefully.
- [ ] The app starts and serves on port 8501 inside its container with no manual setup beyond `docker compose up`.
- [ ] The frontend container has no dependency on any backend service being *built* first — only on it being *reachable* at runtime (`depends_on` in compose is enough; no build-time coupling).

## Out of scope
- Authentication/authorization (single-user local demo tool for now — note this explicitly if you ever consider deploying it beyond a demo)
- Any direct database or event-bus access — the frontend talks to services only, never to Postgres or Redis directly
- Editing or deleting RCA reports from the UI

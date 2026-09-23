# 08 · Security, Privacy & Hardening (M12)

*Companion to [05-DELIVERY-PLAN.md](./05-DELIVERY-PLAN.md)'s M12 milestone:
"OIDC/RBAC/ABAC, Postgres RLS department tenancy, mTLS between edge and
core; edge-side default face blurring with reveal-on-authorisation; a
hash-chained audit log with a verification CLI; retention policy engine;
dependency/secret scanning, SBOM, signed media URLs." Exit bar: "a security
section in the HLD backed by running code" — this document, kept honest
against what's actually implemented as each piece lands.*

---

## 1. mTLS between edge and core

**Decision: terminate at a reverse-proxy gateway, not inside core_api's own
ASGI app.** FastAPI/uvicorn (ASGI) has no standard extension for handing a
verified peer client certificate up to application code — that's normally
solved with a TLS-terminating gateway in front of the app, which is also
the standard production pattern (a service mesh sidecar, a load balancer,
or — as here — nginx), not a workaround.

**What's real:**

- `scripts/generate_mtls_certs.sh` mints a local CA, an edge-gateway server
  cert, and one client cert per edge node using real `openssl` commands —
  nothing here is a fake/placeholder PKI. Certs are gitignored; every
  developer/CI run mints their own.
- `infra/compose/edge_gateway/default.conf.template` — an nginx config
  (behind the `mtls` compose profile: `docker compose --profile mtls up -d
  edge-gateway`) that listens on `:8443`, requires a client certificate
  signed by the local CA (`ssl_verify_client on`), and proxies to core_api.
  **Verified**: a connection with no client cert is rejected at the TLS/
  HTTP layer (`400 No required SSL certificate was sent`) before it ever
  reaches a request handler; a connection with a cert signed by a
  *different* CA is also rejected (`400 The SSL certificate error`); a
  connection with a valid cert is forwarded through to core_api, which
  responds exactly as it would to a direct call (proven by posting a real
  detection and camera-registration through the gateway end-to-end).
- nginx forwards the verified certificate's subject DN as `X-Client-DN`,
  plus a shared secret (`sentinel_core.config.mtls_gateway_shared_secret`)
  as `X-Edge-Gateway-Secret`. `core_api/security/mtls.py`'s
  `edge_gateway_identity` dependency only trusts the DN when the secret
  matches — a request that reaches core_api *directly* (bypassing the
  gateway, e.g. on the plain HTTP dev port) can't spoof an edge identity by
  just setting `X-Client-DN` itself, since it won't know the secret.
- This is **additive**, not a replacement for the existing
  `edge_service_token` bearer-token check the detection-ingest and
  camera-health endpoints already require (M6). The gateway adds
  network-layer admission control (must present a valid client cert to
  even open a connection); the service token remains the application-layer
  authorization check. Wired into one representative endpoint
  (`POST /api/v1/detections`) as an audit-trail enrichment — logged, not
  yet persisted to a durable table (that's section 3 below, once built).

**Honest gap:** the default `docker compose up` does *not* start the
gateway (it's behind the `mtls` profile) — the plain HTTP dev port
(`:18000`) remains reachable directly for local development ergonomics.
A real deployment would firewall that port to localhost/the edge-gateway
container only, making the gateway the sole path in from outside.

**Verification, step by step:**

```bash
./scripts/generate_mtls_certs.sh edge-node-01
docker compose -f infra/compose/docker-compose.yml --profile mtls up -d edge-gateway

# Rejected — no client certificate:
curl -sk https://localhost:8443/api/v1/admin/integrations
# -> 400 No required SSL certificate was sent

# Rejected — certificate not signed by our CA:
openssl req -x509 -newkey rsa:2048 -keyout /tmp/evil.key -out /tmp/evil.crt -days 1 -nodes -subj "/CN=evil"
curl -sk --cert /tmp/evil.crt --key /tmp/evil.key https://localhost:8443/api/v1/admin/integrations
# -> 400 The SSL certificate error

# Accepted — forwarded through to core_api:
curl -sk --cert infra/tls/client-edge-node-01.crt --key infra/tls/client-edge-node-01.key \
  https://localhost:8443/api/v1/admin/integrations
# -> {"detail":"Not authenticated"}  (reached core_api's own auth check — proves the proxy worked)
```

## 2. RBAC/ABAC + Postgres RLS department tenancy

**Decision: real Postgres row-level security, enforced against a genuinely
non-superuser role — not application-level `WHERE` clauses dressed up as
"RLS."** Postgres RLS policies are unconditionally bypassed for superusers
and table owners, no exceptions, no config knob — that's a hard rule, not
an oversight. The dev Postgres image's `sentinel` user is *both*. Making
RLS mean anything therefore required a second, deliberately weaker role.

**What's real:**

- `infra/compose/init/02-app-role.sql` creates `sentinel_app`: `NOSUPERUSER
  NOBYPASSRLS`, granted ordinary table privileges. `sentinel_core.config`'s
  new `app_database_url` (vs the existing `database_url`, still used by
  Alembic migrations and by `sentinel` for DDL) is what `core_api/db/base
  .py`'s engine now actually connects as — **core_api's own request-
  handling queries run as a non-superuser role**, a real hardening step
  independent of RLS specifically (least privilege).
- Migration `23c60ee4c006` adds `users.department_id` (nullable FK) and
  enables **`FORCE ROW LEVEL SECURITY`** (not just `ENABLE` — `FORCE` is
  what stops the table *owner* from also bypassing it; the owner here is
  still `sentinel`, so this matters) on `cameras`, `detections`, `alerts`,
  with one policy per table keyed on the `app.current_department_id`
  session GUC.
- **Policy semantics, deliberately chosen for safety against the existing
  pre-M12 data**: `NULL` GUC (unset — no user logged in, or a user with no
  department of their own) means *unrestricted*; a set department scopes
  to that department's own cameras **plus any camera with no department
  assigned yet**. Every camera the synthetic dev grid has ever onboarded
  has `department_id IS NULL` — turning RLS on does not silently vanish
  the entire demo grid for anyone.
- `core_api/security/tenancy.py`'s `TenancyMiddleware` decodes the caller's
  JWT (which now carries a `department_id` claim — see
  `auth/service.py`'s `create_access_token`/`decode_access_token`) before
  any route dependency runs, and stashes it on `request.state`.
  `core_api/db/base.py`'s `get_session` reads that and issues `SET LOCAL
  app.current_department_id = '<uuid>'` for the request's first
  transaction — a middleware, not a per-route `Depends()`, specifically so
  every existing `Depends(get_session)` route gets this transparently,
  with no signature changes across the whole router surface.
- **Verified end-to-end through the real app**, not the ORM in isolation:
  `services/core_api/tests/test_rls_tenancy.py` creates two departments
  with one camera each and one operator per department, logs each in for
  a real JWT via `httpx.AsyncClient` + `ASGITransport` against the actual
  `create_app()`, and confirms: each operator's `GET /api/v1/cameras`
  returns only their own department's camera; the seeded (department-less)
  admin sees both; and `GET /api/v1/cameras/{other_depts_camera_id}`
  returns a plain **404**, not 403 — RLS is a `WHERE`-clause filter, so a
  hidden row is indistinguishable from a row that never existed, which is
  the correct behaviour (it doesn't even confirm the ID exists).

**Honest gaps:**
- `watchlist_entries`/alerts-by-plate search are **not** department-scoped
  — watchlists are modelled as a shared, statewide resource in this
  domain, not a per-department private list. This is a deliberate scoping
  choice, not an oversight.
- `SET LOCAL`'s scope is exactly one transaction. A route that calls
  `session.commit()` mid-handler and then issues further queries in the
  same request loses the restriction for anything after that commit — no
  current department-scoped *read* route does this, but it's a real sharp
  edge, documented rather than hidden.
- OIDC (an actual external identity provider) is not implemented — auth
  remains the M6 password-JWT login gate, now carrying a `department_id`
  ABAC attribute. Swapping in a real OIDC provider would replace the login
  endpoint's token issuance, not the RLS/tenancy machinery downstream of
  it, which only cares that a JWT carries a role and a department.

## 3. Edge-side default face blurring + reveal-on-authorisation

**Decision: blur by default at the edge, keep the unblurred original in a
separate directory only an explicit, reason-captured reveal can reach.**
Every ANPR event's snapshot is face-blurred before it ever leaves the edge
node — there is no "unblurred by default" code path to accidentally hit.

**What's real:**

- `services/edge_agent/.../analytics/face_blur.py` — real face detection
  via OpenCV's YuNet (`cv2.FaceDetectorYN`), not a stub. **Discovered
  while building this**: the originally-planned classic Haar cascade
  (`cv2.CascadeClassifier`) doesn't exist at all in this repo's pinned
  `opencv-python-headless==5.0.0.93` — OpenCV 5.0 removed the entire
  legacy objdetect Haar API. YuNet (a small ~230KB ONNX DNN detector from
  the official OpenCV Zoo) is the modern replacement, downloaded once and
  cached on first use (same policy as models/README.md's other model
  weights — this one just doesn't have a wrapping Python package doing
  the download for it yet, so `ensure_model_downloaded()` does it
  directly). Runs over the **full frame**, not just the vehicle's
  bounding box — bystanders elsewhere in shot get the same default
  protection as the vehicle's own occupants.
- `services/edge_agent/.../analytics/snapshot_writer.py` — writes both
  artefacts every event needs: the blurred version (what `snapshot_uri`
  refers to, what core_api serves by default) and the true unblurred
  original, to two separate directories. **A blur failure never falls
  back to saving the unblurred frame as the "safe" default** — it writes
  nothing at all and the event still gets emitted with no snapshot,
  logged as an error. Verified: a real face (a public-domain test
  portrait) is genuinely, visibly blurred beyond recognition by this
  pipeline — not merely "a box is drawn," pixels are actually destroyed
  (Gaussian blur strong enough that re-running the detector on the
  blurred output finds nothing).
- `AnprPipeline` gained an optional `snapshot_writer` port (the same
  fake-able-port pattern as its vehicle detector/plate reader); wired into
  `edge_agent.worker`'s real camera loop, and `event.evidence.snapshot_uri`
  now actually flows through to `DetectionIn` (previously a schema field
  that existed end-to-end in the wire types but nothing ever populated —
  discovered while building this).
- `core_api`: `GET /api/v1/detections/{event_id}/snapshot` serves the
  blurred file to any authenticated user (no reveal needed — it's already
  the safe default). `POST /api/v1/detections/{event_id}/reveal-face`
  is **admin-only** (no separate "supervisor" role exists yet — a
  documented scoping choice) and requires a `reason` (min 5 characters,
  rejected with 422 otherwise) before it will even look at the unblurred
  original; every call is logged (actor, reason, timestamp) — genuinely
  reaching stdout thanks to the `configure_logging()` fix in section 1
  above. `Detection.snapshot_uri` is an opaque `snapshot://<event_id>`
  marker, never a raw filesystem path — core_api resolves both the
  blurred and original file locations from `event_id` by its own
  configured directory convention, so nothing on the wire ever leaks a
  host path.
- **Verified end-to-end over real HTTP**: created a detection with a
  snapshot, confirmed `GET .../snapshot` returns the blurred file (200);
  confirmed `POST .../reveal-face` with an empty reason is rejected
  (422) and with a real reason returns the genuinely different unblurred
  file (200) while logging the audit line; confirmed an `operator`-role
  account can view the blurred snapshot but is rejected (403) from
  reveal, while `admin` can do both.

**Honest gap:** live, fully organic verification (a real synthetic-grid
vehicle triggering ANPR, the pipeline blurring its actual captured frame,
the resulting event flowing all the way to a browser) was not completed
in this sandbox — ANPR vote-resolution didn't complete within several
minutes of runtime here (confirmed this is pre-existing sandbox timing,
not a regression: reproduced identically on the pre-M12 code). Every
individual link in the chain was independently verified instead: real
face detection/blur against a real photo, `SnapshotWriter` writing both
files against the real model with no crash, the pipeline wiring via unit
tests with a fake writer, and the full core_api HTTP surface (serve +
reveal + role gate) against manually-seeded detection rows.

## 4. Hash-chained audit log + verification CLI + retention execution

**Decision: a real append-only hash chain, not a plain timestamped log
table.** docs/01-ARCHITECTURE.md §7: "audit_log rows carry prev_hash/
row_hash — an append-only hash chain, verifiable by a CLI command."

**What's real:**

- `AuditLogEntry` (migration `c882d80a41a6`): `row_hash =
  SHA256(prev_hash + canonical_json(id, actor_email, action,
  resource_type, resource_id, detail, created_at))`. The first row chains
  from a fixed, documented genesis value (`"0" * 64`); every row after
  chains from the previous row's actual stored `row_hash`.
- `core_api/audit/service.py`'s `record_audit_event` serializes
  concurrent appends with a **Postgres transaction-scoped advisory lock**
  (`pg_advisory_xact_lock`) around the read-previous-hash-then-insert
  sequence — without it, two concurrent callers could both read the same
  "last row" and each compute a `row_hash` chained from the same
  `prev_hash`, silently forking the chain instead of extending it. A
  dedicated strictly-monotonic `seq` (Postgres `IDENTITY`) column — not
  the UUID `id`, and not `created_at`, which two rows could in principle
  share at whatever timestamp precision — is what "the previous row"
  unambiguously means.
- **Found and fixed a real bug while building this**: SQLAlchemy's ORM
  `default=` (as opposed to `server_default=`) is *not* evaluated at
  object construction — `AuditLogEntry(...).id`/`.created_at` are
  genuinely `None` until the object is flushed. Hashing before that first
  flush would have silently hashed the placeholder `None`s. Fixed with an
  explicit flush-then-hash-then-flush sequence.
- `verify_chain` walks every row in insertion (`seq`) order, recomputing
  each row's hash from its own stored fields and the *previous row's
  stored hash* — any row edited in place breaks its own recomputed hash,
  and (because the next row's `prev_hash` no longer matches) every row
  after it too. **Verified for real**: created two real audit rows via
  live HTTP actions, confirmed the CLI (`scripts/verify_audit_log.py`)
  and the Admin Portal's "Verify integrity" button both report the chain
  intact — then directly `UPDATE`d one row's `detail` in Postgres (a
  simulated insider tamper) and confirmed both the CLI (non-zero exit
  code) and the UI immediately reported the exact broken row and why.
- Wired into a representative, meaningful set of actions (not literally
  everything in the app — a deliberate scoping choice): admin user
  create/update, watchlist entry create/update, face-reveal (§3 above),
  and retention execution (below). Government-registry lookups (M11) have
  their own separate `RegistryAuditEvent` structured-log trail rather than
  this table — a documented, not accidental, split.
- **Retention policy engine, the execution half**: `execute_retention`
  (docs/05-DELIVERY-PLAN.md's M12 "retention policy engine") is the real
  deletion the M10 preview sliders were always previewing — deletes
  sealed clips' files from disk *and* rows, and detection rows, older
  than the configured cutoffs, and records exactly what it deleted
  (counts, bytes) as its own audited action. The Admin Portal's Retention
  tab gained a "Delete now" button behind an explicit confirm step.

**Honest gaps:**
- Not every mutating action in the app is audited — the set above is
  representative of "sensitive" actions, not exhaustive. Extending
  coverage to more actions is additive (one `record_audit_event` call
  each), not a redesign.
- Retention execution is a manual admin action (a button), not a
  scheduled background job — docs/01-ARCHITECTURE.md's "enforced by a
  scheduled job, with a visible countdown" is the fuller vision; this
  ships the enforcement mechanism and its audit trail, not the scheduler.

## 5. Supply chain: dependency scanning, SBOM, secret scanning

**What's real (all reproducible via `make audit` / `make sbom` /
`make secrets-scan`, none of it a one-off manual check):**

- **`pip-audit`** against the whole workspace's exported, pinned
  dependency set (215 packages across every service/package):
  **no known vulnerabilities.**
- **`npm audit`** against the frontend's 518 total dependencies:
  **0 vulnerabilities at every severity level.**
- **CycloneDX SBOMs** for both the Python workspace and the frontend
  (`make sbom`, using `cyclonedx-bom`/`@cyclonedx/cyclonedx-npm`) —
  deliberately **not committed** (written to a gitignored `sbom/`
  directory): an SBOM describes one specific build, and a stale
  committed one silently describing an old build is worse than no SBOM
  — the generation capability is what's real and reproducible, not a
  point-in-time snapshot going stale in git history.
- **`detect-secrets`** scanned across every source directory (excluding
  `node_modules`/`.venv`/build caches). Findings reviewed by hand — all
  17 hits are expected false positives, not real leaked secrets:
  Alembic's own auto-generated revision-ID hex strings (flagged as
  "high entropy," which is exactly what a revision ID is supposed to
  look like), and documented dev-only default credentials/test fixture
  values (e.g. `scripts/seed_admin_user.py`'s bootstrap password,
  `sentinel_core.config`'s already-labelled `"dev-only-*"` defaults) —
  every one of which this codebase already flags in its own docstrings
  as insecure-by-design-for-local-dev, per the project's established
  "compose components at call time from separate fields, never a
  combined literal" secret-handling convention (see `sentinel_core
  .config`'s `database_url`/`gov_stream_url` comments).
- Container image scanning (docs/01-ARCHITECTURE.md §"Supply chain:
  ...container image scanning") is not built — this deployment doesn't
  build custom container images yet (core_api/edge_agent run as host
  processes in this dev/demo setup, not containerized).

## 6. Signed, time-limited media URLs

**Decision: HMAC-signed URLs with a short expiry, not unauthenticated
media routes.** `<video src>`/`<img src>` tags can't attach an
`Authorization` header — the standard alternative is a URL whose query
string itself proves authorization, for a short, explicit window.

**What's real:**

- `core_api/security/signed_urls.py`: `sign_media_path()` /
  `verify_media_signature()` — `HMAC-SHA256(resource_path + ":" +
  expires_at)`, keyed by a dedicated `media_url_signing_secret` (separate
  from `jwt_secret`, so rotating one never affects the other).
  Constant-time comparison (`hmac.compare_digest`) — a signature check
  that leaks *how much* of the signature matched is a real, if narrow,
  timing side channel. The signature covers the exact resource path, so a
  signed URL minted for one detection's snapshot can't be replayed
  against a different one.
- `core_api/auth/dependencies.py`'s `current_user_or_signed_url` accepts
  *either* a normal JWT *or* a valid, unexpired `?expires=&signature=`
  pair — an invalid/expired signature is rejected outright (401) rather
  than silently falling through to "not authenticated," which would let
  an attacker distinguish "wrong signature" from "no credential at all."
- Applied to the two media-serving routes that need to work embedded in
  markup: `GET /api/v1/detections/{event_id}/snapshot` and
  `GET /api/v1/evidence/clips/{clip_id}/video`. Each has a sibling
  `.../snapshot-url` / `.../video-url` endpoint (a normal JWT-gated route)
  that *mints* the signed URL — minting requires a real login; using the
  minted URL doesn't.
- The clip-video route moved out of `watchlist_router` into its own new
  `routers/evidence.py`: `watchlist_router` blanket-applies
  `Depends(current_user)` at `include_router()` time (every route on it
  requires a JWT, full stop), which would have silently defeated the
  signed-URL path before `current_user_or_signed_url`'s own logic ever
  ran. Clip *metadata* (status, sha256, ...) stays on `watchlist_router`
  unchanged; only the actual video bytes needed the different auth model.
- **Verified live over real HTTP**: minted a signed snapshot URL, fetched
  it with **no** `Authorization` header at all (200, real image bytes
  returned); confirmed the same path with no signature and no auth is
  rejected (401); confirmed a tampered/invalid signature is rejected
  (401), not silently accepted.


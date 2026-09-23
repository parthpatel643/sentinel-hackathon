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


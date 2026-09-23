# M15 Fresh-clone test

docs/05-DELIVERY-PLAN.md's M15 asks for a "fresh-clone test ... proves the
quickstart actually works on a machine that is not yours". The point is to
catch the class of bug where a project only builds because of something
untracked sitting in the author's working directory.

**Result: the README quickstart works from a clean checkout.** One real bug was
found and fixed by doing this (see §3).

Run on: macOS, Apple Silicon, 2026-09-23.

---

## 1. Method

```bash
git clone --branch dev/m4-m6-live-ui <repo> /tmp/sentinel-freshclone
cd /tmp/sentinel-freshclone
```

The clone carries no `.env`, no `node_modules`, no `.venv`, no generated
media — `.env` is gitignored, so the fresh checkout starts with exactly what a
reviewer would receive.

Each quickstart step was then executed in order, in the clone.

## 2. What was verified

| Step | Command | Result |
|---|---|---|
| Dependencies | `make install` | Pass — `uv sync --all-packages` plus 437 npm packages, **0 vulnerabilities** |
| Database schema | `alembic current` | Pass — reports head `6943898d1be1` |
| Operator login | `make seed` | Pass — idempotent, correctly reported the existing account |
| Full gate | `make check` | Pass — **359 tests**, mypy clean over 147 files, ruff clean |
| Frontend build | `npm run build` | Pass — `tsc -b` + Vite, no errors |
| Scripts | `synthetic_grid.py --help`, `chaos_drill.py --list` | Pass — both resolve their imports from the clone |

## 3. The bug this caught

`make api` bound port **18080**, while `apps/web/.env` and
`sentinel_core.config`'s `core_api_url` both default to **18000**.

Anyone following the README would have started the API on a port that neither
the operator console nor the edge worker was configured to talk to, and got a
stack whose own components could not reach each other — with no error message
pointing at the cause. It had gone unnoticed because every process in this
project's development had been started by hand on 18000, never through the
documented target.

Fixed in the same pass, with a comment on the target explaining why the number
is load-bearing rather than arbitrary.

## 4. What this test did *not* cover

- **`make up` was not run in the clone.** The infrastructure stack binds fixed
  host ports (15432, 16379, 14222, 19000, 8554, 8888, 9997) and one was already
  running for the evidence work; two stacks cannot hold the same ports. The
  clone's `make check` did run against that live infrastructure, which proves
  the clone's own code and configuration reach a real Postgres/PostGIS
  correctly — but it does not prove `docker compose up` from a truly cold
  machine with no images pulled.
- **A different machine.** This is a clean *checkout*, not clean *hardware*.
  Homebrew-provided `ffmpeg`, Docker itself, `uv` and Node were already
  installed, and the README names them as prerequisites rather than installing
  them. A reviewer without them will have to install them first.

Both are stated rather than glossed: "fresh clone on this machine" is a weaker
claim than "fresh machine", and the difference is exactly the kind of thing
this document exists to be honest about.

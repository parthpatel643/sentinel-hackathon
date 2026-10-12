#!/usr/bin/env bash
# One command to bring Sentinel up for the demo, from a fresh clone or a
# machine that has run it before, and one to take it down cleanly.
#
#   ./scripts/demo.sh up        start everything (the default)
#   ./scripts/demo.sh status    what is running, cameras live, gateway connections
#   ./scripts/demo.sh down      stop it all; ALL=1 also stops Docker
#
# Settings, as environment variables (or `make demo SOURCE=... CAMERAS=...`):
#
#   SOURCE=gov        where analysed video comes from: gov (the live government
#                     grid, the default), mirror (the recorded copy in
#                     data/gov-mirror), or registry (whatever is onboarded)
#   CAMERAS=cam06,cam30
#                     the cameras analysed (the default for gov and mirror;
#                     registry analyses everything onboarded unless set). On
#                     the government grid every
#                     analysed camera draws on one viewing quota per account;
#                     two last roughly two hours, four under one.
#   SAMPLED_FPS=4  STRIDE=3
#                     analysis rate per camera (see GETTING-STARTED.md §4)
#   SYNC=1            onboard every camera in the government catalogue (gov only)
#   RESET=1           start from an empty database (backed up first)
#   WATCH="GJ03MH7800:wanted:critical,GJ39C8018:stolen:high"
#                     watchlist entries to arm: plate:type:priority
#   PHONE=1           also serve the console to phones: a Cloudflare quick tunnel
#                     to the API, and the console deployed to Vercel built
#                     against it. Needs `cloudflared` and `npx vercel login`.
#                     The API is then on the internet, so it runs with
#                     SENTINEL_ENVIRONMENT=prod: secrets are generated into
#                     .env and the admin password is changed (printed below).
#   VERCEL_PROJECT=sentinel-console
#   OPEN=0            do not open Safari at the end
#   INSTALL=1         re-run `make install` even if dependencies are present
#
# Everything started is recorded in var/demo/ (pids, logs, URLs), so `down`
# stops exactly what `up` started. The worker is stopped first and given time
# to release its relay paths: a worker killed with -9 leaves the relay dialling
# the government gateway, quietly spending the quota.
set -euo pipefail

cd "$(dirname "$0")/.."
REPO=$(pwd)
STATE_DIR="$REPO/var/demo"
STATE="$STATE_DIR/state.env"
PY="$REPO/.venv/bin/python"
GOV_HOST=103.250.160.189
PUBLISHED_PASSWORD=sentinel-admin-2026
ADMIN_EMAIL=admin@sentinel-platform.com

SOURCE=${SOURCE:-gov}
CAMERAS=${CAMERAS:-}
[[ -z $CAMERAS && $SOURCE != registry ]] && CAMERAS=cam06,cam30
SAMPLED_FPS=${SAMPLED_FPS:-4}
STRIDE=${STRIDE:-3}
SYNC=${SYNC:-1}
RESET=${RESET:-0}
WATCH=${WATCH:-}
PHONE=${PHONE:-0}
VERCEL_PROJECT=${VERCEL_PROJECT:-sentinel-console}
OPEN=${OPEN:-1}
INSTALL=${INSTALL:-0}

bold=$'\033[1m'; dim=$'\033[2m'; red=$'\033[31m'; green=$'\033[32m'; amber=$'\033[33m'; off=$'\033[0m'
step() { printf '\n%s== %s%s\n' "$bold" "$*" "$off"; }
ok() { printf '   %s✓%s %s\n' "$green" "$off" "$*"; }
warn() { printf '   %s!%s %s\n' "$amber" "$off" "$*"; }
die() { printf '\n%s✗ %s%s\n' "$red" "$*" "$off" >&2; exit 1; }

# --- small helpers -----------------------------------------------------------

env_value() { # the value of KEY in .env, or nothing
  [[ -f .env ]] || return 0
  grep -E "^$1=" .env | tail -1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' || true
}

set_env_value() { # set KEY=VALUE in .env, replacing any earlier line
  local tmp
  tmp=$(mktemp)
  [[ -f .env ]] && grep -vE "^$1=" .env > "$tmp" || true
  printf '%s=%s\n' "$1" "$2" >> "$tmp"
  mv "$tmp" .env
  chmod 600 .env
}

alive() { [[ -f "$STATE_DIR/$1.pid" ]] && kill -0 "$(cat "$STATE_DIR/$1.pid")" 2>/dev/null; }

start_bg() { # name, command...: run detached, logging to var/demo/<name>.log
  local name=$1
  shift
  nohup "$@" > "$STATE_DIR/$name.log" 2>&1 &
  echo $! > "$STATE_DIR/$name.pid"
}

stop_bg() { # name, seconds to wait, then force (1) or only warn (0)
  local name=$1 wait=${2:-10} force=${3:-1} pid
  alive "$name" || { rm -f "$STATE_DIR/$name.pid"; return 0; }
  pid=$(cat "$STATE_DIR/$name.pid")
  kill "$pid" 2>/dev/null || true
  for _ in $(seq 1 "$wait"); do
    kill -0 "$pid" 2>/dev/null || break
    sleep 1
  done
  if kill -0 "$pid" 2>/dev/null && [[ $force == 1 ]]; then
    kill -9 "$pid" 2>/dev/null || true
    sleep 1
  fi
  if kill -0 "$pid" 2>/dev/null; then
    warn "$name (pid $pid) did not stop in ${wait}s; stop it by hand: kill $pid"
  else
    ok "$name stopped"
    rm -f "$STATE_DIR/$name.pid"
  fi
}

wait_for() { # seconds, description, command...
  local seconds=$1 what=$2
  shift 2
  for _ in $(seq 1 "$seconds"); do
    "$@" > /dev/null 2>&1 && return 0
    sleep 1
  done
  return 1
}

json() { # python expression over `d`, the JSON on stdin; CAMS holds $CAMERAS
  CAMS="$CAMERAS" "$PY" -c "import json, os, sys; d = json.load(sys.stdin); cams = os.environ['CAMS'].split(','); print($1)"
}

api_token() {
  curl -sf -X POST http://127.0.0.1:18000/api/v1/auth/login -H 'Content-Type: application/json' \
    -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PW\"}" | json 'd["access_token"]'
}

gateway_connections() {
  lsof -nP -iTCP@"$GOV_HOST" -sTCP:ESTABLISHED 2>/dev/null | grep -c ESTABLISHED || true
}

port_busy() { lsof -nP -iTCP:"$1" -sTCP:LISTEN > /dev/null 2>&1; }

admin_password() {
  local stored
  stored=$(env_value SENTINEL_DEMO_ADMIN_PASSWORD)
  echo "${stored:-$PUBLISHED_PASSWORD}"
}

# --- up ------------------------------------------------------------------------

preflight() {
  step "Checking this machine"
  local missing=()
  for tool in docker uv node npm ffmpeg curl lsof openssl; do
    command -v "$tool" > /dev/null || missing+=("$tool")
  done
  [[ $PHONE == 1 ]] && ! command -v cloudflared > /dev/null && missing+=(cloudflared)
  ((${#missing[@]} == 0)) || die "missing: ${missing[*]}. See GETTING-STARTED.md §1 (brew install ffmpeg node cloudflared; uv from astral.sh)."
  ok "tools present"

  if ! docker info > /dev/null 2>&1; then
    warn "Docker is not running; starting it"
    open -a OrbStack 2> /dev/null || open -a Docker 2> /dev/null || true
    wait_for 90 docker docker info || die "Docker did not start. Start OrbStack or Docker Desktop, then run this again."
  fi
  ok "Docker running"

  case $SOURCE in gov | mirror | registry) ;; *) die "SOURCE must be gov, mirror or registry" ;; esac
  if [[ $SOURCE == gov ]]; then
    [[ -n $(env_value SENTINEL_GOV_ACCESS_EMAIL) && -n $(env_value SENTINEL_GOV_ACCESS_PASSWORD) ]] \
      || die "SOURCE=gov needs SENTINEL_GOV_ACCESS_EMAIL and SENTINEL_GOV_ACCESS_PASSWORD in .env (cp .env.example .env)."
  fi
  if [[ $SOURCE == mirror && ! -f data/gov-mirror/catalogue.json ]]; then
    die "SOURCE=mirror needs data/gov-mirror/ (copy it from the machine that recorded it)."
  fi

  local others
  others=$(pgrep -f "edge_agent.worker" | tr "\n" " " || true)
  [[ -z $others ]] || die "an edge worker is already running (pid ${others% }). Stop it first; ./scripts/demo.sh down stops one this script started."
  for port in 18000 5173; do
    port_busy "$port" && die "port $port is in use. Stop the API/console running there (or ./scripts/demo.sh down)."
  done
  ok "nothing else running"
  if [[ $SOURCE == gov ]]; then
    warn "the viewing quota is per account: make sure no other machine is pulling with these credentials"
  fi
}

install_dependencies() {
  step "Dependencies"
  if [[ $INSTALL == 1 || ! -x $PY || ! -d apps/web/node_modules ]]; then
    make install
  fi
  ok "Python and console dependencies installed"
  if [[ ! -f models/weights/yolo11n.onnx ]]; then
    echo "   exporting the vehicle detector (one-off, ~1 min)"
    uv run --isolated --with ultralytics --with onnx python scripts/export_models.py
  fi
  uv run -q --package edge-agent python scripts/prefetch_models.py > "$STATE_DIR/models.log" 2>&1 \
    || die "model check failed; see var/demo/models.log (the first run needs internet)."
  ok "models ready (cached for offline use)"
}

start_infrastructure() {
  step "Infrastructure"
  make up > "$STATE_DIR/compose.log" 2>&1 || die "make up failed; see var/demo/compose.log"
  wait_for 120 postgres sh -c "docker compose -f infra/compose/docker-compose.yml ps postgres --format '{{.Health}}' | grep -q healthy" \
    || die "Postgres did not become healthy; see: make logs"
  wait_for 30 relay curl -sf http://127.0.0.1:9997/v3/paths/list || die "the media relay is not answering on :9997"
  ok "Postgres, NATS, Valkey and the relay are up"

  if [[ $RESET == 1 ]]; then
    CONFIRM=yes ./scripts/reset_db.sh | sed 's/^/   /'
  else
    (cd services/core_api && uv run -q --project ../.. alembic upgrade head > "$STATE_DIR/migrate.log" 2>&1) \
      || die "database migration failed; see var/demo/migrate.log"
  fi
  ok "database schema current"
  if [[ $SOURCE == mirror ]]; then
    uv run -q python scripts/gov_mirror.py start > "$STATE_DIR/mirror.log" 2>&1 || die "could not start the mirror; see var/demo/mirror.log"
    echo "MIRROR_STARTED=1" >> "$STATE"
    ok "replaying the recorded grid into the relay"
  fi
}

secure_for_internet() {
  step "Hardening for the internet (PHONE=1)"
  local key value
  for key in SENTINEL_JWT_SECRET SENTINEL_EDGE_SERVICE_TOKEN SENTINEL_MTLS_GATEWAY_SHARED_SECRET SENTINEL_MEDIA_URL_SIGNING_SECRET; do
    value=$(env_value "$key")
    if [[ -z $value || $value == dev-only-* ]]; then
      set_env_value "$key" "$(openssl rand -hex 32)"
    fi
  done
  ok "secrets set in .env (not the published development ones)"
  if [[ $(admin_password) == "$PUBLISHED_PASSWORD" ]]; then
    set_env_value SENTINEL_DEMO_ADMIN_PASSWORD "sentinel-$(openssl rand -hex 4)"
  fi
  ok "admin password changed from the published one"
}

set_admin_login() {
  ADMIN_PW=$(admin_password)
  uv run -q --package core_api python scripts/seed_admin_user.py \
    --email "$ADMIN_EMAIL" --password "$ADMIN_PW" --reset-password > "$STATE_DIR/seed.log" 2>&1 \
    || die "could not set the admin login; see var/demo/seed.log"
}

start_tunnel_and_deploy() {
  step "Phone access: tunnel and Vercel"
  npx -y vercel@latest whoami > "$STATE_DIR/vercel.log" 2>&1 \
    || die "not logged in to Vercel. Run: npx vercel login   (then this again)"

  start_bg tunnel cloudflared tunnel --no-autoupdate --url http://127.0.0.1:18000
  local url=""
  for _ in $(seq 1 45); do
    url=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$STATE_DIR/tunnel.log" | head -1 || true)
    [[ -n $url ]] && break
    sleep 1
  done
  [[ -n $url ]] || die "the Cloudflare tunnel did not start; see var/demo/tunnel.log"
  echo "TUNNEL_URL=$url" >> "$STATE"
  ok "API tunnel: $url"

  echo "   deploying the console to Vercel, built against the tunnel (about a minute)"
  (
    cd apps/web
    if [[ ! -f .vercel/project.json ]]; then
      npx -y vercel@latest link --yes --project "$VERCEL_PROJECT" >> "$STATE_DIR/vercel.log" 2>&1
    fi
    npx -y vercel@latest deploy --prod --yes --build-env "VITE_API_BASE_URL=$url"
  ) >> "$STATE_DIR/vercel.log" 2>&1 || die "Vercel deployment failed; see var/demo/vercel.log"
  # The production alias is the shortest *.vercel.app URL the CLI reports.
  local phone
  phone=$(grep -oE 'https://[a-zA-Z0-9.-]+\.vercel\.app' "$STATE_DIR/vercel.log" | awk '{ print length, $0 }' | sort -n | head -1 | cut -d' ' -f2)
  [[ -n $phone ]] || die "could not find the deployment URL in var/demo/vercel.log"
  ALL_ORIGINS=$(grep -oE 'https://[a-zA-Z0-9.-]+\.vercel\.app' "$STATE_DIR/vercel.log" | sort -u | tr '\n' ' ')
  echo "PHONE_URL=$phone" >> "$STATE"
  ok "console deployed: $phone"
}

start_api_and_console() {
  step "API and console"
  local origins='"http://localhost:5173","http://127.0.0.1:5173"'
  local environment=local
  if [[ $PHONE == 1 ]]; then
    environment=prod
    for origin in $ALL_ORIGINS; do origins="$origins,\"$origin\""; done
  fi
  start_bg api env SENTINEL_ENVIRONMENT="$environment" SENTINEL_CORS_ALLOW_ORIGINS="[$origins]" \
    "$REPO/.venv/bin/uvicorn" core_api.app:app --host 127.0.0.1 --port 18000 --timeout-graceful-shutdown 5
  wait_for 60 api curl -sf http://127.0.0.1:18000/api/v1/health \
    || die "the API did not start; see var/demo/api.log"
  ok "API on http://localhost:18000 (environment: $environment)"

  start_bg web sh -c "cd '$REPO/apps/web' && exec ./node_modules/.bin/vite --port 5173 --strictPort"
  wait_for 60 web curl -sf http://localhost:5173 || die "the console did not start; see var/demo/web.log"
  ok "console on http://localhost:5173"

  if [[ $PHONE == 1 ]]; then
    local tunnel
    tunnel=$(grep '^TUNNEL_URL=' "$STATE" | cut -d= -f2-)
    wait_for 60 tunnel curl -sf "$tunnel/api/v1/health" || die "the API is not reachable through the tunnel ($tunnel)"
    ok "API reachable from the internet through the tunnel"
  fi
}

onboard() {
  step "Cameras and watchlist"
  local token
  token=$(api_token) || die "could not sign in as $ADMIN_EMAIL"
  case $SOURCE in
    gov)
      uv run -q python scripts/verify_gov_catalogue.py > "$STATE_DIR/catalogue.log" 2>&1 \
        || die "the government catalogue refused these credentials; see var/demo/catalogue.log"
      ok "government credentials accepted"
      if [[ $SYNC == 1 ]]; then
        local result
        result=$(curl -sf -X POST http://127.0.0.1:18000/api/v1/cameras/discover -H "Authorization: Bearer $token") \
          || die "catalogue sync failed"
        ok "catalogue synced: $(echo "$result" | json '"%d cameras (%d new, %d updated)" % (d["fetched"], len(d["onboarded"]), len(d["updated"]))')"
      fi
      ;;
    mirror)
      uv run -q python scripts/gov_mirror.py register > "$STATE_DIR/register.log" 2>&1 || die "could not register the mirrored cameras"
      ok "mirrored cameras registered"
      ;;
    registry) ok "analysing whatever is onboarded (Cameras → Add camera / Import)" ;;
  esac

  local entry plate kind priority
  IFS=',' read -r -a entries <<< "$WATCH"
  for entry in "${entries[@]:-}"; do
    [[ -n $entry ]] || continue
    IFS=':' read -r plate kind priority <<< "$entry"
    curl -sf -X POST http://127.0.0.1:18000/api/v1/watchlist -H "Authorization: Bearer $token" \
      -H 'Content-Type: application/json' \
      -d "{\"plate\":\"$plate\",\"entry_type\":\"${kind:-bolo}\",\"priority\":\"${priority:-high}\",\"case_reference\":\"DEMO\"}" > /dev/null \
      && ok "watchlist: $plate (${kind:-bolo}, ${priority:-high})" || warn "could not arm $plate"
  done
}

start_worker() {
  step "Edge worker"
  local args=(--source "$SOURCE" --sampled-fps "$SAMPLED_FPS" --frame-stride "$STRIDE")
  if [[ -n $CAMERAS ]]; then args+=(--cameras "$CAMERAS"); fi
  start_bg worker "$PY" -m edge_agent.worker "${args[@]}"
  ok "analysing ${CAMERAS:-every onboarded camera} from $SOURCE (log: var/demo/worker.log)"
  if [[ -z $CAMERAS ]]; then
    ok "it picks up cameras as they are onboarded (every 30 s)"
    return 0
  fi

  local token live=0 want
  token=$(api_token)
  want=$(echo "$CAMERAS" | tr ',' '\n' | grep -c . || true)
  printf '   waiting for the cameras to go live'
  for _ in $(seq 1 30); do
    alive worker || { echo; die "the worker stopped; see var/demo/worker.log"; }
    live=$(curl -sf http://127.0.0.1:18000/api/v1/cameras -H "Authorization: Bearer $token" \
      | json "sum(1 for c in d if c['camera_id'] in cams and c['status'] == 'live')" 2> /dev/null || echo 0)
    [[ $live -ge $want ]] && break
    printf '.'
    sleep 3
  done
  echo
  if [[ $live -ge $want ]]; then ok "$live of $want analysed cameras live"; else warn "$live of $want analysed cameras live so far; check ./scripts/demo.sh status"; fi
  if grep -qiE '403|401|watch time limit' "$STATE_DIR/worker.log"; then
    warn "the gateway refused a stream (403/401): the quota may be spent. Stop, wait 15–20 min, start again."
  fi
}

print_summary() {
  step "Ready"
  echo "   Console      http://localhost:5173   (Safari: H.265 cameras do not play in Chrome)"
  echo "   Sign in      $ADMIN_EMAIL / $ADMIN_PW"
  if [[ $PHONE == 1 ]]; then
    local phone
    phone=$(grep '^PHONE_URL=' "$STATE" | cut -d= -f2-)
    echo "   Phone        $phone/field   (console: $phone)"
    echo "                live video plays on the laptop only; the phone gets alerts, lookup, routes"
    uv run -q --isolated --with qrcode python -c "import qrcode; q = qrcode.QRCode(border=1); q.add_data('$phone/field'); q.print_ascii(invert=True)" 2> /dev/null || true
  fi
  [[ $SOURCE == gov ]] && echo "   Gateway      $(gateway_connections) connection(s) open (one per analysed camera, plus open video tiles)"
  echo "   Status       ./scripts/demo.sh status        Stop: ./scripts/demo.sh down"
  echo "   Logs         var/demo/*.log"
  if [[ $OPEN == 1 ]]; then open -a Safari http://localhost:5173 2> /dev/null || true; fi
}

up() {
  mkdir -p "$STATE_DIR"
  preflight
  : > "$STATE"
  { echo "SOURCE=$SOURCE"; echo "CAMERAS=$CAMERAS"; echo "PHONE=$PHONE"; } >> "$STATE"
  install_dependencies
  start_infrastructure
  [[ $PHONE == 1 ]] && secure_for_internet
  set_admin_login
  ALL_ORIGINS=""
  [[ $PHONE == 1 ]] && start_tunnel_and_deploy
  start_api_and_console
  onboard
  start_worker
  print_summary
}

# --- status and down -------------------------------------------------------------

status() {
  [[ -f $STATE ]] || die "nothing started by this script (no var/demo/state.env)"
  ADMIN_PW=$(admin_password)
  step "Processes"
  for name in worker api web tunnel; do
    if alive "$name"; then ok "$name running (pid $(cat "$STATE_DIR/$name.pid"))"
    elif [[ -f $STATE_DIR/$name.log ]]; then warn "$name not running (log: var/demo/$name.log)"; fi
  done
  step "Cameras"
  local token
  CAMERAS=$(grep '^CAMERAS=' "$STATE" | cut -d= -f2-)
  if token=$(api_token 2> /dev/null); then
    curl -sf http://127.0.0.1:18000/api/v1/cameras -H "Authorization: Bearer $token" | json '"\n".join(
      ["   %d registered, %d live" % (len(d), sum(c["status"] == "live" for c in d))]
      + ["   %-8s %-8s %5s fps  %s" % (c["camera_id"], c["status"], "%.1f" % c["measured_fps"] if c.get("measured_fps") else "-", c["name"])
         for c in d if c["camera_id"] in cams])'
  else
    warn "API not answering"
  fi
  step "Government gateway"
  echo "   $(gateway_connections) connection(s) open"
  if [[ -f $STATE_DIR/worker.log ]] && tail -200 "$STATE_DIR/worker.log" | grep -qiE '403|401|watch time limit'; then
    warn "recent 403/401 in the worker log: the quota may be spent"
  fi
  grep -E '^(TUNNEL_URL|PHONE_URL)=' "$STATE" | sed 's/^/   /' || true
}

down() {
  step "Stopping"
  # Never forced: a worker killed with -9 cannot release its relay paths.
  stop_bg worker 25 0
  stop_bg api 10
  stop_bg web 5
  stop_bg tunnel 5
  if [[ -f $STATE ]] && grep -q '^MIRROR_STARTED=1' "$STATE"; then
    uv run -q python scripts/gov_mirror.py stop > /dev/null 2>&1 && ok "mirror replay stopped"
  fi
  if [[ ${ALL:-0} == 1 ]]; then
    make down > /dev/null 2>&1 && ok "Docker stack stopped"
  fi
  echo "   gateway connections now open: $(gateway_connections)"
  rm -f "$STATE"
}

case ${1:-up} in
  up) up ;;
  status) status ;;
  down) down ;;
  *) die "usage: $0 [up|status|down]" ;;
esac

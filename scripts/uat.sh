#!/usr/bin/env bash
# The automated half of the M4 user-acceptance test (docs/11-M4-UAT.md).
# Every step's full output is kept in var/uat/<timestamp>/, with a summary
# in report.md, so the run itself is the evidence.
#
# Needs: `make up`, `make api` running, and `make seed` once, in the local
# environment (the capacity step logs in with the seeded account).
# Usage: make uat            (about 25 minutes, most of it the capacity curve)
#        make uat QUICK=1    (skips the capacity curve)
set -uo pipefail

OUT="var/uat/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$OUT"
REPORT="$OUT/report.md"
API="${SENTINEL_CORE_API_URL:-http://127.0.0.1:18000}"
failures=0

{
  echo "# M4 UAT, automated checks"
  echo
  echo "| | |"
  echo "|---|---|"
  echo "| Host | $(scutil --get ComputerName 2>/dev/null || hostname) |"
  echo "| Chip | $(sysctl -n machdep.cpu.brand_string 2>/dev/null || uname -m), $(sysctl -n hw.ncpu 2>/dev/null) cores |"
  echo "| Memory | $(( $(sysctl -n hw.memsize 2>/dev/null || echo 0) / 1073741824 )) GB |"
  echo "| Commit | $(git rev-parse --short HEAD) |"
  echo "| Started (UTC) | $(date -u +%FT%TZ) |"
  echo
  echo "| Step | Result | Log |"
  echo "|---|---|---|"
} > "$REPORT"

step() {
  local name="$1" log="$2"
  shift 2
  echo "== $name"
  if "$@" > "$OUT/$log" 2>&1; then
    echo "| $name | pass | \`$log\` |" >> "$REPORT"
    echo "   pass"
  else
    echo "| $name | **FAIL** | \`$log\` |" >> "$REPORT"
    echo "   FAIL (see $OUT/$log)"
    failures=$((failures + 1))
  fi
}

if ! curl -fsS "$API/api/v1/health" > /dev/null; then
  echo "The API is not answering at $API. Start it with \`make api\` (and \`make up\` first)." >&2
  exit 1
fi

step "Doctor (stack, models, relay)" doctor.log make doctor
step "Lint and format" lint.log make lint
step "Type check" types.log make types
step "Backend and edge test suite" pytest.log uv run pytest -q
step "Web type check and build" web-build.log bash -c "cd apps/web && npm run build"
step "Web UI tests (Playwright)" web-ui.log bash -c "cd apps/web && npm run test:ui"
step "DR drill: backup, restore, audit chain" dr-drill.log make dr-drill

if [ -z "${QUICK:-}" ]; then
  step "Capacity, tier B at 8 fps" capacity-b8.log \
    uv run --package core_api python scripts/measure_tier_capacity.py --tier b_sampled --cameras 2 4 6 8
  step "Capacity, tier B at 4 fps" capacity-b4.log \
    uv run --package core_api python scripts/measure_tier_capacity.py --tier b_sampled --sampled-fps 4 --cameras 4 8 12
  step "Capacity, tier A at stride 3" capacity-a3.log \
    uv run --package core_api python scripts/measure_tier_capacity.py --tier a_continuous --stride 3 --cameras 1 2 4
  {
    echo
    echo "## Capacity (verdict per camera count)"
    echo
    echo '```'
    grep -h -E "^-- |analysed fps" "$OUT"/capacity-*.log
    echo '```'
    echo
    echo "A run *keeps up* when every camera is live, analysed fps is at least 80% of"
    echo "target and lag over the last third of the run is under 5 s. Use the largest"
    echo "camera count that keeps up to set tiers and SAMPLED_FPS (runbook §6)."
  } >> "$REPORT"
  # A capacity step "passes" by running; whether a count keeps up is the result.
fi

{
  echo
  echo "Finished (UTC): $(date -u +%FT%TZ). Failed steps: $failures."
  echo
  echo "Now do the hands-on checks in docs/11-M4-UAT.md and record them alongside."
} >> "$REPORT"

echo
cat "$REPORT"
exit "$failures"

#!/usr/bin/env bash
# E2E test for the Yandex OAuth login flow against a mock Yandex server.
#
# Prerequisites:
#   - the compose stack is up with the gateway pointed at the mock:
#       YANDEX_OAUTH_BASE_URL=http://host.docker.internal:9500 \
#       YANDEX_USERINFO_URL=http://host.docker.internal:9500/info \
#       docker compose up -d gateway
#   - the mock is running on the host:  python3 e2e/mock_yandex.py 9500
#
# Usage: bash e2e/test_yandex_oauth.sh

set -euo pipefail

BASE="${BASE:-http://localhost:8000}"
JAR="$(mktemp)"
trap 'rm -f "$JAR"' EXIT

fail() { echo "FAIL: $1" >&2; exit 1; }
pass() { echo "ok: $1"; }

# 1. /auth/yandex/login redirects to the provider with a state
LOCATION=$(curl -s -o /dev/null -w '%{redirect_url}' "$BASE/auth/yandex/login")
[[ "$LOCATION" == *"/authorize?"* ]] || fail "login did not redirect to authorize: $LOCATION"
STATE=$(sed -n 's/.*state=\([^&]*\).*/\1/p' <<<"$LOCATION")
[[ -n "$STATE" ]] || fail "no state in authorize URL"
pass "login redirects to provider with state"

# 2. Callback with a wrong state is rejected
LOCATION=$(curl -s -o /dev/null -w '%{redirect_url}' \
  "$BASE/auth/yandex/callback?code=e2e-auth-code&state=forged")
[[ "$LOCATION" == *"oauth_error=state"* ]] || fail "forged state was accepted: $LOCATION"
pass "forged state rejected"

# 3. Callback with the right code+state logs in and sets a session cookie
LOCATION=$(curl -s -c "$JAR" -o /dev/null -w '%{redirect_url}' \
  "$BASE/auth/yandex/callback?code=e2e-auth-code&state=$STATE")
[[ "$LOCATION" == *"/web/tasks"* ]] || fail "callback did not land on /web/tasks: $LOCATION"
grep -q "session" "$JAR" || fail "no session cookie set"
pass "callback logs in and redirects to /web/tasks"

# 4. The state is one-time: replaying the same callback fails
LOCATION=$(curl -s -o /dev/null -w '%{redirect_url}' \
  "$BASE/auth/yandex/callback?code=e2e-auth-code&state=$STATE")
[[ "$LOCATION" == *"oauth_error=state"* ]] || fail "state replay was accepted: $LOCATION"
pass "state is one-time"

# 5. The session actually works: /auth/me returns the OAuth user
ME=$(curl -s -b "$JAR" "$BASE/auth/me")
grep -q '"username":"e2e.tester"' <<<"$ME" || fail "/auth/me mismatch: $ME"
pass "/auth/me returns the OAuth user"

# 6. Second login with the same Yandex account reuses the user (no duplicate)
LOCATION=$(curl -s -o /dev/null -w '%{redirect_url}' "$BASE/auth/yandex/login")
STATE2=$(sed -n 's/.*state=\([^&]*\).*/\1/p' <<<"$LOCATION")
JAR2="$(mktemp)"
curl -s -c "$JAR2" -o /dev/null \
  "$BASE/auth/yandex/callback?code=e2e-auth-code&state=$STATE2"
ME1_ID=$(sed -n 's/.*"id":\([0-9]*\).*/\1/p' <<<"$ME")
ME2=$(curl -s -b "$JAR2" "$BASE/auth/me")
ME2_ID=$(sed -n 's/.*"id":\([0-9]*\).*/\1/p' <<<"$ME2")
rm -f "$JAR2"
[[ -n "$ME1_ID" && "$ME1_ID" == "$ME2_ID" ]] || fail "second login created a different user: $ME1_ID vs $ME2_ID"
pass "repeat login reuses the same user (id=$ME1_ID)"

echo "ALL PASSED"

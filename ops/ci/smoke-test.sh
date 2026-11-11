#!/usr/bin/env bash
# Smoke-test a deployed environment. Read-only: no uploads, no Gemini calls, no cost beyond a few
# requests. Exits non-zero on the first failure.
#
#   PROJECT_ID=... [REGION=us-central1] [EXPECT_TAG=abc1234] [PROJECT_NUMBER=...] ./ops/ci/smoke-test.sh
#
# EXPECT_TAG, when set, also checks that every service is serving an image with that tag.
# PROJECT_NUMBER, when set, tests the deterministic URLs (https://SERVICE-NUMBER.REGION.run.app),
# which are the ones allowed by CORS and Firebase sign-in.
set -euo pipefail

: "${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-us-central1}"
EXPECT_TAG="${EXPECT_TAG:-}"
PROJECT_NUMBER="${PROJECT_NUMBER:-}"

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "ok:   $*"; }

describe() {
  gcloud run services describe "$1" --project "$PROJECT_ID" --region "$REGION" --format "value($2)"
}

# 1) Each service is ready and serving its newest revision (and the expected image).
for svc in receipt-api receipt-worker receipt-frontend; do
  ready="$(describe "$svc" 'status.conditions[0].status')"
  [[ "$ready" == "True" ]] || fail "$svc is not ready (Ready=$ready)"
  latest="$(describe "$svc" 'status.latestReadyRevisionName')"
  created="$(describe "$svc" 'status.latestCreatedRevisionName')"
  [[ "$latest" == "$created" ]] || fail "$svc: newest revision $created is not ready (serving $latest)"
  if [[ -n "$EXPECT_TAG" ]]; then
    image="$(describe "$svc" 'spec.template.spec.containers[0].image')"
    [[ "$image" == *":${EXPECT_TAG}" ]] || fail "$svc runs $image, expected tag $EXPECT_TAG"
  fi
  pass "$svc ready ($latest)"
done

if [[ -n "$PROJECT_NUMBER" ]]; then
  API_URL="https://receipt-api-${PROJECT_NUMBER}.${REGION}.run.app"
  WEB_URL="https://receipt-frontend-${PROJECT_NUMBER}.${REGION}.run.app"
else
  API_URL="$(describe receipt-api status.url)"
  WEB_URL="$(describe receipt-frontend status.url)"
fi

# 2) API: health is public and reports this environment; data endpoints require sign-in.
health="$(curl -fsS --max-time 30 "${API_URL}/api/v1/health")" || fail "API health request failed"
grep -q '"service":"api"' <<<"$health" || fail "unexpected API health response: $health"
pass "API health: $health"

code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 30 "${API_URL}/api/v1/documents")"
[[ "$code" == "401" ]] || fail "unauthenticated /api/v1/documents returned $code, expected 401"
pass "API rejects requests without a token (401)"

# 3) Frontend: serves the app shell with security headers, and deep links fall back to it.
headers="$(mktemp)"; body="$(mktemp)"; trap 'rm -f "$headers" "$body"' EXIT
curl -fsS --max-time 30 -D "$headers" -o "$body" "${WEB_URL}/" || fail "frontend request failed"
grep -q 'id="root"' "$body" || fail "frontend did not return the app shell"
grep -qi '^x-content-type-options: nosniff' "$headers" || fail "frontend missing X-Content-Type-Options"
grep -qi '^x-frame-options: deny' "$headers" || fail "frontend missing X-Frame-Options"
pass "frontend serves the app with security headers"

code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 30 "${WEB_URL}/review")"
[[ "$code" == "200" ]] || fail "frontend deep link returned $code"
pass "frontend deep links work"

# 4) Worker: not reachable from the internet (internal ingress).
code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 30 "$(describe receipt-worker status.url)/health")"
[[ "$code" == "403" || "$code" == "404" ]] || fail "worker answered from the internet ($code)"
pass "worker is not publicly reachable ($code)"

echo "Smoke test passed: ${WEB_URL}"

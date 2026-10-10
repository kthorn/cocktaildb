#!/bin/bash
# infrastructure/scripts/smoke-test.sh
# Smoke tests for the deployed API and verified hashed frontend.
#
# Usage:
#   ./smoke-test.sh                      # Test localhost
#   ./smoke-test.sh http://1.2.3.4       # Test a specific host
#   ./smoke-test.sh https://example.com  # Test a domain

set -euo pipefail

BASE_URL="${1:-http://localhost}"
BASE_URL="${BASE_URL%/}"
CURL_BIN="${CURL_BIN:-curl}"
RECIPE_ID="${SMOKE_RECIPE_ID:-}"
INGREDIENT_ID="${SMOKE_INGREDIENT_ID:-}"
ALLOW_EMPTY_DB="${SMOKE_ALLOW_EMPTY_DB:-false}"
EMPTY_DATABASE=false

printf '%s\n' "========================================"
printf '%s\n' "  CocktailDB Smoke Tests"
printf '%s\n' "========================================"
printf '\nBase URL: %s\n\n' "$BASE_URL"

PASS=0
FAIL=0
SKIP=0

url_for() {
    printf '%s%s' "$BASE_URL" "$1"
}

request_status() {
    local endpoint="$1"
    "$CURL_BIN" -sS -o /dev/null -w '%{http_code}' \
        --connect-timeout 10 --max-time 30 "$(url_for "$endpoint")" 2>/dev/null || printf '000'
}

request_body() {
    local endpoint="$1"
    "$CURL_BIN" -sS --connect-timeout 10 --max-time 30 \
        "$(url_for "$endpoint")" 2>/dev/null || true
}

test_endpoint() {
    local name="$1"
    local endpoint="$2"
    local expected_status="${3:-200}"
    local status

    printf '%-48s ' "Testing $name..."
    status="$(request_status "$endpoint")"
    if [[ "$status" == "$expected_status" ]]; then
        printf 'PASS (HTTP %s)\n' "$status"
        ((++PASS))
    elif [[ "$status" == 000 ]]; then
        printf '%s\n' 'FAIL (connection error)'
        ((++FAIL))
    else
        printf 'FAIL (expected %s, got %s)\n' "$expected_status" "$status"
        ((++FAIL))
    fi
}

test_json_field() {
    local name="$1"
    local endpoint="$2"
    local field="$3"
    local response

    printf '%-48s ' "Testing $name..."
    response="$(request_body "$endpoint")"
    if [[ -z "$response" ]]; then
        printf '%s\n' 'FAIL (no response)'
        ((++FAIL))
    elif grep -q "\"$field\"" <<<"$response"; then
        printf 'PASS (contains %s)\n' "$field"
        ((++PASS))
    else
        printf 'FAIL (missing %s)\n' "$field"
        ((++FAIL))
    fi
}

extract_asset_refs() {
    # HTML emitted by Vite uses absolute /assets URLs. Keep this deliberately
    # narrow so API URLs and external CDN resources are never smoke targets.
    sed "s/[\"'()<> ]/\\n/g" | grep -E '^/assets/[^?#]+' | sort -u || true
}

check_page_assets() {
    local name="$1"
    local endpoint="$2"
    local expected_status="$3"
    local body ref ref_count=0

    test_endpoint "$name" "$endpoint" "$expected_status"
    body="$(request_body "$endpoint")"
    while IFS= read -r ref; do
        [[ -n "$ref" ]] || continue
        ((++ref_count))
        test_endpoint "asset availability $ref" "$ref" 200
    done < <(printf '%s' "$body" | extract_asset_refs)
    if ((ref_count == 0)); then
        printf '%-48s %s\n' "Asset references $name" "FAIL (no extracted local asset references)"
        ((++FAIL))
    fi
}

discover_recipe_id() {
    local body
    body="$(request_body /api/v1/recipes/search)"
    grep -oE '"id"[[:space:]]*:[[:space:]]*[0-9]+' <<<"$body" |
        head -1 | grep -oE '[0-9]+$' || true
}

discover_ingredient_id() {
    local body
    body="$(request_body /api/v1/ingredients)"
    grep -oE '"id"[[:space:]]*:[[:space:]]*[0-9]+' <<<"$body" |
        head -1 | grep -oE '[0-9]+$' || true
}

printf '%s\n' '=== Health & Infrastructure ==='
test_endpoint 'Health check' /health
test_json_field 'Health response' /health status

printf '\n%s\n' '=== API Endpoints ==='
test_endpoint 'Recipes list' /api/v1/recipes/search
test_endpoint 'Ingredients list' /api/v1/ingredients
test_endpoint 'Units list' /api/v1/units
test_endpoint 'Tags list' /api/v1/tags/public

printf '\n%s\n' '=== Analytics Endpoints ==='
test_endpoint 'Ingredient usage' /api/v1/analytics/ingredient-usage
test_endpoint 'Recipe complexity' /api/v1/analytics/recipe-complexity

printf '\n%s\n' '=== Frontend ==='
check_page_assets 'Static index' / 200
test_endpoint 'Static config' /js/config.js 200

for metadata in /manifest.json /asset-inventory.json /frontend-state.json /frontend-pending.json; do
    test_endpoint "manifest metadata exclusion $metadata" "$metadata" 404
done

if [[ -z "$RECIPE_ID" ]]; then
    RECIPE_ID="$(discover_recipe_id)"
fi
if [[ -z "$INGREDIENT_ID" ]]; then
    INGREDIENT_ID="$(discover_ingredient_id)"
fi

if [[ -n "$RECIPE_ID" && -n "$INGREDIENT_ID" ]]; then
    check_page_assets "Recipe page ($RECIPE_ID)" "/recipe/$RECIPE_ID" 200
    check_page_assets "Ingredient page ($INGREDIENT_ID)" "/ingredient/$INGREDIENT_ID" 200
elif [[ "$ALLOW_EMPTY_DB" == true ]]; then
    EMPTY_DATABASE=true
    printf '%-48s %s\n' 'Testing empty database fixture...' 'PASS (no IDs; using 404 routes)'
    ((++PASS))
    check_page_assets 'Empty recipe route' /recipe/404 404
    check_page_assets 'Empty ingredient route' /ingredient/404 404
else
    printf '%-48s %s\n' 'Testing selected frontend verification IDs...' 'FAIL (API returned no existing recipe and ingredient IDs)'
    ((++FAIL))
fi

if [[ "$EMPTY_DATABASE" == true ]]; then
    printf '%-48s %s\n' 'Recipes/ingredients data checks' 'SKIP (empty database)'
    ((++SKIP))
else
    test_json_field 'Recipes has data' /api/v1/recipes/search recipes
    test_json_field 'Ingredients has data' /api/v1/ingredients name
fi

printf '\n%s\n' '========================================'
printf '%s\n' '  Results'
printf '%s\n' '========================================'
printf '\nPassed: %s\n' "$PASS"
printf 'Failed: %s\n' "$FAIL"
printf 'Skipped: %s\n\n' "$SKIP"

if ((FAIL > 0)); then
    printf 'SMOKE TEST FAILED - %s test(s) failed\n' "$FAIL"
    exit 1
fi

printf '%s\n' 'ALL SMOKE TESTS PASSED'
exit 0

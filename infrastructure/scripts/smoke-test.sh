#!/bin/bash
# infrastructure/scripts/smoke-test.sh
# Smoke tests for CocktailDB deployment
#
# Usage:
#   ./smoke-test.sh                      # Test localhost
#   ./smoke-test.sh http://1.2.3.4       # Test specific host
#   ./smoke-test.sh https://example.com  # Test domain

set -euo pipefail

BASE_URL="${1:-http://localhost}"

# Remove trailing slash if present
BASE_URL="${BASE_URL%/}"

echo "========================================"
echo "  CocktailDB Smoke Tests"
echo "========================================"
echo ""
echo "Base URL: $BASE_URL"
echo ""

PASS=0
FAIL=0
SKIP=0

# Test function
test_endpoint() {
    local name="$1"
    local endpoint="$2"
    local expected_status="${3:-200}"
    local method="${4:-GET}"

    printf "%-40s " "Testing $name..."

    # Make request and capture status code
    local status
    status=$(curl -s -o /dev/null -w "%{http_code}" -X "$method" \
        --connect-timeout 10 --max-time 30 \
        "${BASE_URL}${endpoint}" 2>/dev/null) || status="000"

    if [ "$status" = "$expected_status" ]; then
        echo "PASS (HTTP $status)"
        ((PASS++))
    elif [ "$status" = "000" ]; then
        echo "FAIL (connection error)"
        ((FAIL++))
    else
        echo "FAIL (expected $expected_status, got $status)"
        ((FAIL++))
    fi
}

# Test JSON response contains expected field
test_json_field() {
    local name="$1"
    local endpoint="$2"
    local field="$3"

    printf "%-40s " "Testing $name..."

    local response
    response=$(curl -s --connect-timeout 10 --max-time 30 \
        "${BASE_URL}${endpoint}" 2>/dev/null) || response=""

    if [ -z "$response" ]; then
        echo "FAIL (no response)"
        ((FAIL++))
        return
    fi

    if echo "$response" | grep -q "\"$field\""; then
        echo "PASS (contains $field)"
        ((PASS++))
    else
        echo "FAIL (missing $field)"
        ((FAIL++))
    fi
}

echo "=== Health & Infrastructure ==="
test_endpoint "Health check" "/health"
test_json_field "Health response" "/health" "status"

echo ""
echo "=== API Endpoints ==="
test_endpoint "Recipes list" "/api/v1/recipes"
test_endpoint "Ingredients list" "/api/v1/ingredients"
test_endpoint "Units list" "/api/v1/units"
test_endpoint "Tags list" "/api/v1/tags"

echo ""
echo "=== Analytics Endpoints ==="
test_endpoint "Ingredient usage" "/api/v1/analytics/ingredient-usage"
test_endpoint "Recipe complexity" "/api/v1/analytics/recipe-complexity"

echo ""
echo "=== Frontend ==="
test_endpoint "Index page" "/"
test_endpoint "Static JS" "/js/api.js"
test_endpoint "Static CSS" "/css/styles.css"

echo ""
echo "=== API Response Validation ==="
test_json_field "Recipes has data" "/api/v1/recipes" "recipes"
test_json_field "Ingredients has data" "/api/v1/ingredients" "ingredients"

echo ""
echo "========================================"
echo "  Results"
echo "========================================"
echo ""
echo "Passed: $PASS"
echo "Failed: $FAIL"
echo "Skipped: $SKIP"
echo ""

if [ $FAIL -gt 0 ]; then
    echo "SMOKE TEST FAILED - $FAIL test(s) failed"
    exit 1
fi

echo "ALL SMOKE TESTS PASSED"
exit 0

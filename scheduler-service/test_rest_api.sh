#!/usr/bin/env bash
# Test the scheduler-service REST API directly

BASE_URL="http://localhost:8087/v1"

echo "=== Test 1: Create a simple one-off job with category ==="
curl -X POST "$BASE_URL/jobs" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Test reminder",
    "description": "Check deployment status",
    "created_by": "test-agent-1",
    "category": "ops",
    "schedule": {
      "type": "one_off",
      "expression": {"run_at": "'$(date -u -v+5M +%Y-%m-%dT%H:%M:%S)Z'"}
    }
  }' | jq .

echo -e "\n\n=== Test 2: List all jobs ==="
curl -s "$BASE_URL/jobs" | jq '.[:2]'

echo -e "\n\n=== Test 3: List jobs with filter (status=scheduled) ==="
curl -s "$BASE_URL/jobs?status_filter=scheduled" | jq '.[:2]'

echo -e "\n\n=== Test 4: Health check ==="
curl -s "$BASE_URL/health/ready" | jq .

echo -e "\n\n=== Test 5: Metrics ==="
curl -s "$BASE_URL/health/metrics" | jq .

echo -e "\n\nAll tests complete!"




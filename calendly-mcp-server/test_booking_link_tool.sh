#!/bin/bash

# Test the calendly_create_booking_link tool

set -e

BASE_URL="http://localhost:8086/mcp"

echo "===== Calendly Booking Link Tool Test ====="
echo ""

# Test 1: Generate a booking link
echo "Test 1: Generate booking link for Oct 29 @ 12:30pm"
echo "-----------------------------------------------"
curl -s -X POST "$BASE_URL" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "calendly_create_booking_link",
      "arguments": {
        "url": "https://calendly.com/zarek-drozda/30min",
        "date": "2025-10-29",
        "time": "12:30pm",
        "name": "Chad Dorsey",
        "email": "cdorsey@concord.org",
        "timezone": "America/New_York",
        "custom_fields": {
          "title the meeting": "Chad - Kate - Zarek check-in"
        },
        "guests": ["kmiller@concord.org"]
      }
    }
  }' | jq '.'

echo ""
echo ""

# Test 2: Generate link with 24-hour time format
echo "Test 2: Generate booking link with 24-hour time"
echo "------------------------------------------------"
curl -s -X POST "$BASE_URL" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
      "name": "calendly_create_booking_link",
      "arguments": {
        "url": "https://calendly.com/zarek-drozda/30min",
        "date": "2025-10-29",
        "time": "14:30",
        "name": "Test User",
        "email": "test@example.com",
        "timezone": "America/New_York"
      }
    }
  }' | jq '.'

echo ""
echo ""

# Test 3: Missing required field
echo "Test 3: Missing required field (should error)"
echo "----------------------------------------------"
curl -s -X POST "$BASE_URL" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
      "name": "calendly_create_booking_link",
      "arguments": {
        "url": "https://calendly.com/zarek-drozda/30min",
        "date": "2025-10-29",
        "time": "14:30"
      }
    }
  }' | jq '.'

echo ""
echo "===== Tests Complete ====="


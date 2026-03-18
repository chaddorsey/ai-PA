#!/bin/bash
# Signals the server that the laptop is online.
# Runs on the laptop via launchd on network change and wake from sleep.
# Hits a lightweight endpoint on the server that can trigger task queue drain.

SERVER="http://100.99.171.119:8891/laptop-online"

# Wait a moment for network to fully initialize after wake
sleep 3

# Signal the server
curl -s --max-time 5 -X POST "$SERVER" \
  -H "Content-Type: application/json" \
  -d "{\"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\", \"hostname\": \"$(hostname)\"}" \
  > /dev/null 2>&1

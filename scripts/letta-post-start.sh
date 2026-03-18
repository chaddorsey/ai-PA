#!/bin/bash
# Install SSH client in Letta container after startup
# Run this after docker-compose up
sleep 5
docker exec ai-pa-letta-1 bash -c "which ssh >/dev/null 2>&1 || (apt-get update -qq && apt-get install -y -qq openssh-client)" 2>&1 | tail -1
echo "SSH client ready in Letta container"

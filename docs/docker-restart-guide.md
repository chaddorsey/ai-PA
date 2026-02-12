# Docker Desktop Restart Guide (macOS)

Docker Desktop on macOS can become unresponsive after extended uptime (10+ days). When this happens, `docker` CLI commands hang indefinitely and all containerized services (Letta, Slackbot, MCP servers, etc.) become unreachable.

## Symptoms

- `docker ps`, `docker exec`, `docker info` commands hang forever
- Letta API returns "connection refused" or times out at `http://localhost:8283`
- Slackbot / agents stop responding
- Docker Desktop UI may still appear but is non-functional

## Quick Recovery (try first)

1. **Quit Docker Desktop** from the menu bar (Docker whale icon > Quit Docker Desktop)
2. Wait 10 seconds
3. **Reopen** Docker Desktop from Applications or Spotlight

If Docker Desktop doesn't appear in the menu bar or Force Quit menu, proceed to the full recovery below.

## Full Recovery

### 1. Kill stuck Docker CLI processes

Previous `docker` commands may be holding connections open and blocking the daemon restart.

```bash
# Find and kill all stuck docker CLI processes
ps aux | grep -E "docker (ps|exec|inspect|info|cp)" | grep -v grep | awk '{print $2}' | xargs kill 2>/dev/null
```

### 2. Kill the stale Docker backend

The `com.docker.backend` process can survive a Docker Desktop quit and hold onto sockets/ports. This prevents the new instance from starting properly.

```bash
# Find the stale backend
ps aux | grep "com.docker.backend" | grep -v grep

# Kill it (use -9 if regular kill doesn't work)
kill <PID>
# or
kill -9 <PID>

# Verify it's gone (com.docker.vmnetd is OK to keep — it's a system helper)
ps aux | grep "com.docker" | grep -v grep
```

### 3. Kill other stale Docker processes

```bash
# Kill any remaining Docker Desktop renderer/helper processes
killall "Docker Desktop" 2>/dev/null
killall "Docker Desktop Helper" 2>/dev/null
killall "Docker Desktop Helper (Renderer)" 2>/dev/null
killall "Docker Desktop Helper (GPU)" 2>/dev/null

# Kill stale virtualization and build processes
kill $(pgrep -f "com.docker.virtualization") 2>/dev/null
kill $(pgrep -f "com.docker.build") 2>/dev/null
```

### 4. Relaunch Docker Desktop

```bash
open /Applications/Docker.app
```

### 5. Wait for containers to start

Docker Desktop needs ~30-60 seconds to initialize its VM and start all containers.

```bash
# Poll until Docker is ready
for i in $(seq 1 12); do
    sleep 10
    if docker ps >/dev/null 2>&1; then
        echo "Docker ready after $((i*10)) seconds"
        docker ps --format "table {{.Names}}\t{{.Status}}"
        break
    fi
    echo "Attempt $i: not ready yet..."
done
```

### 6. Wait for Letta health

Letta takes extra time after container start because it recreates the sandbox venv and installs pip requirements (~9 packages including dspy-ai, google-api-python-client, clingo). This can take 2-5 minutes.

```bash
# Poll Letta health
for i in $(seq 1 20); do
    sleep 15
    status=$(docker ps --filter name=letta --format "{{.Status}}" 2>/dev/null)
    echo "Attempt $i: $status"
    if echo "$status" | grep -q "healthy"; then
        echo "Letta is healthy"
        break
    fi
done
```

## Post-Restart Verification

```bash
# Check all critical services are healthy
docker ps --format "table {{.Names}}\t{{.Status}}" | grep -E "(letta|slackbot|scheduler)"

# Verify Letta API
curl -s http://localhost:8283/v1/health

# Verify sandbox venv has packages
docker exec ai-pa-letta-1 /app/tools/letta/env/bin/pip list | grep -E "pytz|google|clingo|dspy"

# Verify PYTHONPATH (scheduling_orchestrator)
docker exec ai-pa-letta-1 env | grep PYTHONPATH
```

## Prevention

### Scheduled Docker Desktop restart

To avoid the hung-daemon issue, consider restarting Docker Desktop weekly via launchd or cron:

```bash
# Add to crontab: restart Docker every Sunday at 4am
# crontab -e
0 4 * * 0 killall "Docker Desktop" 2>/dev/null; sleep 10; open /Applications/Docker.app
```

### Monitor Docker health

A simple health check script that alerts when Docker becomes unresponsive:

```bash
#!/bin/bash
# Save as scripts/check-docker-health.sh
if ! timeout 5 docker ps >/dev/null 2>&1; then
    echo "$(date) - Docker daemon unresponsive" >> ~/Library/Logs/docker-health/health.log
    # Could add notification here (e.g., via Slack webhook)
fi
```

### Reduce Docker resource pressure

Current allocation: 10 CPUs, 8GB RAM for the Docker VM running 30+ containers. If hangs are frequent, consider:
- Stopping non-essential containers during low-use periods
- Increasing VM memory allocation in Docker Desktop > Settings > Resources
- Upgrading to a newer Docker Desktop version (currently running since Feb 3)

## Known Issues

- **`com.docker.backend` survives kills**: Sometimes requires `kill -9` (SIGKILL). Regular `kill` (SIGTERM) may not work if the process is stuck in an I/O wait.
- **Sandbox venv recreation on every restart**: Letta recreates `/app/tools/letta/env/` on each container start, reinstalling all pip_requirements. This adds 2-5 minutes to startup. The PYTHONPATH approach (`/app/tools/letta`) for `scheduling_orchestrator` survives this because it uses the volume mount directly, not the venv.
- **Docker Desktop not appearing in Force Quit**: This means the Electron app hasn't fully launched, usually because the old backend is blocking resources. Kill the old backend first.

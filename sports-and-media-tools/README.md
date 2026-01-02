# Sports & Media Control Tools

Letta agent tools for querying sports schedules, controlling Roku TV, and tuning FIOS cable channels via Flipper Zero IR.

## Overview

This module provides a complete sports and media control system:

- **Query sports games** across NFL, NBA, MLB, NHL, NCAA via ESPN API
- **Control Roku TV** - power, apps, navigation via ECP protocol
- **Tune FIOS channels** - IR commands via Flipper Zero
- **Watch games end-to-end** - automatic channel/app switching

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Docker Network (pa-internal)                │
│  ┌─────────────┐  ┌─────────────────┐  ┌─────────────────────┐  │
│  │   Letta     │  │ sports-service  │  │   flipper-api       │  │
│  │   Agent     │◄─┤  (ESPN + cache) │  │   (IR over USB)     │  │
│  └──────┬──────┘  └────────┬────────┘  └──────────┬──────────┘  │
│         │                  │                       │             │
│         ▼                  ▼                       ▼             │
│  ┌──────────────┐  ┌──────────────┐        ┌──────────────┐     │
│  │  Roku TV     │  │  ESPN API    │        │ Flipper Zero │     │
│  │ 192.168.7.187│  │  (public)    │        │  (USB /dev)  │     │
│  └──────────────┘  └──────────────┘        └──────────────┘     │
└──────────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Start Docker Services

```bash
# From ai-PA root directory
docker-compose up -d sports-service flipper-api
```

### 2. Verify Services

```bash
# Check sports service
curl http://localhost:5123/health

# Check flipper API (requires Flipper Zero connected)
curl http://localhost:5124/health

# Get current games
curl http://localhost:5123/games
```

### 3. Register Letta Tools

```bash
cd sports-and-media-tools/letta-tools
python register_sports_media_tools.py
```

### 4. Setup Agent

```bash
python setup_sports_agent.py
```

## Directory Structure

```
sports-and-media-tools/
├── README.md                    # This file
├── sports-service/              # ESPN API polling service
│   ├── Dockerfile
│   ├── requirements.txt
│   └── sports_api.py
├── flipper-api/                 # Flipper Zero HTTP API
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── flipper_api.py
│   └── send_ir.py
├── config/                      # Configuration files
│   └── channel_mapping.json     # FIOS channels, teams, Roku apps
├── letta-tools/                 # Letta agent tools
│   ├── sports_media_tools.py    # Tool implementations
│   ├── register_sports_media_tools.py
│   └── setup_sports_agent.py
└── reference-voice-tv-remote/   # Original reference implementation
```

## Letta Tools

### query_sports_games

Query ESPN for current and upcoming games.

```python
query_sports_games(team="patriots")  # Games for specific team
query_sports_games(league="nfl")     # All NFL games
query_sports_games()                  # All games
```

### get_channel_for_game

Look up the FIOS channel for a game or network.

```python
get_channel_for_game(team="celtics")  # Channel for Celtics game
get_channel_for_game(network="ESPN")  # ESPN channel number
```

### control_roku_tv

Control Roku TV via ECP protocol.

```python
control_roku_tv(action="power_on")
control_roku_tv(action="launch_app", app_name="netflix")
control_roku_tv(action="input_hdmi1")  # Switch to FIOS
control_roku_tv(action="keypress", key="home")
```

### send_fios_ir_command

Send individual IR commands to FIOS box.

```python
send_fios_ir_command(command="Guide")
send_fios_ir_command(command="Ok")
send_fios_ir_command(command="5")  # Digit
```

### tune_fios_channel

Tune to a specific FIOS channel.

```python
tune_fios_channel(channel=570)  # ESPN HD
tune_fios_channel(channel=504)  # CBS HD
```

### watch_game

End-to-end orchestration to watch a game.

```python
watch_game(team="patriots")  # Finds game, switches input, tunes channel
```

## Configuration

### Channel Mapping (`config/channel_mapping.json`)

```json
{
  "networks": {
    "ESPN": {"channel": 70, "hd_channel": 570, "aliases": ["espn"]},
    "CBS": {"channel": 4, "hd_channel": 504, "aliases": ["cbs"]}
  },
  "teams": {
    "patriots": {"name": "New England Patriots", "league": "nfl"}
  },
  "roku_apps": {
    "netflix": {"app_id": 12},
    "espn": {"app_id": 34376}
  }
}
```

## Hardware Requirements

- **Flipper Zero** - Connected via USB for IR transmission
- **Roku TV** - On network at 192.168.7.187
- **FIOS Cable Box** - Arris VMS1100 or compatible

## API Endpoints

### Sports Service (port 5123)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/games` | GET | All cached games |
| `/games/<league>` | GET | Games for specific league |
| `/team/<name>` | GET | Find game for team |
| `/channel/<network>` | GET | Get channel for network |
| `/lookup` | POST | Main lookup endpoint |
| `/refresh` | POST | Force cache refresh |

### Flipper API (port 5124)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/ir/<command>` | POST | Send IR command |
| `/channel/<number>` | POST | Tune to channel |
| `/commands` | GET | List available commands |
| `/sequence` | POST | Send command sequence |

## Troubleshooting

### Flipper Zero not detected

```bash
# Check for device
ls /dev/tty.usbmodem*

# On Linux
ls /dev/ttyACM*
```

### Sports service not returning games

```bash
# Check health
curl http://localhost:5123/health

# Force refresh
curl -X POST http://localhost:5123/refresh
```

### Roku not responding

```bash
# Check ECP API
curl http://192.168.7.187:8060/query/device-info
```

## Related Documentation

- [PBI-27: Sports & Media Control Agent](../docs/delivery/27/prd.md)
- [Coding Custom Letta Tools](../context/coding_custom_letta_tools.md)
- [Reference Implementation](./reference-voice-tv-remote/README.md)


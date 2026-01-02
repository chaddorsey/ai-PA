# PBI-27: Sports & Media Control Agent

[View in Backlog](../backlog.md#user-content-PBI-27)

## Overview

This PBI implements a Letta-based sports and media control system that enables an AI agent to query sports schedules, match games to broadcast channels, and control TV/entertainment hardware to tune to requested games or streaming services.

## Problem Statement

Users want to easily watch sports games without manually:
- Looking up game schedules across multiple leagues
- Finding which channel or streaming service is broadcasting a game
- Navigating TV inputs and channel tuning

The reference voice-TV-remote implementation solved this for Home Assistant, but we need a Letta agent-based solution that integrates with our existing infrastructure and supports future multi-user scenarios.

## User Stories

1. **As a user**, I want to ask "What games are on tonight?" and get a summary of current/upcoming games across all sports.

2. **As a user**, I want to say "Watch the Patriots game" and have the TV automatically tune to the correct channel.

3. **As a user**, I want to ask "What channel is ESPN?" and get the FIOS channel number.

4. **As a user**, I want to launch streaming apps like Netflix or Peacock through natural language commands.

5. **As a user**, I want the agent to intelligently switch between cable and streaming based on where games are broadcasting.

## Technical Approach

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Docker Network (pa-internal)                │
│  ┌─────────────┐  ┌─────────────────┐  ┌─────────────────────┐  │
│  │   Letta     │  │ sports-service  │  │   flipper-api       │  │
│  │   Agent     │◄─┤  (ESPN + cache) │  │   (IR over USB)     │  │
│  └──────┬──────┘  └────────┬────────┘  └──────────┬──────────┘  │
│         │                  │                       │             │
│         │    Letta Tools   │                       │             │
│         ├──────────────────┴───────────────────────┤             │
│         │                                          │             │
│         ▼                                          ▼             │
│  ┌──────────────┐                          ┌──────────────┐     │
│  │  Roku TV     │                          │ Flipper Zero │     │
│  │ 192.168.7.187│                          │  (USB /dev)  │     │
│  └──────────────┘                          └──────────────┘     │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Components

1. **sports-service** (Docker container, port 5123)
   - Polls ESPN API every 15 minutes
   - Caches game data with team/league indexing
   - Provides REST endpoints for game lookup
   - Manages channel mapping configuration

2. **flipper-api** (Docker container, port 5124)
   - HTTP wrapper for Flipper Zero serial communication
   - Sends IR commands for FIOS cable box control
   - Supports individual commands and channel tuning

3. **Letta Tools** (Python functions)
   - `query_sports_games`: Query ESPN game data
   - `get_channel_for_game`: Look up broadcast channel
   - `control_roku_tv`: Roku ECP control
   - `send_fios_ir_command`: Individual IR commands
   - `tune_fios_channel`: Channel number tuning
   - `watch_game`: End-to-end orchestration

### Data Sources

- **ESPN API**: Free public API for game schedules
  - NFL, NBA, MLB, NHL, NCAA Football, NCAA Basketball, MLS
  - Includes broadcast network information

- **Channel Mapping**: JSON configuration
  - Network to FIOS channel mapping
  - Team aliases and preferences
  - Roku app IDs

## UX/UI Considerations

The agent should:
- Provide concise, useful responses about games
- Confirm actions taken ("Tuned to ESPN, channel 570")
- Handle errors gracefully with alternatives
- Support natural language variations

## Acceptance Criteria

1. **Sports Queries**
   - [ ] Agent can list games by sport/league
   - [ ] Agent can find games by team name
   - [ ] Game data includes broadcast info

2. **Channel Lookup**
   - [ ] Agent can map networks to FIOS channels
   - [ ] Prefers HD channels (500+)
   - [ ] Handles streaming service broadcasts

3. **TV Control**
   - [ ] Can power Roku TV on/off
   - [ ] Can launch streaming apps
   - [ ] Can switch to HDMI1 for cable

4. **FIOS Control**
   - [ ] Can send IR commands via Flipper
   - [ ] Can tune to specific channels
   - [ ] Multi-digit channels work correctly

5. **End-to-End**
   - [ ] "Watch the [team] game" works for cable games
   - [ ] Streaming games launch appropriate app
   - [ ] Errors are handled with useful feedback

## Dependencies

- Flipper Zero hardware connected via USB
- Roku TV on network at 192.168.7.187
- FIOS cable box with IR receiver
- Letta server running on port 8283
- Docker infrastructure for services

## Open Questions

1. How should we handle games on networks not in the channel mapping?
2. Should we add deep linking for streaming apps (e.g., specific game in ESPN+)?
3. How will multi-user preferences be managed for SMS access?

## Related Tasks

See [tasks.md](./tasks.md) for the task breakdown.


# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Auto-Madden is an AI-powered real-time NFL game companion. It provides insights, play explanations, and answers questions about the game—like having John Madden on your couch while watching football.

### Microservices Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  companion-ui   │◄──►│  insight-engine │◄───│ game-state-svc  │
│   (Port 5130)   │    │   (Port 5131)   │    │   (Port 5132)   │
│                 │    │                 │    │                 │
│  Flask Web UI   │    │  LLM Insights   │    │  ESPN Polling   │
└─────────────────┘    └────────┬────────┘    └────────┬────────┘
                                │                      │
                    ┌───────────┴───────────┐          │
                    ▼                       ▼          ▼
            ┌─────────────┐        ┌──────────────┐  ┌─────────────┐
            │ Letta Agent │        │ NFL Pro API  │  │  ESPN API   │
            │  (memory)   │        │ (rich data)  │  │ (live feed) │
            └─────────────┘        └──────────────┘  └─────────────┘
```

**Data Flow:**
1. `game-state-service` polls ESPN for live game data
2. Detected changes (scores, plays, turnovers) are emitted to `insight-engine`
3. `insight-engine` generates contextual insights via LLM and/or templates
4. `companion-ui` receives insights via WebSocket and displays them

## Development Commands

### Quick Start (Local Development)

```bash
# Run all services locally (uses simulator instead of live ESPN)
./start_companion.sh

# Or start services individually:
cd simulator && python3 game_simulator.py serve --port 5132
cd insight-engine && python3 insight_engine.py
cd companion-ui && python3 app.py
```

Open http://localhost:5130/simple in your browser.

### Docker (Production)

```bash
# From parent ai-PA directory
docker-compose up -d auto-madden-companion-ui auto-madden-insight-engine auto-madden-game-state

# View logs
docker-compose logs -f auto-madden-insight-engine

# Rebuild after code changes
docker-compose up -d --build auto-madden-insight-engine
```

### System Verification

```bash
# Run before live game testing
python3 test_system.py
python3 test_system.py --verbose
```

### NFL Pro Session (Rich Play Data)

NFL Pro provides detailed play metadata (formations, personnel, coverage) not available from ESPN:

```bash
cd nfl-pro-scraper
python3 session/nfl_pro_login.py  # Opens browser for manual login
```

Session stored in `credentials/browser_states/nfl_pro_state.json`. Without NFL Pro session, the companion uses ESPN-only mode (basic play descriptions).

### Game Simulator (Testing Without Live Games)

```bash
cd simulator

# List available cached games
python3 game_simulator.py list

# Download a completed game
python3 game_simulator.py download 401671495

# Run simulation at 10x speed (console mode)
python3 game_simulator.py run 401671495 --speed 10

# Run as service (replaces game-state-service)
python3 game_simulator.py serve --port 5132
```

### Registering Letta Tools

```bash
cd letta-tools
pip install -r requirements.txt
python3 register_auto_madden_tools.py
```

## Service Details

| Service | Port | Purpose | Main File |
|---------|------|---------|-----------|
| game-state-service | 5132 | ESPN API polling, change detection | `game_state_service.py` |
| insight-engine | 5131 | LLM insights, WebSocket delivery, Q&A | `insight_engine.py` |
| companion-ui | 5130 | Flask web interface | `app.py` |
| simulator | 5132 | Replays historical games for testing | `game_simulator.py` |

### Key API Endpoints

**game-state-service (5132):**
- `POST /start` - Start tracking (body: `{"team": "patriots"}` or `{"game_id": "401671495"}`)
- `POST /stop` - Stop tracking
- `GET /state` - Current game state
- `GET /games` - List current NFL games

**insight-engine (5131):**
- `POST /event` - Receive game state events
- `POST /query` - Ask a question (body: `{"question": "What is an RPO?"}`)
- `WS /ws` - WebSocket for real-time insights

### Testing API

```bash
# List games
curl http://localhost:5132/games

# Start tracking
curl -X POST http://localhost:5132/start -H "Content-Type: application/json" -d '{"team": "patriots"}'

# Ask a question
curl -X POST http://localhost:5131/query -H "Content-Type: application/json" -d '{"question": "What is an RPO?"}'
```

## Code Structure

```
auto-madden/
├── game-state-service/      # ESPN polling + NFL Pro enrichment
│   ├── game_state_service.py
│   ├── espn_client.py       # ESPN hidden API client
│   ├── nfl_pro_client.py    # NFL Pro API client
│   └── models.py            # GameState, GameChange, Play
├── insight-engine/
│   ├── insight_engine.py    # Main service (large: ~190KB)
│   ├── game_context.py      # Game context tracking
│   └── nfl_pro_integration.py
├── companion-ui/
│   ├── app.py               # Flask server
│   ├── templates/           # Jinja templates
│   └── static/              # JS/CSS
├── simulator/
│   └── game_simulator.py    # Historical game replay
├── nfl-pro-scraper/         # NFL Pro data collection
│   ├── scrapers/            # Various scraping utilities
│   ├── services/            # Live polling, insight preprocessing
│   └── session/             # Browser auth management
├── letta-tools/             # Letta agent integration
│   ├── auto_madden_tools.py
│   ├── auto_madden_sleeptime_tools.py
│   └── register_auto_madden_tools.py
├── config/templates/        # Insight templates (YAML)
└── data/                    # Local databases, cached games
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ESPN_POLL_INTERVAL` | 3 | Seconds between ESPN API polls |
| `LLM_PROVIDER` | anthropic | LLM provider (anthropic/openai) |
| `LLM_MODEL` | claude-sonnet-4-20250514 | Model for insight generation |
| `MAX_INSIGHTS_PER_MINUTE` | 4 | Rate limit for pushed insights |
| `MIN_INSIGHT_GAP_SECONDS` | 8 | Minimum gap between insights |
| `INSIGHT_ENGINE_URL` | http://localhost:5131 | Insight engine endpoint |
| `ANTHROPIC_API_KEY` | - | Required for LLM insights |

## Data Files

- `data/nfl_insights_2025.db` - SQLite database of scraped NFL Pro insights
- `data/processed_insights/` - Pre-processed insights by week
- `data/espn_nfl_pro_mapping.json` - ESPN game ID to NFL Pro UUID mapping
- `config/templates/insights.yaml` - Insight templates for situations/plays

## Cached Test Games

| Game ID | Matchup | Notes |
|---------|---------|-------|
| 401671495 | NYJ @ BUF | Bills blowout, 40-14 |
| 401671725 | GB @ MIN | Close game, 27-25 (good for testing) |
| 401671765 | DAL @ PHI | Eagles blowout, 41-7 |

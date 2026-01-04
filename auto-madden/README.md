# Auto-Madden: Real-Time Game Companion

Auto-Madden is an AI-powered companion for watching NFL games. It provides real-time insights, answers questions, and helps you understand the game better—like having John Madden on your couch.

## Overview

Auto-Madden consists of three microservices:

1. **game-state-service** (port 5132): Polls ESPN API for real-time game data
2. **insight-engine** (port 5131): Generates insights and handles LLM-based Q&A
3. **companion-ui** (port 5130): Web interface for viewing insights and asking questions

## Quick Start

### 1. Start the Services

```bash
# From the project root
docker-compose up -d auto-madden-companion-ui auto-madden-insight-engine auto-madden-game-state
```

### 2. Register Letta Tools

```bash
cd auto-madden/letta-tools
pip install -r requirements.txt
python register_auto_madden_tools.py
```

### 3. Open the Companion UI

Navigate to http://localhost:5130

### 4. Start a Game Session

Type a team name (e.g., "Patriots", "Chiefs", "Bills") to find and track their game.

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  companion-ui   │◄──►│  insight-engine │◄───│ game-state-svc  │
│   (Port 5130)   │    │   (Port 5131)   │    │   (Port 5132)   │
│                 │    │                 │    │                 │
│  Web Interface  │    │  LLM Insights   │    │  ESPN Polling   │
└─────────────────┘    └────────┬────────┘    └────────┬────────┘
                                │                      │
                                ▼                      ▼
                       ┌─────────────────┐    ┌─────────────────┐
                       │  Letta Agents   │    │    ESPN API     │
                       │  (Memory Layer) │    │  (Hidden API)   │
                       └─────────────────┘    └─────────────────┘
```

## Features

### Real-Time Insights
- Automatic insights pushed during the game
- Situation explanations (3rd down, red zone, two-minute warning)
- Play breakdowns for big plays, turnovers, scores
- Momentum shift alerts

### Adaptive Delivery
- Maximum 4 insights per minute (configurable)
- Minimum 8-second gap between insights
- Reduces frequency during intense action
- Increases frequency during stoppages

### Question Answering
- Ask anything about the game
- Context-aware answers using current game state
- Player lookups and stat context
- Rule explanations

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ESPN_POLL_INTERVAL` | 3 | Seconds between ESPN API polls |
| `LLM_PROVIDER` | anthropic | LLM provider (anthropic/openai) |
| `LLM_MODEL` | claude-sonnet-4-20250514 | Model for insight generation |
| `MAX_INSIGHTS_PER_MINUTE` | 4 | Rate limit for pushed insights |
| `MIN_INSIGHT_GAP_SECONDS` | 8 | Minimum gap between insights |

### Insight Templates

Templates are defined in `config/templates/insights.yaml`. Customize templates for:
- Situation explanations (3rd down, red zone, etc.)
- Play types (turnovers, big plays, scores)
- Game state changes (momentum, quarter changes)

## API Endpoints

### game-state-service (5132)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/games` | GET | List current NFL games |
| `/start` | POST | Start tracking a game |
| `/stop` | POST | Stop tracking |
| `/state` | GET | Get current game state |
| `/summary` | GET | Get game summary |

### insight-engine (5131)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/event` | POST | Receive game state events |
| `/query` | POST | Ask a question |
| `/explain_play` | POST | Get play explanation |
| `/ws` | WebSocket | Real-time insight delivery |

### companion-ui (5130)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Main UI |
| `/health` | GET | Health check |

## Letta Tools

### Main Agent Tools
- `get_current_game_state`: Get current score, clock, situation
- `ask_game_question`: Ask any question about the game
- `get_player_info`: Look up player information
- `explain_play`: Get detailed play explanation
- `get_game_summary`: Get drive-by-drive summary

### Sleeptime Agent Tools
- `summarize_game_insights`: Aggregate session insights
- `update_user_knowledge`: Track user learning
- `log_game_session`: Log completed sessions

## Troubleshooting

### No insights appearing
1. Check game-state-service health: `curl localhost:5132/health`
2. Verify a game is being tracked: `curl localhost:5132/state`
3. Check insight-engine logs: `docker logs auto-madden-insight-engine`

### WebSocket connection drops
- The UI auto-reconnects after 3 seconds
- Check insight-engine is running

### Questions not answered
1. Verify LLM API keys are set in environment
2. Check insight-engine logs for API errors

## Development

### Running Locally

```bash
# Game State Service
cd auto-madden/game-state-service
pip install -r requirements.txt
python game_state_service.py

# Insight Engine
cd auto-madden/insight-engine
pip install -r requirements.txt
python insight_engine.py

# Companion UI
cd auto-madden/companion-ui
pip install -r requirements.txt
python app.py
```

### Testing

```bash
# Test ESPN API access
curl http://localhost:5132/games

# Test starting a session
curl -X POST http://localhost:5132/start -H "Content-Type: application/json" -d '{"team": "patriots"}'

# Test asking a question
curl -X POST http://localhost:5131/query -H "Content-Type: application/json" -d '{"question": "What is an RPO?"}'
```

## Testing and Development

### The Testing Challenge

Live NFL games occur infrequently and unpredictably. Reserving them for final tuning makes sense, but we need a way to develop and iterate on the system between games.

### Game Simulator

The `simulator/` folder contains a **Game Simulator** that replays historical games from cached ESPN data. This allows:

- **Full system testing** without a live game
- **Rapid iteration** at configurable playback speeds (10x, 100x, etc.)
- **Reproducible scenarios** - same game, same events, every time
- **Edge case testing** - find games with specific situations (turnovers, close finishes, etc.)

#### Quick Start

```bash
cd auto-madden/simulator

# Find completed games to cache
python3 game_simulator.py find --date 20241229

# Download a game for simulation
python3 game_simulator.py download 401671495

# List cached games
python3 game_simulator.py list

# Run simulation at 10x speed
python3 game_simulator.py run 401671495 --speed 10

# Run as a drop-in replacement for game-state-service
python3 game_simulator.py serve --port 5132
```

#### Simulation Modes

**1. Console Mode** (`run` command)
- Runs simulation in foreground
- Emits events to insight-engine
- Shows progress in terminal

**2. Service Mode** (`serve` command)
- Runs as a Flask server on port 5132
- Same API as game-state-service
- Use with UI for full experience

#### Testing Workflow

1. **Cache several games** - variety of scenarios:
   - Blowout (test reduced frequency)
   - Close game (test high-stakes delivery)
   - High-scoring (test score change handling)
   - Turnover-heavy (test turnover insights)

2. **Run simulator as service**:
   ```bash
   python3 game_simulator.py serve --port 5132
   ```

3. **Start insight-engine and companion-ui** pointing to simulator

4. **Open UI** and start simulation via API or UI

5. **Iterate** on templates, timing, and LLM prompts

#### Cached Games

We've pre-cached these games for testing:

| Game ID | Matchup | Plays | Notes |
|---------|---------|-------|-------|
| 401671495 | NYJ @ BUF | 178 | Bills blowout, 40-14 |
| 401671725 | GB @ MIN | 188 | Close game, 27-25 |
| 401671765 | DAL @ PHI | 178 | Eagles blowout, 41-7 |

### Live Game Testing

When a live game is available:

1. Start all services normally
2. Use the UI to track a real game
3. Focus on:
   - Timing feel (too frequent? too sparse?)
   - Insight quality and relevance
   - Question-answering accuracy
   - Edge cases the simulator can't capture

## License

Part of the AI-PA project. Internal use only.


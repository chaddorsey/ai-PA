# NFL Pro Real-Time Integration

## Overview

This document describes the integration of NFL Pro detailed play-by-play data into the Auto-Madden companion system. NFL Pro provides rich data not available from ESPN:

- **Offensive Formation**: SHOTGUN, UNDER CENTER, I-FORM, PISTOL, EMPTY
- **Personnel Packages**: 11, 12, 21, 13, 22 personnel
- **Defensive Personnel**: DL, LB, DB counts
- **Defenders in Box**: 5-9 defenders
- **Pass Rush Count**: Number of rushers
- **Coverage Type**: Cover 1, Cover 2, Cover 3, etc.
- **Time to Throw**: Seconds before release
- **Air Yards**: Distance of pass attempt
- **Route Type**: Route run by receiver

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  NFL Pro Site   │────▶│  Live Poller     │────▶│ Insight Engine  │
│  (Playwright)   │     │  (Port 5133)     │     │ (Port 5131)     │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                │                         │
                                ▼                         ▼
                        ┌──────────────────┐     ┌─────────────────┐
                        │ Historical DB    │     │  WebSocket UI   │
                        │ (2024 Season)    │     │  (Port 5130)    │
                        └──────────────────┘     └─────────────────┘
```

## Components

### 1. Live Poller (`nfl-pro-scraper/scrapers/live_poller.py`)

Polls NFL Pro during live games to capture detailed play data:

```bash
# Start as a service
cd /Volumes/main-drive/ai-PA/auto-madden/nfl-pro-scraper
python3 scrapers/live_poller.py --port 5133

# Or start with a specific game
python3 scrapers/live_poller.py --game-uuid f979d7ee-311e-11f0-b670-ae1250fadad1 --interval 30
```

**API Endpoints:**
- `POST /start` - Start polling with `{game_uuid, interval}`
- `POST /stop` - Stop polling
- `GET /state` - Current game state with detailed data
- `GET /plays` - All plays with formation/personnel
- `POST /compare` - Compare play against historical data

### 2. Insight Engine Integration (`insight-engine/nfl_pro_integration.py`)

Generates insights from NFL Pro data:

- **Formation insights**: Misdirection success, unconventional looks
- **Personnel insights**: Power run success, spread surprises
- **Defensive insights**: Light box exploitation, stacked box analysis
- **Historical comparisons**: vs league averages from 2024 season

### 3. Historical Database

Season data stored in SQLite at `data/nfl_plays_2024.db`:

```sql
-- Games table
SELECT * FROM games WHERE week = 1;

-- Plays with detailed data
SELECT 
    off_formation, off_personnel, play_type,
    AVG(LENGTH(play_description)) as avg_desc_len
FROM plays
GROUP BY off_formation, off_personnel, play_type;

-- Team tendencies
SELECT 
    possession_team, play_type, 
    COUNT(*) as count,
    AVG(is_scoring) * 100 as scoring_pct
FROM plays
WHERE is_redzone = 1
GROUP BY possession_team, play_type;
```

## Testing Guide

### Test 1: Verify Historical Data

```bash
cd /Volumes/main-drive/ai-PA/auto-madden/nfl-pro-scraper
python3 scrapers/browser_season_scraper.py --season 2024 --stats
```

### Test 2: Test Live Poller with Completed Game

```bash
# Start the live poller service
cd /Volumes/main-drive/ai-PA/auto-madden/nfl-pro-scraper
python3 scrapers/live_poller.py --port 5133 &

# Start polling a completed game (for testing)
curl -X POST http://localhost:5133/start \
  -H "Content-Type: application/json" \
  -d '{"game_uuid": "7d3e8f84-1312-11ef-afd1-646009f18b2e", "interval": 10}'

# Check state
curl http://localhost:5133/state | jq

# Get all plays
curl http://localhost:5133/plays | jq '.plays | length'
```

### Test 3: Test Historical Comparison

```python
from nfl_pro_integration import nfl_pro_generator

# Get tendencies
tendencies = nfl_pro_generator.get_situational_tendency('KC', 'red_zone')
print(tendencies)

# Compare a play
play = {
    'off_formation': 'SHOTGUN',
    'off_personnel': '1 RB, 1 TE, 3 WR',
    'play_type': 'pass',
    'yards_to_go': 7,
    'down': 3,
}
insights = nfl_pro_generator.generate_play_insight(play, {})
print(insights)
```

### Test 4: Full Integration Test

1. Start all services:
```bash
# Terminal 1: Insight Engine
cd /Volumes/main-drive/ai-PA/auto-madden/insight-engine
python3 insight_engine.py

# Terminal 2: NFL Pro Poller
cd /Volumes/main-drive/ai-PA/auto-madden/nfl-pro-scraper
python3 scrapers/live_poller.py --port 5133

# Terminal 3: Simulator (or ESPN live)
cd /Volumes/main-drive/ai-PA/auto-madden/simulator
python3 game_simulator.py serve --port 5132
```

2. Start the companion UI:
```bash
cd /Volumes/main-drive/ai-PA/auto-madden/companion-ui
python3 app.py
```

3. Connect to a game and verify:
- Formation-based insights appear
- Personnel package analysis shows
- Historical comparisons are included

## Next Steps

1. **Find Live Game UUID**: During a live game, navigate to pro.nfl.com and extract the UUID from the URL
2. **Coordinate Polling**: Sync NFL Pro polling with ESPN polling for complete data
3. **Add More Insight Templates**: Expand formation/personnel combinations
4. **Cache Team Tendencies**: Pre-compute tendencies at game start
5. **UI Enhancements**: Show formation/personnel in play display

## Data Fields Available

| Field | Description | Example |
|-------|-------------|---------|
| `off_formation` | Offensive formation | SHOTGUN, UNDER_CENTER |
| `off_personnel` | Offensive personnel | 1 RB, 1 TE, 3 WR |
| `def_personnel` | Defensive personnel | 4 DL, 3 LB, 4 DB |
| `defenders_in_box` | Box count | 7 |
| `pass_rushers` | Rush count | 4 |
| `coverage_type` | Coverage scheme | COVER_2 |
| `man_zone` | Man or Zone | MAN |
| `air_yards` | Pass depth | 12.5 |
| `time_to_throw` | Release time | 2.8 |
| `was_pressure` | Pressure flag | True/False |
| `route` | Receiver route | CURL |

## Troubleshooting

### "No NFL Pro session"
Run `nfl_pro_login.py` to authenticate:
```bash
cd /Volumes/main-drive/ai-PA/auto-madden/nfl-pro-scraper
python3 session/nfl_pro_login.py
```

### Plays not capturing
- Check browser session hasn't expired
- Verify game UUID is correct
- Check network connectivity to pro.nfl.com

### Historical queries slow
- Ensure indexes exist on plays table
- Pre-cache frequently queried combinations


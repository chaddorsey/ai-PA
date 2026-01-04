# NFL Pro Scraper

Playwright-based scraper for NFL Pro (pro.nfl.com) game data, providing rich contextual information for the Auto-Madden game companion.

## Overview

This scraper extracts comprehensive game data from NFL Pro, including:
- **Game Overview**: Matchup comparisons, projections, injury info, last 5 games
- **Box Score**: Detailed stats, win probability charts (real-time during games)
- **Play-by-Play**: All plays with hidden data accessible via filters
- **Insights**: Player-specific narrative insights categorized by type

## Data Structure

```
nfl-pro-scraper/
├── README.md                    # This file
├── requirements.txt             # Python dependencies
├── Dockerfile                   # Container build
│
├── session/                     # Session management
│   ├── nfl_pro_login.py        # Manual login capture
│   └── session_keeper.py       # Automated session refresh
│
├── scrapers/                    # Individual scrapers
│   ├── game_overview.py        # Overview tab scraper
│   ├── box_score.py            # Box score + win probability
│   ├── play_by_play.py         # Play-by-play data
│   └── insights.py             # Narrative insights
│
├── models/                      # Data models
│   ├── game.py                 # Game data models
│   ├── insights.py             # Insight categorization
│   └── plays.py                # Play-by-play models
│
├── storage/                     # Data persistence
│   ├── game_cache.py           # JSON-based game cache
│   └── live_state.py           # Live game state updates
│
├── api/                         # API endpoints
│   └── scraper_api.py          # Flask API for companion
│
└── config/                      # Configuration
    └── nfl_pro_config.py       # Service configuration
```

## URL Patterns

NFL Pro game URLs follow this pattern:
```
Base: https://pro.nfl.com/games/game/{game_uuid}/
Tabs:
  - Overview:    /games/game/{uuid}/
  - Box Score:   /games/game/{uuid}/box-score
  - Play-by-Play:/games/game/{uuid}/play-by-play
  - Insights:    /games/game/{uuid}/insights
```

Game UUIDs are unique identifiers like: `f979d7ee-311e-11f0-b670-ae1250fadad1`

## Insight Categorization

Insights are categorized by:
1. **Entity Count**: Single or Dual entity
2. **Team Scope**: Single-team or Dual-team (for dual-entity)
3. **Entity Type**: Player or Team Unit
4. **Content Structure**: Primary paragraph (salient) + Secondary paragraph (detailed)

Example categories:
- Single-entity: "Ricky Pearsall (WR, SF)" 
- Dual-entity, dual-team: "Sam Darnold vs Brock Purdy (QBs)"
- Dual-entity, dual-team: "SEA Defense vs SF Defense"
- Dual-entity, single-team: "SF Defense + Fred Warner"

## Usage

### 1. Initial Login Capture

```bash
# Run this to open a browser for manual login
python session/nfl_pro_login.py

# This saves cookies/state to credentials/nfl_pro_state.json
```

### 2. Start Scraper API

```bash
# Standalone
python api/scraper_api.py

# Or via Docker
docker-compose up auto-madden-nfl-scraper
```

### 3. Scrape Game Data

```python
# Programmatic usage
from scrapers import NFLProScraper

scraper = NFLProScraper()
game_data = await scraper.scrape_full_game("f979d7ee-311e-11f0-b670-ae1250fadad1")

# Access specific data
overview = game_data.overview
box_score = game_data.box_score
plays = game_data.plays
insights = game_data.insights
```

### 4. Live Game Updates

```python
# For live games, poll specific tabs
live_data = await scraper.scrape_live_updates(game_uuid)
# Returns: current score, win probability, latest plays, new insights
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/games` | GET | List available/recent games |
| `/game/{uuid}` | GET | Get full game data |
| `/game/{uuid}/live` | GET | Get live updates only |
| `/game/{uuid}/plays` | GET | Get play-by-play |
| `/game/{uuid}/insights` | GET | Get categorized insights |
| `/session/status` | GET | Check login session |
| `/session/refresh` | POST | Refresh session |

## Integration with Auto-Madden Companion

The scraper provides data to the insight engine:

```python
# In insight_engine.py
from nfl_pro_client import NFLProClient

nfl_client = NFLProClient()

# Pre-game: load full context
game_data = nfl_client.get_game(game_uuid)
context_loader.set_nfl_pro_data(game_data)

# During game: poll for updates
live_data = nfl_client.get_live_updates(game_uuid)
```

## Session Management

Sessions are maintained following the pattern from sports-and-media-tools:

1. **Manual Login**: `nfl_pro_login.py` opens a visible browser
2. **State Capture**: Cookies and localStorage saved to JSON
3. **Auto-Refresh**: `session_keeper.py` periodically validates/refreshes
4. **Headless Scraping**: Actual scraping uses saved state

## Notes

- NFL Pro requires authentication (NFL+ subscription)
- Session typically lasts 7-14 days before requiring re-login
- Rate limit scraping to avoid detection
- Cache game data locally to reduce API calls
- Live polling should be no more frequent than every 10 seconds


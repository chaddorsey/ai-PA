# NFL Pro Scraper - Investigation Summary

**Date**: January 3-4, 2026  
**Game Tested**: SEA @ SF (f979d7ee-311e-11f0-b670-ae1250fadad1)

## Session Setup ✅

Successfully set up persistent browser context for NFL Pro login:
- Uses `launch_persistent_context` to avoid automation detection
- Stores session in `credentials/chrome_profile_nfl/`
- Captures 57 cookies for authenticated access
- Session persists between runs

---

## 🎯 API Discovery - COMPLETE SUCCESS

### Plays API ✅ WORKING
**Endpoint**: `https://pro.nfl.com/api/secured/plays/playlist/game?gameId={gameId}`

| Field | API Location | Example Value |
|-------|--------------|---------------|
| **Play Type** | `playType` | `play_type_pass`, `play_type_rush` |
| **Personnel (Offense)** | `offense.personnel` | `"1 RB, 2 TE, 2 WR"` |
| **Off Formation** | `offense.offenseFormation` | `"PISTOL"`, `"SINGLEBACK"` |
| **Pass Rush Count** | `defense.numberOfPassRushers` | `4` |
| **In The Box Count** | `defense.defendersInTheBox` | `6` |
| **Coverage Type** | `defense.coverageType` | `"COVER_4"` |
| **Man/Zone** | `defense.manZoneType` | `"ZONE_COVERAGE"` |
| **Personnel (Defense)** | `defense.personnel` | `"4 DL, 3 LB, 4 DB"` |
| **Air Yards** | `passInfo.airYards` | `2.22` |
| **Time To Throw** | `passInfo.timeToThrow` | `1.902` |
| **Pressure** | `passInfo.wasPressure` | `false` |
| **Route** | `recInfo.route` | `"FLAT"` |

**Sample Output**:
```
Q1 1&10 at SEA 30
Formation: PISTOL
Personnel (O): 1 RB, 2 TE, 2 WR
Personnel (D): 4 DL, 3 LB, 4 DB
Pass Rushers: 4
In The Box: 6
Coverage: COVER_4
Route: FLAT
```

### Insights API ✅ WORKING
**Endpoint**: `https://pro.nfl.com/api/content/insights/game?season={season}&limit=100&tags=...`

**Note**: Requires 30+ second wait for graphics-heavy content to load

| Field | Description |
|-------|-------------|
| `title` | Main insight text |
| `subNote1` | Secondary detail paragraph |
| `playerName`, `position`, `teamAbbr` | Primary entity |
| `secondPlayerName`, `secondTeamAbbr` | Secondary entity (matchups) |
| `secondTeamType` | `"defense"` or `"offense"` |
| `imageUrl` | Chart/graphic URL |
| `tags` | `["next-gen-stats", "postgame", "pro-preview"]` |

**Retrieved**: 48 insights for SEA @ SF game

### Other APIs Discovered

| API | Endpoint |
|-----|----------|
| Game Details | `/api/schedules/game?fapiGameId={uuid}` |
| Live Scores | `/api/scores/live/games?season={season}&seasonType={type}&week={week}` |
| Teams | `/api/teams/all` |
| Standings | `/api/schedules/standings?season={season}&seasonType={type}` |
| Odds | `/api/schedules/week/odds?season={season}&seasonType={type}&week={week}` |
| Fantasy Stats | `/api/secured/stats/fantasy/season?season={season}&limit=500` |

---

## Implementation

### New API Client
**File**: `scrapers/nfl_pro_api.py`

```python
async with NFLProAPIClient(headless=True) as client:
    plays = await client.get_plays(game_uuid)
    insights = await client.get_insights(game_uuid, wait_time=30)
```

### Data Models
- `PlayData`: Complete play with offense/defense details
- `InsightData`: Structured insight with player/team info

---

## Technical Notes

### Browser Configuration
```python
context = await p.chromium.launch_persistent_context(
    user_data_dir=str(user_data_dir),
    headless=True,
    args=['--disable-blink-features=AutomationControlled'],
    ignore_default_args=['--enable-automation'],
)
```

### Credential Storage
- Session state: `credentials/browser_states/nfl_pro_state.json`
- Chrome profile: `credentials/chrome_profile_nfl/`

---

## Next Steps

1. ✅ ~~Find Play Type, Personnel, Formation, Pass Rush, Box Count~~ - **DONE**
2. ✅ ~~Get Insights API working~~ - **DONE (30s wait required)**
3. **Integrate with companion**: Feed data to insight engine
4. **Add game discovery**: Find game UUIDs from schedule page
5. **Real-time polling**: Implement live game updates
6. **Cache management**: Store scraped data efficiently


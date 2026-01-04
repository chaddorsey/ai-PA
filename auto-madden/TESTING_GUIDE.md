# Auto-Madden Testing Guide

## Quick Start for Live Game Testing (Week 18)

### Prerequisites
- Week 18 insights are pre-processed and ready (337 insights)
- Background scraper is collecting insights for earlier weeks

### NFL Pro Session (for live play metadata)

If you want rich play metadata (personnel, formation, defenders in box), you need an active NFL Pro session:

```bash
cd auto-madden/nfl-pro-scraper
python3 session/nfl_pro_login.py
```

This opens a browser - log into pro.nfl.com, then the session is saved automatically.

**Without NFL Pro session:** The companion still works but falls back to ESPN-only mode (basic play descriptions, no personnel/formation data).

### Start the Services

1. **Start the simulator/game state service** (handles ESPN feeds):
```bash
cd auto-madden/simulator
python3 game_simulator.py serve --port 5132
```

2. **Start the insight engine** (generates insights, handles WebSocket):
```bash
cd auto-madden/insight-engine
python3 insight_engine.py
```

3. **Start the companion UI** (Flask web app):
```bash
cd auto-madden/companion-ui
python3 app.py
```

4. **Open the companion UI**:
   Navigate to `http://localhost:5130/simple` in your browser

### Using the Companion

1. **Select a game** from the dropdown in the top-right corner
   - Live games appear first with 🔴 indicator
   - Scheduled games appear below

2. **Click "Start Live"** to begin receiving updates

3. **Adjust delay** via the settings gear (⚙️) to sync with your TV

4. **Watch for**:
   - Score updates in the top box
   - Pre-play metadata (orange box) appearing before snaps
   - Insights (teal cards) appearing throughout the game
   - Extended insights during commercial breaks

### Insight Sources

The companion draws from:
- **NFL Pro pre-processed insights** (337 for Week 18)
- **ESPN live game data** (real-time plays and scores)
- **Template-based insights** (formations, personnel analysis)
- **Break detection** (commercial breaks, timeouts, halftime)

---

# Original Testing Guide: GB @ MIN

This guide walks you through testing the companion with the Packers @ Vikings game (Dec 29, 2024).

## Quick Reference: Scoring Plays

Use these to sync your NFL+ video with the simulator:

| Quarter | Clock | Score | Event |
|---------|-------|-------|-------|
| Q1 | 1:47 | GB 3-0 | McManus 22yd FG |
| Q2 | 11:52 | GB 3-7 | Nailor 31yd TD catch |
| Q2 | 2:16 | GB 3-10 | Reichard 25yd FG |
| Q2 | 0:00 | GB 3-13 | Reichard 50yd FG (halftime) |
| Q3 | 9:44 | GB 3-20 | Addison 18yd TD |
| Q3 | 5:07 | GB 10-20 | Jacobs 2yd TD run |
| Q3 | 0:51 | GB 10-27 | Akers 9yd TD catch |
| Q4 | 6:12 | GB 18-27 | Wilson 5yd TD + 2pt |
| Q4 | 2:18 | GB 25-27 | Heath 3yd TD (final Packers score) |

**Final: Vikings 27, Packers 25** (Close finish - great for testing!)

---

## Step 1: Open 3 Terminal Windows

### Terminal 1: Simulator (Game State Service)

```bash
cd /Volumes/main-drive/ai-PA/auto-madden/simulator
python3 game_simulator.py serve --port 5132
```

You should see:
```
Starting simulator server on port 5132
This replaces game-state-service for testing
```

### Terminal 2: Insight Engine

```bash
cd /Volumes/main-drive/ai-PA/auto-madden/insight-engine
pip3 install -r requirements.txt
python3 insight_engine.py
```

You should see:
```
Starting Auto-Madden Insight Engine
```

### Terminal 3: Companion UI

```bash
cd /Volumes/main-drive/ai-PA/auto-madden/companion-ui
pip3 install -r requirements.txt
python3 app.py
```

You should see:
```
Starting Auto-Madden Companion UI
```

---

## Step 2: Open NFL+ and the Companion UI

1. **NFL+ Premium**: Find and start the GB @ MIN game (Dec 29, Week 17)
2. **Browser**: Open http://localhost:5130

---

## Step 3: Start the Simulation

You have two options:

### Option A: Start from Beginning (sync manually)

In a new terminal or use curl:

```bash
curl -X POST http://localhost:5132/start \
  -H "Content-Type: application/json" \
  -d '{"game_id": "401671725", "speed": 1.0}'
```

Then sync the NFL+ video to match the simulator.

### Option B: Jump to a Specific Point

Start the simulation:
```bash
curl -X POST http://localhost:5132/start \
  -H "Content-Type: application/json" \
  -d '{"game_id": "401671725", "speed": 1.0, "start_quarter": 3, "start_clock": "10:00"}'
```

Seek the NFL+ video to Q3 10:00.

---

## Step 4: Control the Simulation

### Pause (when you need to sync)
```bash
curl -X POST http://localhost:5132/pause
```

### Resume
```bash
curl -X POST http://localhost:5132/resume
```

### Change Speed
```bash
# Speed up to catch up with video
curl -X POST http://localhost:5132/speed -H "Content-Type: application/json" -d '{"speed": 2.0}'

# Back to real-time
curl -X POST http://localhost:5132/speed -H "Content-Type: application/json" -d '{"speed": 1.0}'
```

### Jump to a Time
```bash
curl -X POST http://localhost:5132/jump \
  -H "Content-Type: application/json" \
  -d '{"quarter": 4, "clock": "6:00"}'
```

### Check Status
```bash
curl http://localhost:5132/state | python3 -m json.tool
```

---

## Step 5: Interact with the Companion

In the companion UI (http://localhost:5130):

1. Watch for pushed insights as plays happen
2. Ask questions:
   - "What's an RPO?"
   - "Who is Jordan Love?"
   - "Why did they go for two there?"
   - "What do the Packers need to do to win?"

---

## Key Testing Moments

### High-Stakes Situations (Test reduced frequency)

- **Q4 6:00+**: Packers down 27-10, mounting comeback
- **Q4 2:18**: Packers score, now 27-25
- **Final 2 minutes**: Maximum tension

### Scoring Plays (Test score insights)

Jump to just before each scoring play to test reactions.

### Turnover (if any)

Check for turnover detection and insights.

---

## Troubleshooting

### "No simulation running"
Start it: `curl -X POST http://localhost:5132/start -d '{"game_id": "401671725"}'`

### WebSocket not connecting
Check that insight-engine is running on port 5131.

### No insights appearing
1. Check Terminal 2 for insight-engine logs
2. Verify ANTHROPIC_API_KEY is set if using LLM insights

### Sync issues
Use pause/resume and speed controls to catch up or wait.

---

## Feedback Checklist

While testing, note:

- [ ] Are insights arriving at good times (not during active plays)?
- [ ] Is the frequency right (not too many, not too few)?
- [ ] Are the insights helpful for your knowledge level?
- [ ] Do questions get good answers?
- [ ] Does the UI feel responsive?
- [ ] Any missing insight types you'd want?

---

## Stop Testing

```bash
curl -X POST http://localhost:5132/stop
```

Then Ctrl+C in each terminal.


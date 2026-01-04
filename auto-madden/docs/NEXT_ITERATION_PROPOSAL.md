# Auto-Madden Next Iteration Proposal

**Prepared:** January 3, 2026  
**Status:** Ready for Review

---

## Executive Summary

This proposal addresses four key areas for improving the Auto-Madden companion:
1. **Richer, more natural commentary** with varied templates and LLM-generated insights
2. **Pre-game team/matchup context** loaded before the game starts
3. **In-game evolving context** tracked throughout the game
4. **Broadcast delay handling** for sync with live TV

---

## 1. Richer, More Natural Commentary

### Current Problem
Templates are repetitive and stilted. "1st & 10: establishing the run?" gets old quickly.

### Solution: Multi-Layer Insight Generation

#### Layer 1: Template Variety (Fast, Cheap)
- Expand each situation to 10-15 variations
- Include personality/tone variations ("Let's see what they dial up here" vs "Standard first down situation")
- Track recently used templates to avoid repetition

```python
FIRST_DOWN_TEMPLATES = [
    {"headline": "Fresh set of downs", "body": "Ten yards, four chances. The playbook is wide open."},
    {"headline": "1st & 10", "body": "Most teams run here 45% of the time. Sets up play-action later."},
    {"headline": "New series", "body": "Watch the formation—extra tight ends usually means run."},
    {"headline": "Possession football", "body": "Move the chains, control the clock."},
    # ... 10+ more variations
]
```

#### Layer 2: Context-Aware Selection
Choose templates based on:
- Game situation (score differential, time remaining)
- Team tendencies (run-heavy team? pass-happy?)
- Recent game flow (just had a big play? turnover?)

#### Layer 3: LLM-Enhanced Insights (Rich, Occasional)
For significant moments, use LLM to generate unique insights:
- Scoring plays
- Turnovers  
- Key third/fourth downs
- Momentum shifts
- End of half/game situations

**Architecture Change:** Add an `insight_personality` config that sets the tone (analytical, casual, enthusiastic, educational).

---

## 2. Pre-Game Team & Matchup Context

### Available ESPN Data (Verified)

| Endpoint | Data Available |
|----------|---------------|
| `/teams/{id}` | Name, colors, logos |
| `/teams/{id}/statistics` | Season stats (passing, rushing, defense, etc.) |
| `/teams/{id}?enable=record` | Season record, division standing |
| `/teams/{id}/schedule` | Recent game results |
| `/scoreboard` | Odds, spread, over/under from DraftKings |

### Pre-Game Context Object

```python
@dataclass
class MatchupContext:
    """Loaded once at game start, stored in Letta agent memory."""
    
    # Team identities
    home_team: TeamProfile
    away_team: TeamProfile
    
    # Season context
    home_record: str  # "8-8"
    away_record: str
    home_division_standing: int
    away_division_standing: int
    
    # Statistical tendencies
    home_run_rate: float  # % of plays that are runs
    away_run_rate: float
    home_pass_yards_per_game: float
    away_pass_yards_per_game: float
    home_points_per_game: float
    away_points_per_game: float
    home_points_allowed_per_game: float
    away_points_allowed_per_game: float
    
    # Betting context
    spread: float  # e.g., -3.0 means home favored by 3
    over_under: float
    
    # Narrative context (LLM-generated summary)
    matchup_narrative: str  # "Division rivals meet with playoff implications..."
    
    # Key players to watch
    players_to_watch: List[PlayerHighlight]
```

### Loading Flow

```
Game Selected → Fetch Team Stats (parallel) → Generate Matchup Narrative (LLM) → Store in Context
```

### Letta Agent Integration
- Store `MatchupContext` in agent's archival memory at game start
- Agent can reference "The Vikings are averaging 20.5 PPG this season"
- Sleeptime agent can update narrative as game evolves

---

## 3. In-Game Evolving Context

### Key Metrics to Track

#### Box Score Stats (Query from ESPN)
- Total yards, rushing yards, passing yards
- Time of possession
- Third down conversion rate
- Turnovers
- Sacks given up

#### Derived/Computed Metrics (Track in Memory)
- **Run/Pass ratio this game** vs season average
- **Scoring efficiency** (points per red zone trip)
- **Momentum score** (recent plays trending positive/negative)
- **Fatigue indicators** (time of possession, play count)
- **Clock management** (are they rushing? milking clock?)

### In-Game State Object

```python
@dataclass
class GameFlowState:
    """Updated after each drive/significant play."""
    
    # Current game stats
    home_total_yards: int
    away_total_yards: int
    home_rushing_yards: int
    away_rushing_yards: int
    home_passing_yards: int
    away_passing_yards: int
    home_time_of_possession: str
    away_time_of_possession: str
    home_third_down_conversions: str  # "3/7"
    away_third_down_conversions: str
    
    # Trend analysis
    home_run_rate_this_game: float  # vs season average
    away_run_rate_this_game: float
    momentum_indicator: str  # "home", "away", "neutral"
    
    # Play history for pattern detection
    last_10_plays: List[PlaySummary]
    
    # Key moments
    lead_changes: int
    biggest_lead: int
    scoring_summary: List[ScoringPlay]
```

### Pattern Detection Rules

```python
PATTERN_RULES = {
    "run_heavy": {
        "condition": "run_rate_this_game > season_run_rate + 0.10",
        "insight": "They're pounding the rock more than usual—{yards} rushing yards so far"
    },
    "abandoning_run": {
        "condition": "run_rate_this_game < season_run_rate - 0.15",
        "insight": "Run game isn't working—only {run_yards} yards on {attempts} carries"
    },
    "defense_tiring": {
        "condition": "opponent_time_of_possession > 35:00 and quarter >= 3",
        "insight": "Defense has been on the field a lot—fatigue could be a factor"
    },
    "shootout": {
        "condition": "combined_score > over_under * 0.7 and quarter < 4",
        "insight": "We're on pace to crush the over—defenses can't stop anyone"
    },
    "defensive_battle": {
        "condition": "combined_score < over_under * 0.3 and quarter >= 2",
        "insight": "Low-scoring affair—field position and turnovers will decide this"
    }
}
```

### What to Store Where

| Data Type | Storage | Why |
|-----------|---------|-----|
| Pre-game context | Letta archival memory | Persistent, queryable by agent |
| Current box score | ESPN API query | Always fresh, no storage needed |
| Last 10 plays | In-memory (insight engine) | Immediate access for patterns |
| Key moments | Letta archival memory | For narrative building |
| Momentum score | Computed on demand | Derived metric |

---

## 4. External Analytics Frameworks

### Available Resources

#### nfl-data-py / nflfastR Ecosystem
- **What it provides:** Historical play-by-play data, expected points models, win probability models
- **Best for:** Pre-computing team tendencies, historical context
- **Integration:** Download season data, compute team profiles offline

#### ESPN's Built-in Analytics
- **Win probability:** Available in game summary (`winprobability` array)
- **Expected points:** Not directly exposed, but can be estimated
- **Already using:** We parse this in the simulator

#### Custom Models (Future)
- Fourth down decision model (go for it vs punt/kick)
- Play prediction model (run vs pass based on situation)
- EPA (Expected Points Added) per play

### Recommended Integration Path

**Phase 1 (Now):** Use ESPN data + simple pattern rules
**Phase 2 (Next):** Add nfl-data-py for team tendency profiles  
**Phase 3 (Future):** Custom ML models for predictions

---

## 5. Broadcast Delay Handling

### The Problem
- Live TV broadcasts are delayed 5-30+ seconds from real-time
- If we use live ESPN data, we'll spoil plays before they happen on TV
- User needs to sync our companion with their specific broadcast

### Solution: Delay Calibration System

#### UI Component: "That Just Happened" Button

```
┌────────────────────────────────────────────────────┐
│  🏈 Auto-Madden Companion                          │
├────────────────────────────────────────────────────┤
│  Q2 · 8:45  |  GB 10 - MIN 14  |  2nd & 7         │
├────────────────────────────────────────────────────┤
│                                                    │
│  [Latest insight shown here]                       │
│                                                    │
│  ┌──────────────────────────────────────────────┐  │
│  │  ⏱️ Sync: When you see a score on TV,       │  │
│  │     click here:  [ That Just Happened! ]    │  │
│  │     Current delay: ~12 seconds              │  │
│  └──────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────┘
```

#### Calibration Flow

1. **User watches TV, sees a scoring play**
2. **User clicks "That Just Happened!"**
3. **System compares:**
   - TV timestamp (button press time)
   - Our timestamp (when we received the scoring play event)
   - Delay = Our time - Button press time
4. **System applies delay to all future insights**
5. **Repeat for accuracy** (average multiple samples)

#### Implementation

```python
class BroadcastSync:
    """Manages delay between real-time data and TV broadcast."""
    
    def __init__(self):
        self.delay_samples: List[float] = []
        self.current_delay: float = 0.0  # seconds
        self.pending_events: List[Tuple[float, Dict]] = []  # (release_time, event)
    
    def record_sync_point(self, event_type: str):
        """User clicked 'That Just Happened' for an event type."""
        button_time = time.time()
        
        # Find the most recent event of this type
        for event_time, event in reversed(self.pending_events):
            if event.get('type') == event_type:
                delay = event_time - button_time
                self.delay_samples.append(delay)
                self._recalculate_delay()
                break
    
    def _recalculate_delay(self):
        """Average recent samples, weighted toward recent."""
        if self.delay_samples:
            # Use last 5 samples, weighted
            recent = self.delay_samples[-5:]
            self.current_delay = sum(recent) / len(recent)
    
    def queue_event(self, event: Dict):
        """Queue an event to be released after the delay."""
        event_time = time.time()
        release_time = event_time + self.current_delay
        heapq.heappush(self.pending_events, (release_time, event))
    
    def get_ready_events(self) -> List[Dict]:
        """Get events ready to be shown (delay has passed)."""
        ready = []
        now = time.time()
        while self.pending_events and self.pending_events[0][0] <= now:
            _, event = heapq.heappop(self.pending_events)
            ready.append(event)
        return ready
```

#### Manual Delay Override
```
Delay: [Auto ▼]  |  [ -5s ] [ -1s ] [ +1s ] [ +5s ]
```

---

## 6. Architecture Updates

### Current Architecture
```
ESPN API → Simulator → Insight Engine → WebSocket → UI
```

### Proposed Architecture
```
                                    ┌─────────────────┐
                                    │ Letta Sleeptime │
                                    │ Agent           │
                                    │ (Narrative &    │
                                    │  Memory)        │
                                    └────────┬────────┘
                                             │
┌──────────┐    ┌──────────────┐    ┌────────┴────────┐    ┌──────────┐
│ ESPN API │───▶│ Game State   │───▶│ Insight Engine  │───▶│ Delay    │───▶ UI
│          │    │ Service      │    │ + Context Mgr   │    │ Buffer   │
└──────────┘    └──────────────┘    └────────┬────────┘    └──────────┘
                       │                     │
                       ▼                     ▼
              ┌──────────────┐      ┌──────────────┐
              │ Team Context │      │ Game Flow    │
              │ Service      │      │ Tracker      │
              │ (pre-game)   │      │ (in-game)    │
              └──────────────┘      └──────────────┘
```

### New Components

#### 1. Team Context Service
- Fetches team stats, records, schedules at game start
- Generates matchup narrative via LLM
- Caches for the session

#### 2. Game Flow Tracker  
- Maintains running box score stats
- Detects patterns and trends
- Provides context to insight engine

#### 3. Delay Buffer
- Queues all events
- Releases after calibrated delay
- Handles sync button callbacks

#### 4. Letta Integration Points
- **Main Agent:** Handles user queries with full context
- **Sleeptime Agent:** Monitors game flow, updates narratives, manages memory

---

## 7. Implementation Priority

### For Today's 4:25 Game (1 hour)

1. **Add delay buffer** (critical for live games)
2. **Expand template variety** (quick win)
3. **Add "That Just Happened" button** to UI

### Next Session

4. **Add Team Context Service** (pre-game loading)
5. **Add Game Flow Tracker** (in-game patterns)
6. **LLM-enhanced insights** for key moments

### Future

7. **nfl-data-py integration** for historical context
8. **Full Letta agent integration**
9. **Personnel/formation detection** (if data available)

---

## 8. Quick Wins for Today

### Template Expansion (5 minutes each)

Add to `insight_engine.py`:

```python
FIRST_DOWN_INSIGHTS = [
    {"h": "Fresh set of downs", "b": "Ten yards, four chances."},
    {"h": "1st & 10", "b": "Establish the run or go for chunk plays?"},
    {"h": "New series begins", "b": "Watch the formation for clues."},
    {"h": "First down", "b": "The playbook is wide open here."},
    {"h": "Moving the chains", "b": "Possession football, control the clock."},
]

# Random selection with recency avoidance
def get_varied_insight(category, context):
    options = INSIGHT_TEMPLATES[category]
    # Avoid last 3 used
    available = [o for o in options if o not in recently_used[-3:]]
    choice = random.choice(available or options)
    recently_used.append(choice)
    return choice
```

### Delay Buffer (15 minutes)

Add delay handling to insight delivery:

```python
class DelayedInsightQueue:
    def __init__(self, delay_seconds=10):
        self.delay = delay_seconds
        self.queue = []
    
    def add(self, insight):
        release_time = time.time() + self.delay
        heapq.heappush(self.queue, (release_time, insight))
    
    def get_ready(self):
        ready = []
        now = time.time()
        while self.queue and self.queue[0][0] <= now:
            _, insight = heapq.heappop(self.queue)
            ready.append(insight)
        return ready
```

### Sync Button UI (10 minutes)

Add to `index.html`:
```html
<div class="sync-controls">
    <span>📺 Broadcast Sync</span>
    <button id="btn-sync" class="sync-button">That Just Happened!</button>
    <span id="delay-display">Delay: --</span>
</div>
```

---

## Summary

| Priority | Feature | Time | Impact |
|----------|---------|------|--------|
| 🔴 Critical | Delay buffer for live games | 15 min | Prevents spoilers |
| 🟡 High | Template variety | 20 min | Better UX |
| 🟡 High | Sync button | 10 min | User control |
| 🟢 Medium | Team context loading | 30 min | Richer insights |
| 🟢 Medium | Game flow tracking | 30 min | Pattern detection |
| 🔵 Future | Letta integration | 2 hrs | Full agent memory |

---

*Ready for review. Implementation can begin immediately on your return.*


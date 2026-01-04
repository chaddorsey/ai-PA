# PBI-29: Auto-Madden Real-Time Game Companion

[View in Backlog](../backlog.md#user-content-PBI-29)

## Overview

Auto-Madden is a real-time AI companion for watching NFL games (and eventually other sports). It provides contextual insights, explanations, and commentary tuned to the viewer's knowledge level and engagement preferences. Think "John Madden on your couch" - but perfectly sensitive to your understanding of the game and respectful of your attention on the actual action.

## Problem Statement

Watching NFL games can be challenging for intermediate fans who:
- Understand basic rules but want to learn strategic nuances
- Can follow the action but miss contextual significance of plays
- Know some players but lack historical context for records and milestones
- Want to deepen their knowledge without being overwhelmed

Current solutions (broadcast commentary, second-screen apps) don't adapt to individual knowledge levels and often distract from rather than enhance the viewing experience.

## User Stories

1. **As a viewer**, I want to start a game companion session by saying "Watch the Patriots game" so that I can get real-time insights during the game.

2. **As a viewer**, I want to understand what just happened on a play with context (why it mattered, what to expect next) without pausing or looking away from the TV.

3. **As a viewer**, I want the companion to stay out of my way during intense game action but be more helpful during slower periods.

4. **As a viewer**, I want to ask questions about the game ("What's an RPO?" "Who's that receiver?") and get concise, contextual answers.

5. **As a viewer**, I want the companion to remember what I've learned and adapt its explanations to my growing knowledge level.

6. **As a viewer**, I want insights about significant moments (records approached, momentum shifts, critical decisions) pushed to me at appropriate times.

## Technical Approach

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Auto-Madden Architecture                              │
│                                                                              │
│  User Interface                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  companion-ui (Flask + WebSocket) - Port 5130                        │   │
│  │  - Browser-based chat interface                                       │   │
│  │  - Real-time insight display                                          │   │
│  │  - Session management (start/stop game watching)                      │   │
│  └────────────────────────────────────────────────────────────────────┬─┘   │
│                                                                       │     │
│  Orchestration                                                        │     │
│  ┌────────────────────────────────────────────────────────────────────▼─┐   │
│  │  insight-engine (Python service) - Port 5131                         │   │
│  │  - Receives game state changes                                        │   │
│  │  - Generates insights (template + LLM paths)                          │   │
│  │  - Manages delivery frequency and user attention model                │   │
│  │  - Routes to Letta for memory-enriched responses                      │   │
│  └───────────────────────────────────────────────────────────────────┬──┘   │
│                                                                      │      │
│          ┌───────────────────────┬───────────────────┬───────────────┘      │
│          ▼                       ▼                   ▼                      │
│  ┌───────────────┐      ┌───────────────┐   ┌───────────────┐              │
│  │ Letta Main    │      │ Letta Sleep   │   │ Direct LLM    │              │
│  │ Agent         │      │ Agent         │   │ (Anthropic/   │              │
│  │ (user Q&A,    │      │ (aggregation, │   │  OpenAI/etc)  │              │
│  │  memory)      │      │  summaries)   │   │               │              │
│  └───────────────┘      └───────────────┘   └───────────────┘              │
│                                                                              │
│  Data Layer                                                                  │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  game-state-service (Python service) - Port 5132                     │   │
│  │  - Polls ESPN API (2-5 sec during action, adaptive)                   │   │
│  │  - Maintains GameState model                                          │   │
│  │  - Detects changes: plays, scores, turnovers, clock                   │   │
│  │  - Emits events to insight-engine                                     │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Components

#### 1. game-state-service (Port 5132)
Real-time game state management with ESPN API integration.

**Responsibilities:**
- Poll ESPN API summary endpoint for active game
- Parse play-by-play, drives, situation data
- Detect state changes (new plays, score changes, turnovers)
- Emit events to insight-engine via internal HTTP/WebSocket
- Adaptive polling: faster during active play, slower during stoppages

**Key Data Model:**
```python
@dataclass
class GameState:
    game_id: str
    status: str  # pre, in, halftime, post
    quarter: int
    clock: str
    down: int
    distance: int
    yard_line: int
    possession: str
    home_team: TeamInfo
    away_team: TeamInfo
    home_score: int
    away_score: int
    recent_plays: List[PlayEvent]
    current_drive: DriveInfo
    win_probability: Dict[str, float]
```

#### 2. insight-engine (Port 5131)
Insight generation and delivery orchestration.

**Responsibilities:**
- Receive game state change events
- Classify events by significance and insight potential
- Generate insights via:
  - Fast path: template-based for common situations
  - LLM path: Claude/GPT for nuanced explanations (rate-limited)
- Manage delivery timing and frequency
- Route user queries to Letta agent
- Track user attention model and adapt

**Insight Types:**
- `situation_explanation`: What this down/distance typically means
- `play_explanation`: What just happened and why
- `player_spotlight`: Notable player performance
- `strategic_observation`: Why a team made a choice
- `rule_explanation`: Clarify penalties or reviews
- `prediction`: What to watch for next
- `record_alert`: Approaching/breaking records
- `momentum_shift`: Win probability changes

**Delivery Rules:**
- Maximum 4 insights per minute (configurable)
- Minimum 8-second gap between insights
- Immediate delivery for major events (scores, turnovers)
- Queue insights during intense action
- Adapt frequency based on game pace and user engagement

#### 3. companion-ui (Port 5130)
Web-based chat interface for user interaction.

**Responsibilities:**
- WebSocket connection for real-time updates
- Display pushed insights with appropriate styling
- Accept user text queries
- Session management (start game, end session)
- Simple, distraction-free UI optimized for second-screen use

**MVP UI:**
- Single-page Flask app with WebSocket
- Chat-style insight display
- Input field for questions
- Game status header
- Minimal, dark-themed design

#### 4. Letta Tools
Custom tools registered with Letta agents for memory-enriched interactions.

**Main Agent Tools:**
- `get_current_game_state`: Retrieve current game situation
- `ask_game_question`: Answer user questions about the game
- `get_player_info`: Look up player details from ESPN
- `explain_play`: Detailed play breakdown with context
- `get_game_summary`: Drive-by-drive summary

**Sleeptime Agent Tools:**
- `summarize_game_insights`: Aggregate insights delivered during game
- `update_user_knowledge`: Track what user has learned
- `log_game_session`: Record session for future reference

### Data Sources

**ESPN Hidden API (Primary):**
```
# Scoreboard (find active games)
GET http://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard

# Game summary with play-by-play
GET http://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event={gameId}

# Player details
GET http://site.api.espn.com/apis/site/v2/sports/football/nfl/athletes/{athleteId}
```

### Agent Configuration

**Main Agent:** `agent-30ff1be2-3922-42fb-b7ee-458cb5a3bb07`
- Handles user questions and memory-enriched responses
- Remembers user's knowledge level and preferences
- Provides contextual explanations

**Sleeptime Agent:** `agent-89d31c34-de69-4f34-b388-9bd8d9b647fa`
- Aggregates insights and user interactions
- Updates user knowledge model
- Generates post-game summaries

## UX/UI Considerations

### Design Principles

1. **Companion, Not Distraction**: Never pull attention from game action
2. **Adaptive Presence**: More helpful during slow moments, invisible during intensity
3. **Progressive Knowledge**: Remember what user has learned, build on it
4. **Natural Interaction**: Conversational, not clinical
5. **Respectful Frequency**: Less is more; quality over quantity

### Insight Delivery Timing

| Game State | Insight Behavior |
|------------|------------------|
| Active play (clock running) | Queue non-urgent insights |
| Between plays | Deliver queued insights, one at a time |
| Timeout/commercial | Deeper context, multiple insights OK |
| Halftime | Summary, stats, predictions |
| Post-touchdown | Scoring play breakdown |
| Controversial call | Rule explanation |

### User Attention Model

Factors that influence delivery frequency:
- Game stakes (rivalry vs. casual viewing)
- Score differential (blowout vs. close game)
- User query frequency (engaged vs. passive)
- Time since last insight
- Importance of pending insight

## Acceptance Criteria

### 1. Session Management
- [ ] User can start a game session with natural language ("Watch the Patriots game")
- [ ] System identifies correct game from ESPN API
- [ ] Session remains active for duration of game
- [ ] User can end session explicitly or system detects game end

### 2. Real-Time Game State
- [ ] Game state updates within 5 seconds of ESPN API refresh
- [ ] Play-by-play accurately tracked
- [ ] Score, clock, situation properly maintained
- [ ] Polling frequency adapts to game state

### 3. Insight Generation
- [ ] Template-based insights generated for common situations
- [ ] LLM insights generated for significant/novel events
- [ ] Insights appropriate to intermediate knowledge level
- [ ] Variety of insight types (explanation, context, prediction)

### 4. Insight Delivery
- [ ] Maximum delivery rate respected (≤4/min)
- [ ] Minimum gap enforced (≥8 sec)
- [ ] High-priority events delivered immediately
- [ ] Lower-priority insights queued appropriately
- [ ] Frequency adapts to game pace

### 5. User Interaction
- [ ] User can ask questions via chat interface
- [ ] Questions routed to Letta agent with game context
- [ ] Responses draw on agent memory
- [ ] Agent remembers explanations given

### 6. Services Integration
- [ ] All services containerized with Docker
- [ ] Services communicate via pa-internal network
- [ ] Health checks implemented
- [ ] Graceful handling of ESPN API failures

## Dependencies

- Letta server running on port 8283
- ESPN API accessible (public, no auth required)
- Docker infrastructure for new services
- Anthropic/OpenAI API keys for LLM calls (already in .env)

## Open Questions

1. **Attention Sensing**: How do we detect user engagement level without explicit input?
   - Initial approach: Infer from query frequency and game state
   - Future: Could integrate with physical signals (phone pickup detection)

2. **Multi-Game Expansion**: How to extend to tracking multiple games?
   - Defer: Focus on single-game flow first

3. **Mid-Game Join**: How to catch user up when joining mid-game?
   - Defer: Build full-game flow first, then add catch-up feature

4. **Knowledge Persistence**: How much does agent remember across games?
   - Initial: Per-game session, with persistent user knowledge level
   - Future: Cross-game memory of team/player context discussed

## Future Enhancements (Not in Scope)

- Custom React frontend with rich visuals
- TV integration (auto-tune via watch_game tool)
- Slack notification channel for ambient updates
- College football and other sports
- Multi-game tracking (RedZone-style)
- Voice input/output
- Historical context database (nflverse data)
- Deep linking to streaming (ESPN+)

## Related Tasks

See [tasks.md](./tasks.md) for the task breakdown.


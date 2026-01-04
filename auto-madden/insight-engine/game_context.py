#!/usr/bin/env python3
"""
Game Context Loader for Auto-Madden.

Fetches comprehensive background information about teams, players, and matchups
from multiple APIs to provide rich context for insight generation.

Data Sources:
- ESPN API: Real-time stats, news, injuries, win probability
- API-Sports.io: Historical data, standings, head-to-head records
- (Future) NYT API: News articles about teams

Context is used for:
1. Pre-game matchup summaries
2. Break-time deeper analysis
3. LLM context for dynamic insight generation
4. Shareable articles/links during long breaks
"""

import os
import logging
import requests
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)

# API Configuration
ESPN_API_BASE = "https://site.api.espn.com/apis/site/v2/sports/football/nfl"
API_SPORTS_BASE = "https://v1.american-football.api-sports.io"
API_SPORTS_KEY = os.environ.get('SPORTS_API_KEY', '7355c699b35b350da7932d79dd865d84')

# Team ID mappings between ESPN and API-Sports
ESPN_TO_API_SPORTS_TEAM = {
    # NFC South
    '27': 24,  # Tampa Bay Buccaneers
    '29': 19,  # Carolina Panthers
    '1': 8,    # Atlanta Falcons
    '18': 27,  # New Orleans Saints
    # NFC West
    '26': 23,  # Seattle Seahawks
    '25': 14,  # San Francisco 49ers
    '22': 11,  # Arizona Cardinals
    '14': 31,  # Los Angeles Rams
    # NFC North
    '9': 15,   # Green Bay Packers
    '16': 32,  # Minnesota Vikings
    '3': 16,   # Chicago Bears
    '8': 7,    # Detroit Lions
    # NFC East
    '21': 12,  # Philadelphia Eagles
    '6': 29,   # Dallas Cowboys
    '19': 4,   # New York Giants
    '28': 18,  # Washington Commanders
    # AFC South
    '34': 26,  # Houston Texans
    '11': 21,  # Indianapolis Colts
    '30': 2,   # Jacksonville Jaguars
    '10': 6,   # Tennessee Titans
    # AFC West
    '12': 17,  # Kansas City Chiefs
    '24': 30,  # Los Angeles Chargers
    '7': 28,   # Denver Broncos
    '13': 1,   # Las Vegas Raiders
    # AFC North
    '33': 5,   # Baltimore Ravens
    '23': 22,  # Pittsburgh Steelers
    '4': 10,   # Cincinnati Bengals
    '5': 9,    # Cleveland Browns
    # AFC East
    '2': 20,   # Buffalo Bills
    '15': 25,  # Miami Dolphins
    '20': 13,  # New York Jets
    '17': 3,   # New England Patriots
}

# ESPN abbreviation to ID mapping
ESPN_ABBR_TO_ID = {
    'ARI': '22', 'ATL': '1', 'BAL': '33', 'BUF': '2', 'CAR': '29', 'CHI': '3',
    'CIN': '4', 'CLE': '5', 'DAL': '6', 'DEN': '7', 'DET': '8', 'GB': '9',
    'HOU': '34', 'IND': '11', 'JAX': '30', 'KC': '12', 'LAC': '24', 'LAR': '14',
    'LV': '13', 'MIA': '15', 'MIN': '16', 'NE': '17', 'NO': '18', 'NYG': '19',
    'NYJ': '20', 'PHI': '21', 'PIT': '23', 'SEA': '26', 'SF': '25', 'TB': '27',
    'TEN': '10', 'WSH': '28'
}


@dataclass
class TeamContext:
    """Context information for a team."""
    team_id: str
    name: str
    abbreviation: str
    record: str = ""
    division_rank: int = 0
    
    # Season stats
    ppg: float = 0.0
    ppg_allowed: float = 0.0
    rush_ypg: float = 0.0
    pass_ypg: float = 0.0
    
    # Key players
    key_players: List[Dict[str, Any]] = field(default_factory=list)
    
    # Injuries
    injuries: List[Dict[str, Any]] = field(default_factory=list)
    
    # Recent form (last 5 games)
    recent_results: List[str] = field(default_factory=list)
    
    # Historical data
    all_time_record: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'team_id': self.team_id,
            'name': self.name,
            'abbreviation': self.abbreviation,
            'record': self.record,
            'division_rank': self.division_rank,
            'ppg': self.ppg,
            'ppg_allowed': self.ppg_allowed,
            'rush_ypg': self.rush_ypg,
            'pass_ypg': self.pass_ypg,
            'key_players': self.key_players,
            'injuries': self.injuries,
            'recent_results': self.recent_results,
        }


@dataclass
class MatchupContext:
    """Full context for a game matchup."""
    home_team: TeamContext
    away_team: TeamContext
    
    # Head-to-head history
    h2h_record: str = ""  # e.g., "TB leads 5-3"
    last_meeting: str = ""  # e.g., "TB 28-13 W (Week 14, 2023)"
    
    # Pre-game analysis
    win_probability_home: float = 50.0
    win_probability_away: float = 50.0
    spread: str = ""  # Interpreted, not raw odds
    over_under_context: str = ""  # e.g., "Expected high-scoring affair"
    
    # News and articles
    articles: List[Dict[str, Any]] = field(default_factory=list)
    
    # Generated summary
    summary: str = ""
    key_storylines: List[str] = field(default_factory=list)
    
    loaded_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'home_team': self.home_team.to_dict(),
            'away_team': self.away_team.to_dict(),
            'h2h_record': self.h2h_record,
            'last_meeting': self.last_meeting,
            'win_probability': {
                'home': self.win_probability_home,
                'away': self.win_probability_away
            },
            'spread_context': self.spread,
            'over_under_context': self.over_under_context,
            'articles': self.articles,
            'summary': self.summary,
            'key_storylines': self.key_storylines,
            'loaded_at': self.loaded_at.isoformat()
        }


class GameContextLoader:
    """Loads and manages game context from multiple sources."""
    
    def __init__(self):
        self.current_context: Optional[MatchupContext] = None
        self._api_sports_teams: Dict[str, int] = {}
        self._session = requests.Session()
        self._session.verify = False  # Skip SSL verification for some APIs
    
    def load_matchup(self, home_espn_id: str, away_espn_id: str, 
                     game_id: Optional[str] = None) -> MatchupContext:
        """
        Load full context for a matchup.
        
        Args:
            home_espn_id: ESPN team ID for home team
            away_espn_id: ESPN team ID for away team
            game_id: Optional ESPN game ID for game-specific data
        """
        logger.info(f"Loading matchup context: {away_espn_id} @ {home_espn_id}")
        
        # Load team contexts
        home_team = self._load_team_context(home_espn_id)
        away_team = self._load_team_context(away_espn_id)
        
        context = MatchupContext(
            home_team=home_team,
            away_team=away_team
        )
        
        # Load head-to-head history from API-Sports
        self._load_h2h_history(context)
        
        # Load game-specific data if we have game_id
        if game_id:
            self._load_game_data(context, game_id)
        
        # Load news articles
        self._load_articles(context)
        
        # Generate summary
        context.summary = self._generate_matchup_summary(context)
        context.key_storylines = self._identify_storylines(context)
        
        self.current_context = context
        logger.info(f"Matchup context loaded: {context.summary[:100]}...")
        
        return context
    
    def _load_team_context(self, espn_team_id: str) -> TeamContext:
        """Load context for a single team from ESPN."""
        context = TeamContext(
            team_id=espn_team_id,
            name="Unknown",
            abbreviation="UNK"
        )
        
        try:
            # Fetch team info with record
            url = f"{ESPN_API_BASE}/teams/{espn_team_id}?enable=roster,record"
            resp = self._session.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json().get('team', {})
                context.name = data.get('displayName', 'Unknown')
                context.abbreviation = data.get('abbreviation', 'UNK')
                
                # Parse record
                record_items = data.get('record', {}).get('items', [])
                for item in record_items:
                    if item.get('type') == 'total':
                        context.record = item.get('summary', '')
                        for stat in item.get('stats', []):
                            if stat.get('name') == 'avgPointsFor':
                                try:
                                    context.ppg = float(stat.get('value', 0))
                                except (ValueError, TypeError):
                                    context.ppg = 0.0
                            if stat.get('name') == 'avgPointsAgainst':
                                try:
                                    context.ppg_allowed = float(stat.get('value', 0))
                                except (ValueError, TypeError):
                                    context.ppg_allowed = 0.0
            
            # Fetch team statistics
            stats_url = f"{ESPN_API_BASE}/teams/{espn_team_id}/statistics"
            resp = self._session.get(stats_url, timeout=10)
            if resp.status_code == 200:
                stats_data = resp.json().get('results', {}).get('stats', {})
                categories = stats_data.get('categories', [])
                
                for cat in categories:
                    cat_name = cat.get('name', '')
                    for stat in cat.get('stats', []):
                        stat_name = stat.get('name', '')
                        value = stat.get('perGameValue', stat.get('value', 0))
                        
                        if cat_name == 'passing' and stat_name == 'passingYardsPerGame':
                            try:
                                context.pass_ypg = float(value) if value else 0.0
                            except (ValueError, TypeError):
                                context.pass_ypg = 0.0
                        elif cat_name == 'rushing' and stat_name == 'rushingYardsPerGame':
                            try:
                                context.rush_ypg = float(value) if value else 0.0
                            except (ValueError, TypeError):
                                context.rush_ypg = 0.0
            
        except Exception as e:
            logger.error(f"Error loading team context for {espn_team_id}: {e}")
        
        # Load standings from API-Sports for division rank
        self._load_team_standings(context)
        
        return context
    
    def _load_team_standings(self, context: TeamContext):
        """Load team standings/rank from API-Sports."""
        api_sports_id = ESPN_TO_API_SPORTS_TEAM.get(context.team_id)
        if not api_sports_id:
            return
        
        try:
            url = f"{API_SPORTS_BASE}/standings?league=1&season=2024"
            resp = self._session.get(
                url, 
                headers={'x-apisports-key': API_SPORTS_KEY},
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                for entry in data.get('response', []):
                    team = entry.get('team', {})
                    if team.get('id') == api_sports_id:
                        context.division_rank = entry.get('position', 0)
                        wins = entry.get('won', 0)
                        losses = entry.get('lost', 0)
                        if not context.record:
                            context.record = f"{wins}-{losses}"
                        break
        except Exception as e:
            logger.debug(f"Could not load standings: {e}")
    
    def _load_h2h_history(self, context: MatchupContext):
        """Load head-to-head history from API-Sports."""
        home_api_id = ESPN_TO_API_SPORTS_TEAM.get(context.home_team.team_id)
        away_api_id = ESPN_TO_API_SPORTS_TEAM.get(context.away_team.team_id)
        
        if not home_api_id or not away_api_id:
            return
        
        try:
            url = f"{API_SPORTS_BASE}/games/h2h?h2h={home_api_id}-{away_api_id}"
            resp = self._session.get(
                url,
                headers={'x-apisports-key': API_SPORTS_KEY},
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                games = data.get('response', [])
                
                if games:
                    # Count wins
                    home_wins = 0
                    away_wins = 0
                    
                    for game in games:
                        scores = game.get('scores', {})
                        home_score = scores.get('home', {}).get('total', 0)
                        away_score = scores.get('away', {}).get('total', 0)
                        
                        teams = game.get('teams', {})
                        if teams.get('home', {}).get('id') == home_api_id:
                            if home_score > away_score:
                                home_wins += 1
                            else:
                                away_wins += 1
                        else:
                            if away_score > home_score:
                                home_wins += 1
                            else:
                                away_wins += 1
                    
                    # Set H2H record
                    if home_wins > away_wins:
                        context.h2h_record = f"{context.home_team.abbreviation} leads series {home_wins}-{away_wins}"
                    elif away_wins > home_wins:
                        context.h2h_record = f"{context.away_team.abbreviation} leads series {away_wins}-{home_wins}"
                    else:
                        context.h2h_record = f"Series tied {home_wins}-{away_wins}"
                    
                    # Last meeting
                    if games:
                        last = games[0]
                        last_date = last.get('game', {}).get('date', {}).get('date', '')
                        last_scores = last.get('scores', {})
                        h = last_scores.get('home', {}).get('total', 0)
                        a = last_scores.get('away', {}).get('total', 0)
                        context.last_meeting = f"Last meeting: {a}-{h} on {last_date}"
                        
        except Exception as e:
            logger.debug(f"Could not load H2H: {e}")
    
    def _load_game_data(self, context: MatchupContext, game_id: str):
        """Load game-specific data from ESPN game summary."""
        try:
            url = f"{ESPN_API_BASE}/summary?event={game_id}"
            resp = self._session.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                
                # Win probability (translate from predictor/odds)
                predictor = data.get('predictor', {})
                if predictor:
                    home_proj = predictor.get('homeTeam', {}).get('gameProjection', 50)
                    away_proj = predictor.get('awayTeam', {}).get('gameProjection', 50)
                    # Ensure these are floats for comparison
                    try:
                        context.win_probability_home = float(home_proj) if home_proj else 50.0
                        context.win_probability_away = float(away_proj) if away_proj else 50.0
                    except (ValueError, TypeError):
                        context.win_probability_home = 50.0
                        context.win_probability_away = 50.0
                
                # Interpret odds (without showing betting language)
                odds = data.get('odds', [])
                if odds:
                    odd = odds[0]
                    spread = odd.get('spread', 0)
                    over_under = odd.get('overUnder', 0)
                    
                    # Interpret spread as expected margin
                    if spread and spread != 0:
                        fav = context.home_team.abbreviation if spread < 0 else context.away_team.abbreviation
                        margin = abs(spread)
                        context.spread = f"{fav} expected to win by ~{margin:.0f} points"
                    
                    # Interpret over/under as scoring expectation
                    if over_under:
                        if over_under >= 50:
                            context.over_under_context = f"High-scoring game expected (~{over_under:.0f} combined points)"
                        elif over_under <= 40:
                            context.over_under_context = f"Defensive battle expected (~{over_under:.0f} combined points)"
                        else:
                            context.over_under_context = f"Moderate scoring expected (~{over_under:.0f} combined points)"
                
                # Load injuries from game summary
                injuries = data.get('injuries', [])
                for inj in injuries:
                    team_abbr = inj.get('team', {}).get('abbreviation', '')
                    for player_inj in inj.get('injuries', []):
                        injury_entry = {
                            'player': player_inj.get('athlete', {}).get('displayName', '?'),
                            'status': player_inj.get('status', '?'),
                            'type': player_inj.get('type', {}).get('description', '')
                        }
                        if team_abbr == context.home_team.abbreviation:
                            context.home_team.injuries.append(injury_entry)
                        elif team_abbr == context.away_team.abbreviation:
                            context.away_team.injuries.append(injury_entry)
                
        except Exception as e:
            logger.error(f"Error loading game data: {e}")
    
    def _load_articles(self, context: MatchupContext):
        """Load relevant news articles from ESPN."""
        try:
            # General NFL news
            url = f"{ESPN_API_BASE}/news"
            resp = self._session.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                articles = data.get('articles', [])
                
                # Filter for relevant articles (mention either team)
                home_name = context.home_team.name.lower()
                away_name = context.away_team.name.lower()
                home_abbr = context.home_team.abbreviation.lower()
                away_abbr = context.away_team.abbreviation.lower()
                
                for art in articles:
                    headline = art.get('headline', '').lower()
                    desc = art.get('description', '').lower()
                    
                    # Check if article mentions either team
                    relevant = any(term in headline or term in desc 
                                   for term in [home_name, away_name, home_abbr, away_abbr])
                    
                    if relevant:
                        context.articles.append({
                            'headline': art.get('headline', ''),
                            'description': art.get('description', '')[:200],
                            'url': art.get('links', {}).get('web', {}).get('href', ''),
                            'published': art.get('published', '')
                        })
                
                # Also include top stories even if not team-specific
                for art in articles[:3]:
                    if art not in context.articles:
                        context.articles.append({
                            'headline': art.get('headline', ''),
                            'description': art.get('description', '')[:200],
                            'url': art.get('links', {}).get('web', {}).get('href', ''),
                            'published': art.get('published', ''),
                            'is_general': True
                        })
                        
        except Exception as e:
            logger.debug(f"Could not load articles: {e}")
    
    def _generate_matchup_summary(self, context: MatchupContext) -> str:
        """Generate a text summary of the matchup."""
        parts = []
        
        # Basic matchup
        parts.append(f"{context.away_team.abbreviation} ({context.away_team.record}) @ "
                     f"{context.home_team.abbreviation} ({context.home_team.record})")
        
        # Division context
        if context.home_team.division_rank or context.away_team.division_rank:
            parts.append(f"Division standings: {context.home_team.abbreviation} #{context.home_team.division_rank}, "
                        f"{context.away_team.abbreviation} #{context.away_team.division_rank}")
        
        # H2H history
        if context.h2h_record:
            parts.append(context.h2h_record)
        
        # Win probability
        if context.win_probability_home != 50:
            fav = context.home_team.abbreviation if context.win_probability_home > 50 else context.away_team.abbreviation
            prob = max(context.win_probability_home, context.win_probability_away)
            parts.append(f"{fav} favored ({prob:.0f}% win probability)")
        
        # Scoring context
        if context.over_under_context:
            parts.append(context.over_under_context)
        
        return ". ".join(parts) + "." if parts else "No context available."
    
    def _identify_storylines(self, context: MatchupContext) -> List[str]:
        """Identify key storylines for the matchup."""
        storylines = []
        
        home = context.home_team
        away = context.away_team
        
        # Playoff implications
        # (would need more data to determine this properly)
        
        # Offensive matchups
        if home.ppg > 25 and away.ppg > 25:
            storylines.append("Offensive shootout potential - both teams averaging 25+ PPG")
        
        if home.rush_ypg > 130:
            storylines.append(f"{home.abbreviation}'s strong run game ({home.rush_ypg:.0f} rush YPG)")
        
        if away.pass_ypg > 250:
            storylines.append(f"{away.abbreviation}'s potent passing attack ({away.pass_ypg:.0f} pass YPG)")
        
        # Recent form (would need API-Sports recent games)
        
        # Injury impact
        key_injuries_home = [i for i in home.injuries if i.get('status') == 'Out']
        key_injuries_away = [i for i in away.injuries if i.get('status') == 'Out']
        
        if key_injuries_home:
            storylines.append(f"{home.abbreviation} missing key players: {', '.join([i['player'] for i in key_injuries_home[:2]])}")
        
        if key_injuries_away:
            storylines.append(f"{away.abbreviation} missing key players: {', '.join([i['player'] for i in key_injuries_away[:2]])}")
        
        return storylines
    
    def get_break_content(self, break_type: str, duration: int) -> Dict[str, Any]:
        """
        Get content appropriate for a break of given type and duration.
        
        Args:
            break_type: Type of break (halftime, tv_timeout, etc.)
            duration: Expected duration in seconds
        
        Returns:
            Dict with articles, stats, and analysis for the break
        """
        if not self.current_context:
            return {'content': [], 'stats': {}}
        
        ctx = self.current_context
        content = {
            'articles': [],
            'stats': {},
            'analysis_points': [],
            'shareable_links': []
        }
        
        # Short breaks (< 90s): Just key stats
        if duration < 90:
            content['stats'] = {
                'home_ppg': ctx.home_team.ppg,
                'away_ppg': ctx.away_team.ppg,
                'h2h': ctx.h2h_record
            }
            content['analysis_points'] = ctx.key_storylines[:2]
        
        # Medium breaks (90-180s): Stats + 1 article
        elif duration < 180:
            content['stats'] = {
                'home': ctx.home_team.to_dict(),
                'away': ctx.away_team.to_dict(),
                'h2h': ctx.h2h_record,
                'win_prob': f"{ctx.home_team.abbreviation} {ctx.win_probability_home:.0f}%"
            }
            content['analysis_points'] = ctx.key_storylines[:3]
            
            if ctx.articles:
                content['articles'] = ctx.articles[:1]
                content['shareable_links'] = [
                    {'headline': a['headline'], 'url': a.get('url', '')} 
                    for a in ctx.articles[:1] if a.get('url')
                ]
        
        # Long breaks (halftime, 180s+): Full content
        else:
            content['stats'] = {
                'home': ctx.home_team.to_dict(),
                'away': ctx.away_team.to_dict(),
                'h2h': ctx.h2h_record,
                'last_meeting': ctx.last_meeting,
                'win_prob': {
                    'home': ctx.win_probability_home,
                    'away': ctx.win_probability_away
                },
                'spread_context': ctx.spread,
                'scoring_context': ctx.over_under_context
            }
            content['analysis_points'] = ctx.key_storylines
            content['articles'] = ctx.articles[:5]
            content['shareable_links'] = [
                {'headline': a['headline'], 'url': a.get('url', '')} 
                for a in ctx.articles[:5] if a.get('url')
            ]
        
        return content
    
    def get_llm_context_prompt(self) -> str:
        """
        Generate a context prompt for LLM insight generation.
        
        Returns a formatted string with all relevant context for the LLM.
        """
        if not self.current_context:
            return "No game context loaded."
        
        ctx = self.current_context
        
        prompt = f"""GAME CONTEXT:

MATCHUP: {ctx.away_team.name} ({ctx.away_team.record}) @ {ctx.home_team.name} ({ctx.home_team.record})

TEAM PROFILES:
- {ctx.home_team.abbreviation}: {ctx.home_team.ppg:.1f} PPG, {ctx.home_team.ppg_allowed:.1f} allowed, {ctx.home_team.rush_ypg:.0f} rush YPG, {ctx.home_team.pass_ypg:.0f} pass YPG
- {ctx.away_team.abbreviation}: {ctx.away_team.ppg:.1f} PPG, {ctx.away_team.ppg_allowed:.1f} allowed, {ctx.away_team.rush_ypg:.0f} rush YPG, {ctx.away_team.pass_ypg:.0f} pass YPG

HISTORICAL: {ctx.h2h_record}. {ctx.last_meeting}

PRE-GAME OUTLOOK:
- Win probability: {ctx.home_team.abbreviation} {ctx.win_probability_home:.0f}%, {ctx.away_team.abbreviation} {ctx.win_probability_away:.0f}%
- {ctx.spread}
- {ctx.over_under_context}

KEY STORYLINES:
{chr(10).join('- ' + s for s in ctx.key_storylines)}

INJURIES:
- {ctx.home_team.abbreviation}: {', '.join([i['player'] + ' (' + i['status'] + ')' for i in ctx.home_team.injuries[:3]]) or 'None significant'}
- {ctx.away_team.abbreviation}: {', '.join([i['player'] + ' (' + i['status'] + ')' for i in ctx.away_team.injuries[:3]]) or 'None significant'}
"""
        return prompt
    
    def generate_pregame_insights(self) -> List[Dict[str, Any]]:
        """
        Generate a series of pre-game insights for display before kickoff.
        
        Returns a list of insight dictionaries in order of delivery with rich,
        narrative-style commentary about the teams and matchup.
        """
        if not self.current_context:
            return []
        
        ctx = self.current_context
        insights = []
        home = ctx.home_team
        away = ctx.away_team
        
        # 1. Welcome/Matchup Overview with context (immediate)
        welcome_body = f"Welcome to today's matchup! The {away.name} ({away.record}) travel to face the {home.name} ({home.record})."
        
        # Add scoring context
        if home.ppg > 25 and away.ppg > 25:
            welcome_body += f" Both teams bring explosive offenses averaging 25+ PPG – expect fireworks!"
        elif home.ppg < 18 and away.ppg < 18:
            welcome_body += f" This could be a defensive battle with both teams struggling to score."
        
        insights.append({
            'type': 'pregame_welcome',
            'priority': 10,
            'headline': f"🏈 {away.abbreviation} @ {home.abbreviation}",
            'body': welcome_body,
            'delay': 0
        })
        
        # 2. Offensive Analysis (after 3 seconds)
        offense_lines = []
        if home.ppg > 0:
            offense_lines.append(f"The {home.name} are averaging {home.ppg:.1f} points per game")
            if home.ppg_allowed > 0:
                if home.ppg > home.ppg_allowed + 5:
                    offense_lines.append(f"and their offense is outpacing their defense by {home.ppg - home.ppg_allowed:.1f} PPG.")
                elif home.ppg_allowed > home.ppg + 5:
                    offense_lines.append(f"though they're giving up {home.ppg_allowed:.1f} – defense has been a concern.")
        
        if away.ppg > 0:
            offense_lines.append(f"Meanwhile, {away.abbreviation} puts up {away.ppg:.1f} PPG")
            if away.rush_ypg > 130:
                offense_lines.append(f"with a dominant ground game ({away.rush_ypg:.0f} rush YPG).")
            elif away.pass_ypg > 250:
                offense_lines.append(f"largely through the air ({away.pass_ypg:.0f} pass YPG).")
        
        if offense_lines:
            insights.append({
                'type': 'pregame_offense',
                'priority': 9,
                'headline': '🔥 Offensive Preview',
                'body': ' '.join(offense_lines),
                'delay': 3
            })
        
        # 3. Win Probability / Game Outlook (after 6 seconds)
        if ctx.win_probability_home != 50.0:
            fav = home.abbreviation if ctx.win_probability_home > 50 else away.abbreviation
            fav_name = home.name if ctx.win_probability_home > 50 else away.name
            fav_prob = max(ctx.win_probability_home, ctx.win_probability_away)
            
            outlook_body = f"The {fav_name} come in as slight favorites ({fav_prob:.0f}% win probability)."
            if ctx.spread:
                outlook_body += f" {ctx.spread}."
            if ctx.over_under_context:
                outlook_body += f" {ctx.over_under_context}."
            
            insights.append({
                'type': 'pregame_outlook',
                'priority': 8,
                'headline': '📊 Game Outlook',
                'body': outlook_body,
                'delay': 6
            })
        
        # 4. Head-to-Head History (after 9 seconds)
        if ctx.h2h_record:
            h2h_body = ctx.h2h_record
            if ctx.last_meeting:
                h2h_body += f" {ctx.last_meeting}"
            insights.append({
                'type': 'pregame_history',
                'priority': 7,
                'headline': '📜 Series History',
                'body': h2h_body,
                'delay': 9
            })
        
        # 5. Key Storylines with narrative (after 12 seconds)
        if ctx.key_storylines:
            storylines_body = "Key storylines to watch today:\n"
            storylines_body += '\n'.join(f"• {s}" for s in ctx.key_storylines[:4])
            insights.append({
                'type': 'pregame_storylines',
                'priority': 8,
                'headline': '🎯 What to Watch',
                'body': storylines_body,
                'delay': 12
            })
        
        # 6. Injury Report with impact context (after 15 seconds)
        home_injuries = [i for i in home.injuries if i.get('status') in ['Out', 'Doubtful']]
        away_injuries = [i for i in away.injuries if i.get('status') in ['Out', 'Doubtful']]
        
        if home_injuries or away_injuries:
            injury_body = "Players to watch on the injury report:\n"
            if home_injuries:
                names = [i['player'] for i in home_injuries[:3]]
                injury_body += f"• {home.name}: {', '.join(names)} (OUT)\n"
            if away_injuries:
                names = [i['player'] for i in away_injuries[:3]]
                injury_body += f"• {away.name}: {', '.join(names)} (OUT)"
            
            # Add impact commentary
            if len(home_injuries) >= 3 or len(away_injuries) >= 3:
                injury_body += "\nSignificant injuries could impact game flow."
            
            insights.append({
                'type': 'pregame_injuries',
                'priority': 6,
                'headline': '🏥 Injury Report',
                'body': injury_body.strip(),
                'delay': 15
            })
        
        # 7. Recent News/Article (after 18 seconds)
        # Prefer team-specific articles, fallback to general NFL news
        team_articles = [a for a in ctx.articles if not a.get('is_general')]
        if not team_articles:
            team_articles = ctx.articles  # Use any available articles
        
        if team_articles:
            art = team_articles[0]
            headline = art.get('headline', '')
            desc = art.get('description', '')
            
            # Create engaging article share
            article_body = desc[:180] if desc else headline
            if art.get('url'):
                article_body += f"\n\n🔗 Read more: {art['url']}"
            
            insights.append({
                'type': 'pregame_news',
                'priority': 5,
                'headline': f"📰 {headline[:50]}{'...' if len(headline) > 50 else ''}",
                'body': article_body,
                'delay': 18
            })
        
        # 8. Kickoff countdown (after 21 seconds)
        insights.append({
            'type': 'pregame_ready',
            'priority': 9,
            'headline': '⏰ Almost Kickoff!',
            'body': f"Get ready for {ctx.away_team.abbreviation} @ {ctx.home_team.abbreviation}. Insights will continue throughout the game.",
            'delay': 21
        })
        
        return insights


# Global instance for easy access
game_context_loader = GameContextLoader()


def load_game_context(home_id: str, away_id: str, game_id: str = None) -> MatchupContext:
    """Convenience function to load game context."""
    return game_context_loader.load_matchup(home_id, away_id, game_id)


def get_break_content(break_type: str, duration: int) -> Dict[str, Any]:
    """Convenience function to get break content."""
    return game_context_loader.get_break_content(break_type, duration)


def get_llm_context() -> str:
    """Convenience function to get LLM context prompt."""
    return game_context_loader.get_llm_context_prompt()


def generate_pregame_insights() -> List[Dict[str, Any]]:
    """Convenience function to generate pre-game insight sequence."""
    return game_context_loader.generate_pregame_insights()


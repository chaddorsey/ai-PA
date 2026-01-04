"""
NFL Pro Insight Retrieval Service

Manages the retrieval and surfacing of pre-processed NFL Pro insights
during a game. Integrates with the insight engine.

Key responsibilities:
1. Load and index insights at game start
2. Match insights to game events (player plays, situations)
3. Surface appropriate insights during breaks
4. Provide LLM context for insight synthesis
5. Track usage to avoid repetition

Usage:
    service = InsightRetrievalService()
    service.load_game_insights(game_uuid, home_team, away_team)
    
    # When a player makes a play
    insights = service.get_player_triggered_insights("Patrick Mahomes", "KC")
    
    # During a break
    insights = service.get_break_insights(quarter=2, break_type="halftime")
    
    # For LLM context
    context = service.get_llm_context(player="Travis Kelce", situation="red_zone")
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

from models.insight_schema import (
    NFLProInsight,
    InsightIndex,
    InsightCategory,
    InsightTiming,
)
from insight_parser import InsightParser

logger = logging.getLogger(__name__)

DATA_PATH = Path(os.environ.get('DATA_PATH', '../data'))
INSIGHTS_CACHE_PATH = DATA_PATH / 'insights_cache'


class InsightRetrievalService:
    """
    Manages insight retrieval during a live game.
    """
    
    # Configuration
    MAX_INSIGHTS_PER_BREAK = 5
    MAX_INSIGHTS_PER_TRIGGER = 2
    COOLDOWN_QUARTERS = 2  # Don't reuse insight for N quarters
    
    def __init__(self):
        self.index: Optional[InsightIndex] = None
        self.current_game_id: Optional[str] = None
        self.home_team: str = ""
        self.away_team: str = ""
        
        # Track what we've shown
        self.used_insight_ids: set = set()
        self.quarter_usage: Dict[int, List[str]] = {}  # quarter -> insight_ids used
        
        # Recent context for coherence
        self.recent_themes: List[str] = []  # Last few topics discussed
        
        # Ensure cache directory exists
        INSIGHTS_CACHE_PATH.mkdir(parents=True, exist_ok=True)
    
    def load_game_insights(
        self,
        game_uuid: str,
        home_team: str,
        away_team: str,
        raw_insights: List[Dict] = None
    ) -> int:
        """
        Load and index insights for a game.
        
        Args:
            game_uuid: NFL Pro game UUID
            home_team: Home team abbreviation
            away_team: Away team abbreviation
            raw_insights: Optional pre-fetched insights data
        
        Returns:
            Number of insights indexed
        """
        self.current_game_id = game_uuid
        self.home_team = home_team.upper()
        self.away_team = away_team.upper()
        self.used_insight_ids = set()
        self.quarter_usage = {}
        self.recent_themes = []
        
        # Check for cached insights
        cache_file = INSIGHTS_CACHE_PATH / f"{game_uuid}_insights.json"
        
        if cache_file.exists() and not raw_insights:
            logger.info(f"Loading cached insights from {cache_file}")
            self.index = InsightIndex.from_json(cache_file.read_text())
        elif raw_insights:
            # Parse and index
            parser = InsightParser()
            self.index = parser.parse_batch(raw_insights)
            
            # Cache for future use
            cache_file.write_text(self.index.to_json())
            logger.info(f"Cached {len(self.index.all_insights)} insights")
        else:
            # Empty index
            self.index = InsightIndex()
            logger.warning("No insights loaded for game")
        
        # Log summary
        team_count = len(self.index.by_team.get(self.home_team, []))
        team_count += len(self.index.by_team.get(self.away_team, []))
        logger.info(
            f"Loaded {len(self.index.all_insights)} insights "
            f"({team_count} for {self.away_team} @ {self.home_team})"
        )
        
        return len(self.index.all_insights)
    
    def get_player_triggered_insights(
        self,
        player_name: str,
        team: str = None,
        play_type: str = None,
        yards: int = 0,
        quarter: int = 1
    ) -> List[Dict[str, str]]:
        """
        Get insights triggered by a player's action.
        
        Called when a player makes a notable play.
        
        Returns list of insight dicts with 'headline', 'body', 'priority'.
        """
        if not self.index:
            return []
        
        results = []
        
        # Find player insights
        player_insights = self.index.get_for_player(player_name)
        
        # Filter to unused or cooled-down
        available = self._filter_available(player_insights, quarter)
        
        # Prioritize by significance and relevance
        for insight in available[:self.MAX_INSIGHTS_PER_TRIGGER]:
            # Check if it fits current context
            if not self._is_contextually_appropriate(insight, play_type, yards):
                continue
            
            # Mark as used
            self._mark_used(insight.id, quarter)
            
            # Format for presentation
            results.append({
                'headline': insight.title,
                'body': insight.primary_text,
                'priority': insight.significance,
                'source': 'nfl_pro',
                'insight_id': insight.id,
            })
        
        return results
    
    def get_situation_insights(
        self,
        situation: str,
        team: str = None,
        quarter: int = 1
    ) -> List[Dict[str, str]]:
        """
        Get insights relevant to a game situation.
        
        Situations: 'red_zone', '3rd_down', 'goal_line', 'two_minute', etc.
        """
        if not self.index:
            return []
        
        results = []
        
        # Get situation-specific insights
        situation_insights = self.index.get_for_situation(situation, team)
        available = self._filter_available(situation_insights, quarter)
        
        for insight in available[:self.MAX_INSIGHTS_PER_TRIGGER]:
            self._mark_used(insight.id, quarter)
            
            results.append({
                'headline': insight.title,
                'body': insight.primary_text,
                'priority': insight.significance,
                'source': 'nfl_pro',
                'insight_id': insight.id,
                'situation': situation,
            })
        
        return results
    
    def get_break_insights(
        self,
        quarter: int,
        break_type: str = "commercial",
        duration_seconds: int = 120
    ) -> List[Dict[str, str]]:
        """
        Get insights appropriate for a break period.
        
        Args:
            quarter: Current quarter
            break_type: 'commercial', 'timeout', 'halftime', 'quarter_break'
            duration_seconds: Estimated break duration
        
        Returns insights sized for the break duration.
        """
        if not self.index:
            return []
        
        results = []
        
        # Get break-appropriate insights
        break_insights = self.index.get_for_break(
            quarter,
            teams=[self.home_team, self.away_team]
        )
        available = self._filter_available(break_insights, quarter)
        
        # Calculate how many insights we can fit
        if break_type == 'halftime':
            # Halftime: more, deeper insights
            max_insights = 5
            use_secondary = True
        elif break_type == 'timeout':
            # Short timeout: just one quick insight
            max_insights = 1
            use_secondary = False
        else:
            # Commercial: 1-2 insights
            max_insights = min(duration_seconds // 60, 3)
            use_secondary = duration_seconds >= 90
        
        for insight in available[:max_insights]:
            self._mark_used(insight.id, quarter)
            
            # Use appropriate text depth
            if use_secondary and insight.secondary_text:
                body = f"{insight.primary_text}\n\n{insight.secondary_text}"
            else:
                body = insight.primary_text
            
            results.append({
                'headline': insight.title,
                'body': body,
                'priority': insight.significance,
                'source': 'nfl_pro',
                'insight_id': insight.id,
                'break_type': break_type,
                'is_extended': use_secondary,
            })
        
        return results
    
    def get_matchup_insights(self, quarter: int = 1) -> List[Dict[str, str]]:
        """
        Get head-to-head matchup insights.
        
        Best for pregame or halftime.
        """
        if not self.index:
            return []
        
        results = []
        
        matchup_insights = self.index.get_matchup_insights(
            self.home_team,
            self.away_team
        )
        available = self._filter_available(matchup_insights, quarter)
        
        for insight in available[:3]:
            self._mark_used(insight.id, quarter)
            
            results.append({
                'headline': insight.title,
                'body': insight.primary_text,
                'priority': insight.significance + 1,  # Boost matchup priority
                'source': 'nfl_pro',
                'insight_id': insight.id,
                'is_matchup': True,
            })
        
        return results
    
    def get_llm_context(
        self,
        player: str = None,
        team: str = None,
        situation: str = None,
        max_context_length: int = 1500
    ) -> str:
        """
        Get context bundle for LLM synthesis.
        
        Provides relevant background information for the LLM
        to generate more informed insights.
        """
        if not self.index:
            return ""
        
        context = self.index.get_llm_context_bundle(
            player=player,
            team=team,
            situation=situation,
            max_insights=5
        )
        
        # Truncate if needed
        if len(context) > max_context_length:
            context = context[:max_context_length] + "..."
        
        return context
    
    def get_facts_for_template(
        self,
        player: str = None,
        team: str = None
    ) -> Dict[str, Any]:
        """
        Get extracted facts for template variable substitution.
        
        Returns a dict of variable_name -> value that can be
        used in insight templates.
        """
        if not self.index:
            return {}
        
        variables = {}
        
        # Get relevant insights
        if player:
            insights = self.index.get_for_player(player)[:3]
        elif team:
            insights = self.index.get_for_team(team)[:3]
        else:
            return {}
        
        # Extract facts
        for insight in insights:
            for fact in insight.facts:
                var_dict = fact.to_template_var()
                variables.update(var_dict)
        
        return variables
    
    def get_pregame_sequence(
        self,
        num_insights: int = 5
    ) -> List[Dict[str, str]]:
        """
        Get a sequence of insights for pregame presentation.
        
        Orders insights for a compelling pregame narrative:
        1. Matchup overview
        2. Key player spotlights
        3. Statistical context
        4. Historical notes
        """
        if not self.index:
            return []
        
        sequence = []
        
        # 1. Matchup insights first
        matchups = self.get_matchup_insights(quarter=0)
        sequence.extend(matchups[:2])
        
        # 2. Key player spotlights
        for team in [self.away_team, self.home_team]:
            team_insights = self.index.get_for_team(team)
            for insight in team_insights[:1]:
                if insight.id not in self.used_insight_ids:
                    self._mark_used(insight.id, 0)
                    sequence.append({
                        'headline': insight.title,
                        'body': insight.primary_text,
                        'priority': insight.significance,
                        'source': 'nfl_pro',
                        'insight_id': insight.id,
                    })
        
        # 3. Fill with highest significance unused
        remaining = num_insights - len(sequence)
        if remaining > 0:
            all_unused = [
                i for i in self.index.all_insights
                if i.id not in self.used_insight_ids
            ]
            all_unused.sort(key=lambda i: -i.significance)
            
            for insight in all_unused[:remaining]:
                self._mark_used(insight.id, 0)
                sequence.append({
                    'headline': insight.title,
                    'body': insight.primary_text,
                    'priority': insight.significance,
                    'source': 'nfl_pro',
                    'insight_id': insight.id,
                })
        
        return sequence[:num_insights]
    
    def _filter_available(
        self,
        insights: List[NFLProInsight],
        current_quarter: int
    ) -> List[NFLProInsight]:
        """Filter to insights that are available (unused or cooled down)."""
        available = []
        
        for insight in insights:
            # Never used
            if insight.id not in self.used_insight_ids:
                available.append(insight)
                continue
            
            # Check cooldown
            if insight.last_used_quarter is not None:
                quarters_since = current_quarter - insight.last_used_quarter
                if quarters_since >= self.COOLDOWN_QUARTERS:
                    available.append(insight)
        
        return available
    
    def _is_contextually_appropriate(
        self,
        insight: NFLProInsight,
        play_type: str = None,
        yards: int = 0
    ) -> bool:
        """Check if insight fits the current play context."""
        # For now, most insights are appropriate
        # Could add logic like:
        # - Don't show rushing insight on a pass play
        # - Don't show negative stats after a big play
        return True
    
    def _mark_used(self, insight_id: str, quarter: int):
        """Mark an insight as used."""
        self.used_insight_ids.add(insight_id)
        
        if quarter not in self.quarter_usage:
            self.quarter_usage[quarter] = []
        self.quarter_usage[quarter].append(insight_id)
        
        # Update the insight object
        self.index.mark_used(insight_id, quarter)
    
    def get_usage_stats(self) -> Dict[str, Any]:
        """Get statistics about insight usage."""
        return {
            'total_insights': len(self.index.all_insights) if self.index else 0,
            'used_count': len(self.used_insight_ids),
            'by_quarter': {q: len(ids) for q, ids in self.quarter_usage.items()},
            'remaining_high_priority': len([
                i for i in (self.index.all_insights if self.index else [])
                if i.id not in self.used_insight_ids and i.significance >= 7
            ]),
        }


# Singleton for use by insight engine
_retrieval_service: Optional[InsightRetrievalService] = None


def get_retrieval_service() -> InsightRetrievalService:
    """Get or create the singleton retrieval service."""
    global _retrieval_service
    if _retrieval_service is None:
        _retrieval_service = InsightRetrievalService()
    return _retrieval_service


# Flask endpoints for external integration
from flask import Flask, jsonify, request

app = Flask(__name__)


@app.route('/health')
def health():
    service = get_retrieval_service()
    return jsonify({
        'status': 'healthy',
        'game_loaded': service.current_game_id is not None,
        'insights_count': len(service.index.all_insights) if service.index else 0,
    })


@app.route('/load', methods=['POST'])
def load_insights():
    data = request.get_json() or {}
    game_uuid = data.get('game_uuid')
    home_team = data.get('home_team')
    away_team = data.get('away_team')
    raw_insights = data.get('insights', [])
    
    if not game_uuid or not home_team or not away_team:
        return jsonify({'status': 'error', 'message': 'Missing required fields'}), 400
    
    service = get_retrieval_service()
    count = service.load_game_insights(game_uuid, home_team, away_team, raw_insights)
    
    return jsonify({
        'status': 'ok',
        'insights_loaded': count,
        'teams': [home_team, away_team],
    })


@app.route('/player/<player_name>')
def get_player_insights(player_name: str):
    quarter = request.args.get('quarter', 1, type=int)
    
    service = get_retrieval_service()
    insights = service.get_player_triggered_insights(player_name, quarter=quarter)
    
    return jsonify({
        'status': 'ok',
        'player': player_name,
        'insights': insights,
    })


@app.route('/situation/<situation>')
def get_situation_insights_api(situation: str):
    quarter = request.args.get('quarter', 1, type=int)
    team = request.args.get('team')
    
    service = get_retrieval_service()
    insights = service.get_situation_insights(situation, team, quarter)
    
    return jsonify({
        'status': 'ok',
        'situation': situation,
        'insights': insights,
    })


@app.route('/break')
def get_break_insights_api():
    quarter = request.args.get('quarter', 1, type=int)
    break_type = request.args.get('type', 'commercial')
    duration = request.args.get('duration', 120, type=int)
    
    service = get_retrieval_service()
    insights = service.get_break_insights(quarter, break_type, duration)
    
    return jsonify({
        'status': 'ok',
        'break_type': break_type,
        'insights': insights,
    })


@app.route('/pregame')
def get_pregame_sequence_api():
    count = request.args.get('count', 5, type=int)
    
    service = get_retrieval_service()
    insights = service.get_pregame_sequence(count)
    
    return jsonify({
        'status': 'ok',
        'insights': insights,
    })


@app.route('/llm_context', methods=['POST'])
def get_llm_context_api():
    data = request.get_json() or {}
    
    service = get_retrieval_service()
    context = service.get_llm_context(
        player=data.get('player'),
        team=data.get('team'),
        situation=data.get('situation'),
    )
    
    return jsonify({
        'status': 'ok',
        'context': context,
    })


@app.route('/stats')
def get_stats():
    service = get_retrieval_service()
    return jsonify(service.get_usage_stats())


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Insight Retrieval Service')
    parser.add_argument('--port', type=int, default=5134, help='Port to run on')
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
    
    print(f"\n{'='*60}")
    print("NFL Pro Insight Retrieval Service")
    print(f"{'='*60}")
    print(f"Port: {args.port}")
    print("Endpoints:")
    print("  POST /load - Load game insights")
    print("  GET  /player/<name> - Get player insights")
    print("  GET  /situation/<situation> - Get situation insights")
    print("  GET  /break - Get break-time insights")
    print("  GET  /pregame - Get pregame sequence")
    print("  POST /llm_context - Get LLM context")
    print("  GET  /stats - Usage statistics")
    print(f"{'='*60}\n")
    
    app.run(host='0.0.0.0', port=args.port, debug=False)


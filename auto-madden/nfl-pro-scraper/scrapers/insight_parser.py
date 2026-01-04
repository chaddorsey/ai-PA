"""
NFL Pro Insight Parser

Parses raw NFL Pro insights and structures them for optimal retrieval.
Uses LLM for fact extraction and categorization when available.
"""

import logging
import re
import uuid
from typing import Dict, List, Optional, Any, Tuple

from models.insight_schema import (
    NFLProInsight,
    InsightEntity,
    InsightFact,
    InsightIndex,
    EntityType,
    InsightCategory,
    InsightTiming,
)
from models.terms_of_art import detect_terms_in_text, get_term, TermComplexity

logger = logging.getLogger(__name__)


# Common position abbreviations
POSITIONS = {
    'QB': 'Quarterback',
    'RB': 'Running Back',
    'WR': 'Wide Receiver',
    'TE': 'Tight End',
    'OL': 'Offensive Line',
    'DL': 'Defensive Line',
    'LB': 'Linebacker',
    'CB': 'Cornerback',
    'S': 'Safety',
    'K': 'Kicker',
    'P': 'Punter',
}

# Situation keywords for triggering
SITUATION_KEYWORDS = {
    'red zone': ['red zone', 'inside the 20', 'goal-to-go', 'goal line'],
    '3rd down': ['third down', '3rd down', 'third-down'],
    'two minute': ['two-minute', 'two minute', '2-minute'],
    'goal line': ['goal line', 'goal-line', 'inside the 5'],
    'passing': ['passing', 'through the air', 'passing game', 'pass attack'],
    'rushing': ['rushing', 'run game', 'ground game', 'running attack'],
    'defense': ['defensive', 'defense', 'pass rush', 'coverage'],
    'turnover': ['turnover', 'interception', 'fumble'],
}

# Category detection patterns
CATEGORY_PATTERNS = {
    InsightCategory.STATISTICAL: [r'\d+%', r'\d+ yard', r'ranks? \d', r'averaging'],
    InsightCategory.STREAK: [r'consecutive', r'streak', r'in a row', r'straight'],
    InsightCategory.HISTORICAL: [r'since \d{4}', r'first time', r'last season', r'history'],
    InsightCategory.MILESTONE: [r'career', r'record', r'milestone', r'all-time'],
    InsightCategory.HEAD_TO_HEAD: [r'vs\.?', r'against', r'matchup', r'face'],
    InsightCategory.INJURY_RELATED: [r'injury', r'injured', r'return', r'healthy'],
    InsightCategory.TACTICAL: [r'blitz', r'coverage', r'formation', r'scheme'],
}


class InsightParser:
    """
    Parses raw NFL Pro API insights into structured format.
    """
    
    def __init__(self, llm_client=None):
        """
        Initialize parser.
        
        Args:
            llm_client: Optional LLM client for advanced parsing
        """
        self.llm = llm_client
    
    def parse_raw_insight(self, raw: Dict[str, Any]) -> Optional[NFLProInsight]:
        """
        Parse a raw insight from the NFL Pro API.
        
        Expected raw format:
        {
            "title": "...",
            "subNote1": "Primary paragraph",
            "subNote2": "Secondary paragraph",
            "playerName": "Sam Darnold",
            "teamAbbr": "SF",
            "playerName2": "Brock Purdy",  # Optional for dual
            "teamAbbr2": "SF",  # Optional
            ...
        }
        """
        if not raw:
            return None
        
        insight_id = str(raw.get('id', uuid.uuid4()))[:12]
        title = raw.get('title', '')
        primary_text = raw.get('subNote1', '')
        secondary_text = raw.get('subNote2', '')
        
        if not primary_text:
            return None
        
        # Build entities
        entities = []
        teams = set()
        
        # Primary entity
        player1 = raw.get('playerName', '')
        team1 = raw.get('teamAbbr', '')
        if player1:
            entity1 = self._build_player_entity(player1, team1, raw.get('position1', ''))
            entities.append(entity1)
            if team1:
                teams.add(team1.upper())
        
        # Secondary entity (for dual-entity insights)
        player2 = raw.get('playerName2', '')
        team2 = raw.get('teamAbbr2', '')
        if player2:
            entity2 = self._build_player_entity(player2, team2, raw.get('position2', ''))
            entities.append(entity2)
            if team2:
                teams.add(team2.upper())
        
        # Check for team unit mentions
        team_units = self._extract_team_units(primary_text + ' ' + secondary_text)
        for unit_name, unit_team in team_units:
            entities.append(InsightEntity(
                name=unit_name,
                entity_type=EntityType.TEAM_UNIT,
                team_abbr=unit_team,
            ))
            teams.add(unit_team.upper())
        
        # Classify
        is_dual_entity = len(entities) >= 2
        is_dual_team = len(teams) >= 2
        
        # Detect categories
        categories = self._detect_categories(primary_text + ' ' + secondary_text)
        
        # Detect situation triggers
        situation_triggers = self._detect_situations(primary_text + ' ' + secondary_text)
        
        # Determine timing
        timing = self._determine_timing(categories, is_dual_team)
        
        # Extract facts
        facts = self._extract_facts(primary_text, secondary_text, entities)
        
        # Estimate significance
        significance = self._estimate_significance(
            categories, facts, is_dual_team, primary_text
        )
        
        # Extract terms of art for educational opportunities
        full_text = f"{title} {primary_text} {secondary_text}"
        extracted_terms = detect_terms_in_text(full_text)
        
        terms_of_art_data = []
        primary_term = None
        has_educational = False
        
        for ext_term in extracted_terms:
            term_data = {
                'term': ext_term.term,
                'centrality': ext_term.centrality,
                'context': ext_term.context_snippet,
                'needs_explanation': ext_term.needs_explanation,
            }
            terms_of_art_data.append(term_data)
            
            # Track primary term (most central, needs explanation)
            if ext_term.needs_explanation and not primary_term:
                primary_term = ext_term.term
                has_educational = True
        
        return NFLProInsight(
            id=insight_id,
            title=title,
            primary_text=primary_text,
            secondary_text=secondary_text,
            entities=entities,
            primary_entity=entities[0] if entities else None,
            categories=categories,
            is_dual_entity=is_dual_entity,
            is_dual_team=is_dual_team,
            timing=timing,
            situation_triggers=situation_triggers,
            facts=facts,
            teams=list(teams),
            significance=significance,
            freshness=7,  # Recent game insights
            terms_of_art=terms_of_art_data,
            primary_term=primary_term,
            has_educational_opportunity=has_educational,
        )
    
    def _build_player_entity(
        self,
        name: str,
        team: str,
        position: str = ""
    ) -> InsightEntity:
        """Build a player entity with name variants."""
        variants = []
        
        # Full name
        variants.append(name)
        
        # Last name only
        parts = name.split()
        if len(parts) > 1:
            variants.append(parts[-1])
            # First initial + last name
            variants.append(f"{parts[0][0]}. {parts[-1]}")
            variants.append(f"{parts[0][0]}.{parts[-1]}")
        
        return InsightEntity(
            name=name,
            entity_type=EntityType.PLAYER,
            team_abbr=team,
            position=position,
            name_variants=variants,
        )
    
    def _extract_team_units(self, text: str) -> List[Tuple[str, str]]:
        """Extract team unit mentions like '49ers defense'."""
        units = []
        
        # Pattern: [Team] [unit]
        # e.g., "Chiefs offense", "49ers defense"
        patterns = [
            r"(\w+(?:'s)?)\s+(offense|defense|special teams|secondary|offensive line|defensive line)",
            r"(\w+)\s+(pass rush|rushing attack|passing attack)",
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                team_name = match[0].replace("'s", "")
                unit = match[1]
                # Would need team name->abbr mapping
                # For now, just capture
                units.append((f"{team_name} {unit}", team_name[:3].upper()))
        
        return units
    
    def _detect_categories(self, text: str) -> List[InsightCategory]:
        """Detect insight categories from text patterns."""
        categories = []
        text_lower = text.lower()
        
        for category, patterns in CATEGORY_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text_lower):
                    if category not in categories:
                        categories.append(category)
                    break
        
        # Default category
        if not categories:
            categories.append(InsightCategory.PLAYER_SPOTLIGHT)
        
        return categories
    
    def _detect_situations(self, text: str) -> List[str]:
        """Detect game situations this insight is relevant to."""
        triggers = []
        text_lower = text.lower()
        
        for situation, keywords in SITUATION_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text_lower:
                    triggers.append(situation)
                    break
        
        return triggers
    
    def _determine_timing(
        self,
        categories: List[InsightCategory],
        is_matchup: bool
    ) -> InsightTiming:
        """Determine optimal timing for this insight."""
        
        # Matchup insights are great for pregame/halftime
        if is_matchup or InsightCategory.HEAD_TO_HEAD in categories:
            return InsightTiming.PREGAME
        
        # Historical/milestone insights good for breaks
        if InsightCategory.HISTORICAL in categories or InsightCategory.MILESTONE in categories:
            return InsightTiming.BREAK
        
        # Statistical insights can be used anytime
        if InsightCategory.STATISTICAL in categories:
            return InsightTiming.ANY
        
        # Tactical insights best during game
        if InsightCategory.TACTICAL in categories:
            return InsightTiming.PLAY_SPECIFIC
        
        return InsightTiming.ANY
    
    def _extract_facts(
        self,
        primary: str,
        secondary: str,
        entities: List[InsightEntity]
    ) -> List[InsightFact]:
        """Extract discrete facts from insight text."""
        facts = []
        full_text = primary + ' ' + secondary
        
        # Extract percentage stats
        pct_matches = re.findall(r'(\d+\.?\d*)%', full_text)
        for pct in pct_matches:
            # Try to find context
            context_match = re.search(
                rf'(\w+(?:\s+\w+){{0,3}})\s+{pct}%',
                full_text
            )
            context = context_match.group(1) if context_match else ""
            
            facts.append(InsightFact(
                fact_type="percentage",
                subject=entities[0].name if entities else "team",
                value=float(pct),
                context=context,
                prompt_fragment=f"{context}: {pct}%",
            ))
        
        # Extract yardage stats
        yard_matches = re.findall(r'(\d+)\s+(?:yards?|yds?)', full_text, re.IGNORECASE)
        for yards in yard_matches:
            context_match = re.search(
                rf'(\w+(?:\s+\w+){{0,2}})\s+{yards}\s+(?:yards?|yds?)',
                full_text
            )
            context = context_match.group(1) if context_match else ""
            
            facts.append(InsightFact(
                fact_type="yardage",
                subject=entities[0].name if entities else "team",
                value=int(yards),
                context=context,
                prompt_fragment=f"{yards} yards ({context})",
            ))
        
        # Extract rankings
        rank_matches = re.findall(r'ranks?\s+(\d+)', full_text, re.IGNORECASE)
        for rank in rank_matches:
            facts.append(InsightFact(
                fact_type="ranking",
                subject=entities[0].name if entities else "team",
                value=int(rank),
                context="league ranking",
                prompt_fragment=f"ranked #{rank}",
            ))
        
        return facts
    
    def _estimate_significance(
        self,
        categories: List[InsightCategory],
        facts: List[InsightFact],
        is_matchup: bool,
        primary_text: str
    ) -> int:
        """Estimate how significant/interesting this insight is."""
        score = 5  # Base
        
        # Matchups are interesting
        if is_matchup:
            score += 2
        
        # More categories = richer insight
        score += min(len(categories) - 1, 2)
        
        # More facts = more substance
        score += min(len(facts), 2)
        
        # Key phrases boost significance
        boosters = ['first time', 'record', 'career', 'best', 'worst', 'never', 'most']
        for phrase in boosters:
            if phrase in primary_text.lower():
                score += 1
                break
        
        return min(score, 10)
    
    def parse_batch(self, raw_insights: List[Dict]) -> InsightIndex:
        """
        Parse a batch of raw insights and build an index.
        """
        index = InsightIndex()
        
        for raw in raw_insights:
            try:
                insight = self.parse_raw_insight(raw)
                if insight:
                    index.add_insight(insight)
            except Exception as e:
                logger.error(f"Error parsing insight: {e}")
        
        logger.info(f"Parsed {len(index.all_insights)} insights")
        logger.info(f"  Players indexed: {len(index.by_player)}")
        logger.info(f"  Teams indexed: {len(index.by_team)}")
        logger.info(f"  Matchup insights: {len(index.matchup_insights)}")
        
        return index
    
    async def enrich_with_llm(self, insight: NFLProInsight) -> NFLProInsight:
        """
        Use LLM to extract additional structure from insight text.
        
        Extracts:
        - Additional facts not caught by regex
        - Refined categorization
        - Situation triggers
        - Optimal presentation timing
        """
        if not self.llm:
            return insight
        
        prompt = f"""Analyze this NFL insight and extract structured information:

Title: {insight.title}
Primary: {insight.primary_text}
Secondary: {insight.secondary_text}

Extract:
1. Key statistics mentioned (format: stat_name: value)
2. Relevant game situations (red zone, 3rd down, 2-minute, etc.)
3. Significance rating (1-10, where 10 is most newsworthy)
4. Best timing to present (pregame, during_play, during_break, halftime)

Respond in JSON format.
"""
        
        try:
            response = await self.llm.generate(prompt)
            # Parse and merge with existing insight
            # ... implementation depends on LLM client
        except Exception as e:
            logger.error(f"LLM enrichment failed: {e}")
        
        return insight


def load_game_insights(game_uuid: str, insights_data: List[Dict]) -> InsightIndex:
    """
    Convenience function to load and index insights for a game.
    """
    parser = InsightParser()
    return parser.parse_batch(insights_data)


# Example usage / testing
if __name__ == '__main__':
    # Example raw insight from NFL Pro API
    sample_raw = {
        'id': 'ins_001',
        'title': 'Quarterback Showdown',
        'subNote1': 'Sam Darnold has completed 68.4% of his passes this season, '
                   'ranking 5th among qualified quarterbacks.',
        'subNote2': 'Darnold has thrown for 2,456 yards and 18 touchdowns in 2024, '
                   'with only 4 interceptions. His passer rating of 105.2 is a '
                   'career high.',
        'playerName': 'Sam Darnold',
        'teamAbbr': 'SF',
        'playerName2': 'Brock Purdy',
        'teamAbbr2': 'SF',
    }
    
    parser = InsightParser()
    insight = parser.parse_raw_insight(sample_raw)
    
    if insight:
        print(f"Parsed insight: {insight.title}")
        print(f"Entities: {[e.name for e in insight.entities]}")
        print(f"Categories: {[c.value for c in insight.categories]}")
        print(f"Facts extracted: {len(insight.facts)}")
        for fact in insight.facts:
            print(f"  - {fact.fact_type}: {fact.value} ({fact.context})")
        print(f"Significance: {insight.significance}")
        print(f"Timing: {insight.timing.value}")


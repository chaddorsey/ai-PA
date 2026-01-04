"""
Mini-Lesson Generator

Generates educational content ("Did you know?") from insights containing
football terms of art. Creates lessons at different lengths for different
break types.

Break Type → Lesson Length:
- Timeout (30s): Brief definition + insight primary text
- Commercial (90s): Standard definition + context + insight full text  
- Halftime (15min): Extended definition + history + anecdotes + insight
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.terms_of_art import get_term, TermOfArt, TermComplexity, FOOTBALL_GLOSSARY
from models.insight_schema import NFLProInsight

logger = logging.getLogger(__name__)


@dataclass
class MiniLesson:
    """An educational mini-lesson paired with an insight."""
    term: str
    term_definition: str
    insight_headline: str
    insight_body: str
    
    # Different length versions
    brief_version: str = ""      # ~30 seconds reading
    standard_version: str = ""   # ~60 seconds reading
    extended_version: str = ""   # ~2-3 minutes reading
    
    # Metadata
    complexity: str = "intermediate"
    category: str = "general"
    insight_id: str = ""
    
    def get_for_break_type(self, break_type: str) -> str:
        """Get the appropriate version for a break type."""
        if break_type in ['timeout', 'team_timeout', 'injury']:
            return self.brief_version
        elif break_type in ['commercial', 'official_timeout', 'quarter_break']:
            return self.standard_version
        elif break_type in ['halftime']:
            return self.extended_version
        else:
            return self.brief_version


class MiniLessonGenerator:
    """
    Generates educational mini-lessons from insights.
    """
    
    def __init__(self, llm_client=None):
        """
        Initialize generator.
        
        Args:
            llm_client: Optional LLM client for enhanced content generation
        """
        self.llm = llm_client
        self._cache: Dict[str, MiniLesson] = {}
    
    def generate_lesson(
        self,
        insight: NFLProInsight,
        term_name: str = None
    ) -> Optional[MiniLesson]:
        """
        Generate a mini-lesson for an insight.
        
        Args:
            insight: The NFL Pro insight
            term_name: Specific term to explain (uses primary_term if not specified)
        
        Returns:
            MiniLesson object or None if no educational content available
        """
        # Determine which term to explain
        term_to_use = term_name or insight.primary_term
        if not term_to_use:
            return None
        
        # Check cache
        cache_key = f"{insight.id}_{term_to_use}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # Get term from glossary
        term_entry = get_term(term_to_use)
        if not term_entry:
            logger.debug(f"Term not in glossary: {term_to_use}")
            return None
        
        # Generate lesson content
        lesson = self._build_lesson(insight, term_entry)
        
        # Cache and return
        self._cache[cache_key] = lesson
        return lesson
    
    def _build_lesson(
        self,
        insight: NFLProInsight,
        term: TermOfArt
    ) -> MiniLesson:
        """Build a mini-lesson from insight and term."""
        
        # Brief version (timeout ~30s)
        brief = self._build_brief_version(insight, term)
        
        # Standard version (commercial ~60s)
        standard = self._build_standard_version(insight, term)
        
        # Extended version (halftime ~2-3min)
        extended = self._build_extended_version(insight, term)
        
        return MiniLesson(
            term=term.term,
            term_definition=term.definition_brief,
            insight_headline=insight.title,
            insight_body=insight.primary_text,
            brief_version=brief,
            standard_version=standard,
            extended_version=extended,
            complexity=term.complexity.value,
            category=term.category.value,
            insight_id=insight.id,
        )
    
    def _build_brief_version(self, insight: NFLProInsight, term: TermOfArt) -> str:
        """Build brief version for timeouts (~30s reading)."""
        
        # Format: Quick definition + insight primary text
        return f"""💡 **{term.term}**: {term.definition_brief}

{insight.primary_text}"""
    
    def _build_standard_version(self, insight: NFLProInsight, term: TermOfArt) -> str:
        """Build standard version for commercial breaks (~60s reading)."""
        
        # Find which entity is most relevant
        entity_name = insight.entities[0].name if insight.entities else "This player"
        
        parts = [
            f"📚 **Did You Know? {term.term}**",
            "",
            term.definition_standard or term.definition_brief,
            "",
        ]
        
        # Add "why it matters" if available
        if term.why_it_matters:
            parts.extend([
                f"*Why it matters*: {term.why_it_matters}",
                "",
            ])
        
        # Add the insight
        parts.extend([
            "---",
            "",
            f"**{insight.title}**",
            "",
            insight.primary_text,
        ])
        
        # Add secondary if short enough
        if insight.secondary_text and len(insight.secondary_text) < 200:
            parts.extend(["", insight.secondary_text])
        
        return "\n".join(parts)
    
    def _build_extended_version(self, insight: NFLProInsight, term: TermOfArt) -> str:
        """Build extended version for halftime (~2-3min reading)."""
        
        parts = [
            f"📖 **Football 101: {term.term}**",
            "",
            term.definition_extended or term.definition_standard or term.definition_brief,
            "",
        ]
        
        # When used
        if term.when_used:
            parts.extend([
                f"**When teams use it**: {term.when_used}",
                "",
            ])
        
        # Famous practitioners
        if term.famous_practitioners:
            practitioners = ", ".join(term.famous_practitioners)
            parts.extend([
                f"**Made famous by**: {practitioners}",
                "",
            ])
        
        # Why it matters
        if term.why_it_matters:
            parts.extend([
                f"**Why it matters**: {term.why_it_matters}",
                "",
            ])
        
        # Related concepts
        if term.related_terms:
            related = ", ".join(term.related_terms[:4])
            parts.extend([
                f"*Related concepts*: {related}",
                "",
            ])
        
        # The insight itself
        parts.extend([
            "---",
            "",
            f"**Today's Example: {insight.title}**",
            "",
            insight.primary_text,
            "",
        ])
        
        if insight.secondary_text:
            parts.extend([insight.secondary_text, ""])
        
        return "\n".join(parts)
    
    async def generate_with_llm(
        self,
        insight: NFLProInsight,
        term: TermOfArt,
        length: str = "standard"
    ) -> str:
        """
        Use LLM to generate a more natural, engaging mini-lesson.
        
        Falls back to template if LLM unavailable.
        """
        if not self.llm:
            lesson = self._build_lesson(insight, term)
            if length == "brief":
                return lesson.brief_version
            elif length == "extended":
                return lesson.extended_version
            else:
                return lesson.standard_version
        
        # Build LLM prompt
        prompt = self._build_llm_prompt(insight, term, length)
        
        try:
            response = await self.llm.generate(prompt)
            return response
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            # Fallback to template
            lesson = self._build_lesson(insight, term)
            return lesson.standard_version
    
    def _build_llm_prompt(
        self,
        insight: NFLProInsight,
        term: TermOfArt,
        length: str
    ) -> str:
        """Build prompt for LLM mini-lesson generation."""
        
        length_guidance = {
            "brief": "Write a brief 2-3 sentence explanation suitable for a 30-second timeout.",
            "standard": "Write a 3-4 paragraph explanation suitable for a 90-second commercial break.",
            "extended": "Write a comprehensive 5-6 paragraph explanation suitable for halftime, including historical context and examples.",
        }
        
        return f"""Generate an educational football mini-lesson for a viewer watching an NFL game.

TERM TO EXPLAIN: {term.term}
BASIC DEFINITION: {term.definition_brief}
COMPLEXITY LEVEL: {term.complexity.value}

RELATED INSIGHT: {insight.title}
INSIGHT DETAILS: {insight.primary_text}

{length_guidance.get(length, length_guidance['standard'])}

Write in an engaging, conversational tone as if explaining to a friend who's new to football. 
Connect the term explanation naturally to the specific insight about the current game.
Start with "Did you know?" or a similar engaging opener.
"""


def generate_mini_lesson_for_insight(
    insight: NFLProInsight,
    break_type: str = "commercial"
) -> Optional[str]:
    """
    Convenience function to generate a mini-lesson for an insight.
    
    Args:
        insight: The insight to generate a lesson for
        break_type: Type of break (timeout, commercial, halftime)
    
    Returns:
        Formatted mini-lesson text or None
    """
    if not insight.has_educational_opportunity:
        return None
    
    generator = MiniLessonGenerator()
    lesson = generator.generate_lesson(insight)
    
    if not lesson:
        return None
    
    return lesson.get_for_break_type(break_type)


def preprocess_insight_lessons(insights: List[NFLProInsight]) -> Dict[str, MiniLesson]:
    """
    Pre-generate mini-lessons for a batch of insights.
    
    Returns dict mapping insight_id to MiniLesson.
    """
    generator = MiniLessonGenerator()
    lessons = {}
    
    for insight in insights:
        if insight.has_educational_opportunity:
            lesson = generator.generate_lesson(insight)
            if lesson:
                lessons[insight.id] = lesson
                
                # Also store on the insight itself
                insight.mini_lesson_brief = lesson.brief_version
                insight.mini_lesson_extended = lesson.extended_version
                insight.mini_lesson_generated = True
    
    logger.info(f"Generated {len(lessons)} mini-lessons from {len(insights)} insights")
    return lessons


# Example / test
if __name__ == '__main__':
    import json
    from scrapers.insight_parser import InsightParser
    
    # Load sample insights
    with open('../nfl_pro_data_f979d7ee_20260104_000445.json', 'r') as f:
        data = json.load(f)
    
    def convert(raw):
        return {
            'id': raw.get('insight_id', ''),
            'title': raw.get('title', ''),
            'subNote1': raw.get('sub_note', ''),
            'subNote2': raw.get('sub_note2', ''),
            'playerName': raw.get('player_name', ''),
            'teamAbbr': raw.get('team_abbr', ''),
            'playerName2': raw.get('second_player_name', ''),
            'teamAbbr2': raw.get('second_team_abbr', ''),
        }
    
    parser = InsightParser()
    index = parser.parse_batch([convert(i) for i in data['insights']])
    
    print("="*60)
    print("MINI-LESSON EXAMPLES")
    print("="*60)
    
    # Find insights with educational opportunities
    educational = [i for i in index.all_insights if i.has_educational_opportunity]
    print(f"\nFound {len(educational)} insights with educational opportunities")
    
    generator = MiniLessonGenerator()
    
    for insight in educational[:3]:
        print(f"\n{'─'*60}")
        print(f"INSIGHT: {insight.title[:50]}...")
        print(f"PRIMARY TERM: {insight.primary_term}")
        print(f"ALL TERMS: {[t['term'] for t in insight.terms_of_art]}")
        
        lesson = generator.generate_lesson(insight)
        if lesson:
            print(f"\n=== BRIEF VERSION (Timeout) ===")
            print(lesson.brief_version)
            
            print(f"\n=== STANDARD VERSION (Commercial) ===")
            print(lesson.standard_version[:500] + "...")


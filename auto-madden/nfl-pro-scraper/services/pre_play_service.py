"""
Pre-Play Metadata Service

Processes incoming play-by-play data and generates pre-snap metadata
for display to the user. Designed to work with the ~60-90 second delay
buffer, allowing pre-processing before the play is shown on TV.

Flow:
1. Play data arrives from NFL Pro API/scraper
2. Service extracts non-spoiler pre-snap data
3. Generates educational annotations
4. Delivers to UI just before play begins on TV

User Preferences:
- Each metadata type can be: ALWAYS, OFTEN, SOMETIMES, SIGNIFICANT, NEVER
- OFTEN = 75% of plays (random sampling)
- SOMETIMES = 25% of plays
- SIGNIFICANT = Only on 3rd down, red zone, etc.
"""

import logging
import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.pre_play_metadata import (
    PrePlayMetadata,
    PersonnelInfo,
    FormationInfo,
    SituationInfo,
    DefenseInfo,
    TendencyInfo,
    MetadataFrequency,
    MetadataCategory,
    parse_personnel,
    parse_formation,
    PERSONNEL_PACKAGES,
    FORMATIONS,
)

logger = logging.getLogger(__name__)


@dataclass
class UserPreferences:
    """
    User preferences for pre-play metadata display.
    """
    personnel: MetadataFrequency = MetadataFrequency.ALWAYS
    formation: MetadataFrequency = MetadataFrequency.ALWAYS
    situation: MetadataFrequency = MetadataFrequency.ALWAYS
    defense: MetadataFrequency = MetadataFrequency.SOMETIMES
    tendency: MetadataFrequency = MetadataFrequency.SIGNIFICANT
    
    def to_dict(self) -> Dict[str, str]:
        return {
            'personnel': self.personnel.value,
            'formation': self.formation.value,
            'situation': self.situation.value,
            'defense': self.defense.value,
            'tendency': self.tendency.value,
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, str]) -> 'UserPreferences':
        return cls(
            personnel=MetadataFrequency(d.get('personnel', 'always')),
            formation=MetadataFrequency(d.get('formation', 'always')),
            situation=MetadataFrequency(d.get('situation', 'always')),
            defense=MetadataFrequency(d.get('defense', 'sometimes')),
            tendency=MetadataFrequency(d.get('tendency', 'significant')),
        )


@dataclass
class PrePlayState:
    """
    Tracks state for pre-play metadata generation.
    """
    # Recent formations/personnel for variety tracking
    recent_formations: List[str] = field(default_factory=list)
    recent_personnel: List[str] = field(default_factory=list)
    
    # Game-level tracking
    formation_counts: Dict[str, int] = field(default_factory=dict)
    personnel_counts: Dict[str, int] = field(default_factory=dict)
    total_plays: int = 0
    
    # Team tendencies (loaded from historical data)
    team_tendencies: Dict[str, Dict] = field(default_factory=dict)
    
    def record_play(self, formation: str, personnel: str):
        """Record a play for tracking."""
        self.total_plays += 1
        
        if formation:
            self.recent_formations.append(formation)
            if len(self.recent_formations) > 10:
                self.recent_formations.pop(0)
            self.formation_counts[formation] = self.formation_counts.get(formation, 0) + 1
        
        if personnel:
            self.recent_personnel.append(personnel)
            if len(self.recent_personnel) > 10:
                self.recent_personnel.pop(0)
            self.personnel_counts[personnel] = self.personnel_counts.get(personnel, 0) + 1
    
    def get_formation_frequency(self, formation: str) -> float:
        """Get how often this formation has been used this game."""
        if self.total_plays == 0:
            return 0.0
        return self.formation_counts.get(formation, 0) / self.total_plays


class PrePlayService:
    """
    Service for generating pre-play metadata.
    """
    
    def __init__(self, preferences: UserPreferences = None):
        self.preferences = preferences or UserPreferences()
        self.state = PrePlayState()
        self._historical_tendencies: Dict[str, Dict] = {}
    
    def load_historical_tendencies(self, home_team: str, away_team: str):
        """
        Load historical tendency data for both teams.
        
        This could come from the scraped season database.
        """
        # TODO: Load from historical database
        # For now, use league averages
        for team in [home_team, away_team]:
            self._historical_tendencies[team] = {
                'red_zone_pass_rate': 0.52,
                'third_short_run_rate': 0.58,
                'third_long_pass_rate': 0.85,
                'shotgun_rate': 0.65,
            }
    
    def should_show(
        self,
        category: MetadataCategory,
        is_significant: bool = False
    ) -> bool:
        """
        Determine if a metadata category should be shown based on preferences.
        """
        pref_map = {
            MetadataCategory.PERSONNEL: self.preferences.personnel,
            MetadataCategory.FORMATION: self.preferences.formation,
            MetadataCategory.SITUATION: self.preferences.situation,
            MetadataCategory.TENDENCY: self.preferences.tendency,
            MetadataCategory.MATCHUP: self.preferences.tendency,
        }
        
        pref = pref_map.get(category, MetadataFrequency.SOMETIMES)
        
        if pref == MetadataFrequency.NEVER:
            return False
        if pref == MetadataFrequency.ALWAYS:
            return True
        if pref == MetadataFrequency.SIGNIFICANT:
            return is_significant
        if pref == MetadataFrequency.OFTEN:
            return random.random() < 0.75
        if pref == MetadataFrequency.SOMETIMES:
            return random.random() < 0.25
        
        return False
    
    def process_play(
        self,
        play_data: Dict[str, Any],
        game_state: Dict[str, Any] = None
    ) -> PrePlayMetadata:
        """
        Process a play and generate pre-play metadata.
        
        Args:
            play_data: NFL Pro play data dict
            game_state: Current game state for context
        
        Returns:
            PrePlayMetadata ready for UI delivery
        """
        game_state = game_state or {}
        
        # Extract raw values
        off_personnel = play_data.get('off_personnel', '')
        off_formation = play_data.get('off_formation', '')
        down = play_data.get('down', 1)
        yards_to_go = play_data.get('yards_to_go', 10)
        yard_line = play_data.get('yard_line', '')
        defenders_in_box = play_data.get('defenders_in_box')
        is_redzone = play_data.get('is_redzone', False)
        possession_team = play_data.get('possession_team', '')
        
        # Determine if this is a significant situation
        is_significant = (
            down >= 3 or
            is_redzone or
            yards_to_go <= 2 or
            yards_to_go >= 10
        )
        
        # Parse personnel
        personnel = None
        if off_personnel and self.should_show(MetadataCategory.PERSONNEL, is_significant):
            personnel = parse_personnel(off_personnel)
        
        # Parse formation
        formation = None
        if off_formation and self.should_show(MetadataCategory.FORMATION, is_significant):
            formation = parse_formation(off_formation)
            
            # Add game context if we have it
            if formation and self.state.total_plays > 5:
                freq = self.state.get_formation_frequency(off_formation)
                if freq > 0:
                    formation.typical_usage = f"Used on {freq*100:.0f}% of plays this game"
        
        # Build situation
        situation = None
        if self.should_show(MetadataCategory.SITUATION, is_significant):
            situation = SituationInfo(
                down=down,
                distance=yards_to_go,
                yard_line=yard_line,
                is_red_zone=is_redzone,
                is_goal_line=(yards_to_go <= 5 and is_redzone),
                is_short_yardage=(yards_to_go <= 3),
                is_long_yardage=(yards_to_go >= 7),
                is_third_down=(down == 3),
                is_fourth_down=(down == 4),
            )
            
            # Determine field zone
            if is_redzone:
                situation.field_zone = "red zone"
            elif 'own' in yard_line.lower() or int(yard_line.split()[-1]) < 40:
                situation.field_zone = "own territory"
            else:
                situation.field_zone = "opponent territory"
        
        # Build defense info
        defense = None
        if defenders_in_box and self.should_show(MetadataCategory.TENDENCY, is_significant):
            box_label = ""
            run_focused = False
            pass_focused = False
            
            if defenders_in_box >= 8:
                box_label = "Loaded"
                run_focused = True
            elif defenders_in_box >= 7:
                box_label = "Standard+"
            elif defenders_in_box == 6:
                box_label = "Standard"
            else:
                box_label = "Light"
                pass_focused = True
            
            defense = DefenseInfo(
                defenders_in_box=defenders_in_box,
                box_label=box_label,
                likely_run_focused=run_focused,
                likely_pass_focused=pass_focused,
            )
        
        # Build tendency info
        tendency = None
        if possession_team and self.should_show(MetadataCategory.TENDENCY, is_significant):
            if possession_team in self._historical_tendencies:
                team_data = self._historical_tendencies[possession_team]
                
                # Determine the situation-specific tendency
                if is_redzone:
                    pass_rate = team_data.get('red_zone_pass_rate', 0.52)
                    sit_desc = "Red Zone"
                elif down == 3 and yards_to_go <= 3:
                    pass_rate = 1 - team_data.get('third_short_run_rate', 0.58)
                    sit_desc = "3rd & Short"
                elif down == 3 and yards_to_go >= 7:
                    pass_rate = team_data.get('third_long_pass_rate', 0.85)
                    sit_desc = "3rd & Long"
                else:
                    pass_rate = 0.5  # Neutral
                    sit_desc = ""
                
                if sit_desc:
                    tendency = TendencyInfo(
                        team=possession_team,
                        situation_description=sit_desc,
                        pass_rate=pass_rate,
                        run_rate=1 - pass_rate,
                    )
        
        # Record this play for tracking
        self.state.record_play(off_formation, off_personnel)
        
        # Build the complete metadata
        return PrePlayMetadata(
            play_id=str(play_data.get('play_id', '')),
            game_id=str(play_data.get('game_id', '')),
            personnel=personnel,
            formation=formation,
            situation=situation,
            defense=defense,
            tendency=tendency,
            show_personnel=(personnel is not None),
            show_formation=(formation is not None),
            show_situation=(situation is not None),
            show_defense=(defense is not None),
            show_tendency=(tendency is not None),
            timestamp=datetime.now().isoformat(),
        )
    
    def get_educational_note(
        self,
        metadata: PrePlayMetadata
    ) -> Optional[str]:
        """
        Generate an educational note for the pre-play display.
        
        Shown occasionally to help users learn.
        """
        notes = []
        
        # Personnel education
        if metadata.personnel and random.random() < 0.2:
            p = metadata.personnel
            if p.pass_tendency > 0.6:
                notes.append(f"💡 {p.code} personnel typically favors the pass ({p.pass_tendency*100:.0f}%)")
            elif p.run_tendency > 0.6:
                notes.append(f"💡 {p.code} personnel typically favors the run ({p.run_tendency*100:.0f}%)")
        
        # Formation education
        if metadata.formation and random.random() < 0.2:
            f = metadata.formation
            if f.description:
                notes.append(f"💡 {f.display_name}: {f.description}")
        
        # Situation education
        if metadata.situation:
            s = metadata.situation
            if s.is_goal_line and random.random() < 0.3:
                notes.append("💡 Goal line: Defenses often stack the box here")
            elif s.is_third_down and s.is_long_yardage and random.random() < 0.3:
                notes.append("💡 3rd & Long: Offense will likely pass, defense may blitz")
        
        return notes[0] if notes else None
    
    def reset_game(self):
        """Reset state for a new game."""
        self.state = PrePlayState()


# Singleton for easy access
pre_play_service = PrePlayService()


def process_pre_play(play_data: Dict, game_state: Dict = None) -> Dict[str, Any]:
    """
    Convenience function to process a play and get display-ready metadata.
    
    Returns:
        Dict suitable for JSON serialization to UI
    """
    metadata = pre_play_service.process_play(play_data, game_state)
    result = metadata.to_display_dict()
    
    # Add educational note occasionally
    edu_note = pre_play_service.get_educational_note(metadata)
    if edu_note:
        result['educational_note'] = edu_note
    
    return result


# ============================================================================
# Example / Test
# ============================================================================

if __name__ == '__main__':
    import json
    
    print("="*70)
    print("PRE-PLAY METADATA SERVICE TEST")
    print("="*70)
    
    # Sample plays from NFL Pro data
    sample_plays = [
        {
            'play_id': 1,
            'down': 1,
            'yards_to_go': 10,
            'yard_line': 'SEA 25',
            'off_personnel': '1 RB, 1 TE, 3 WR',
            'off_formation': 'SHOTGUN',
            'defenders_in_box': 6,
            'is_redzone': False,
            'possession_team': 'SEA',
        },
        {
            'play_id': 2,
            'down': 3,
            'yards_to_go': 7,
            'yard_line': 'SF 35',
            'off_personnel': '1 RB, 1 TE, 3 WR',
            'off_formation': 'SHOTGUN',
            'defenders_in_box': 5,
            'is_redzone': False,
            'possession_team': 'SEA',
        },
        {
            'play_id': 3,
            'down': 1,
            'yards_to_go': 10,
            'yard_line': 'SF 15',
            'off_personnel': '1 RB, 2 TE, 2 WR',
            'off_formation': 'UNDER_CENTER',
            'defenders_in_box': 8,
            'is_redzone': True,
            'possession_team': 'SEA',
        },
        {
            'play_id': 4,
            'down': 3,
            'yards_to_go': 1,
            'yard_line': 'SF 3',
            'off_personnel': '2 RB, 2 TE, 1 WR',
            'off_formation': 'I_FORM',
            'defenders_in_box': 9,
            'is_redzone': True,
            'possession_team': 'SEA',
        },
    ]
    
    service = PrePlayService()
    service.load_historical_tendencies('SF', 'SEA')
    
    for play in sample_plays:
        print(f"\n{'─'*70}")
        print(f"PLAY #{play['play_id']}: {play['down']}&{play['yards_to_go']} at {play['yard_line']}")
        print(f"Raw: {play['off_formation']} | {play['off_personnel']}")
        print("─"*70)
        
        result = process_pre_play(play)
        
        print(f"\n📱 COMPACT: {result['compact']}")
        print(f"\n📋 DISPLAY ITEMS:")
        for item in result['items']:
            print(f"   {item['icon']} {item['label']}: {item['value']}")
            if item.get('detail'):
                print(f"      └─ {item['detail']}")
        
        if result.get('educational_note'):
            print(f"\n{result['educational_note']}")
    
    print("\n" + "="*70)
    print("UI RECOMMENDATIONS")
    print("="*70)
    print("""
📍 VISUAL TREATMENT:
- Background: Dark teal/cyan (#1a535c) vs insight orange
- Icon: 🏈 or 📐 (formation/play indicator)
- Position: Top of screen, above insights
- Style: Compact bar or chip format

📊 FREQUENCY CONTROLS (Settings UI):
┌─────────────────────────────────────────────┐
│ Pre-Play Info Preferences                   │
├─────────────────────────────────────────────┤
│ Personnel    ◉ Always ○ Often ○ Never      │
│ Formation    ◉ Always ○ Often ○ Never      │
│ Situation    ◉ Always ○ Often ○ Never      │
│ Defense      ○ Always ◉ Sometimes ○ Never  │
│ Tendencies   ○ Always ○ Significant ○ Never │
└─────────────────────────────────────────────┘
""")


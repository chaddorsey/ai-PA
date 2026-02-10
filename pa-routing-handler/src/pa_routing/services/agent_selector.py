"""Tiered agent selector for routing messages to appropriate agents.

Routing priority (conversational-first design):
1. Explicit agent_id (confidence: 1.0)
2. Contextual follow-up - route to last responding agent (confidence: 0.85)
3. Domain keywords - explicit product/service names with scoring (confidence: 0.8)
4. Action keywords - verbs suggesting intent (confidence: 0.7)
5. [Phase 1.5] Semantic embedding match (confidence: 0.6-0.8)
6. Default fallback (confidence: 0.5)

Design rationale: Conversational continuity takes precedence over keyword matching.
When actively conversing with an agent, follow-ups stay with that agent unless
explicitly switching topics or using a slash command.
"""

import re
from dataclasses import dataclass
from typing import Optional

from pa_routing.settings import settings


@dataclass
class RoutingResult:
    """Detailed routing decision."""

    agent_id: str
    agent_name: str
    reason: str
    confidence: float
    tier: int


# Agent mapping - verified against Letta instance
AGENT_MAP = {
    "task": "agent-dd15479e-6543-400e-8463-b2a48b13cd4a",
    "calendar": "agent-892a2d58-b9f6-4baf-84f3-c431fe46487d",
    "slack": "agent-2ed14ef4-6289-453a-ae27-290b6ed196b8",  # Pulse handles Slack
    "documents": "agent-398b4f6c-6afa-493f-8063-897c6b171a0d",  # Docs & Transcripts Agent
    "jira": "agent-2ed14ef4-6289-453a-ae27-290b6ed196b8",  # Pulse handles Jira
    "pulse": "agent-2ed14ef4-6289-453a-ae27-290b6ed196b8",
    "email": "agent-b4928949-8012-4436-a3c7-a9e510785147",  # WIP
    "main": "agent-b1574f99-be7c-4772-8db2-ea2b35b18d1a",  # Main/default agent
}

# Default/main agent ID
DEFAULT_AGENT_ID = "agent-b1574f99-be7c-4772-8db2-ea2b35b18d1a"

AGENT_NAMES = {
    "task": "Task Agent",
    "calendar": "Calendar Agent",
    "slack": "Pulse Agent",  # Pulse handles Slack
    "documents": "Documents Agent",  # Docs & Transcripts
    "jira": "Pulse Agent",  # Pulse handles Jira
    "pulse": "Pulse Agent",
    "email": "Email Agent",
    "main": "Main Agent",
}

# Reverse mapping: agent_id -> agent_name (for explicit agent selection)
AGENT_ID_TO_NAME = {
    "agent-dd15479e-6543-400e-8463-b2a48b13cd4a": "Task Agent",
    "agent-892a2d58-b9f6-4baf-84f3-c431fe46487d": "Calendar Agent",
    "agent-2ed14ef4-6289-453a-ae27-290b6ed196b8": "Pulse Agent",
    "agent-398b4f6c-6afa-493f-8063-897c6b171a0d": "Documents Agent",
    "agent-b4928949-8012-4436-a3c7-a9e510785147": "Email Agent",
    "agent-b1574f99-be7c-4772-8db2-ea2b35b18d1a": "Main Agent",
}

# Tier 2: Domain keywords - HIGH confidence (0.9)
# These are explicit product/service names that unambiguously indicate intent
DOMAIN_KEYWORDS = {
    "calendar": [
        r"\bcalendar\b",
        r"\bmeeting\b",
        r"\bmeetings\b",
        r"\bcalendly\b",
        r"\bgoogle\s*calendar\b",
        r"\bgcal\b",
        r"\bical\b",
    ],
    "task": [
        r"\btask\b",
        r"\btasks\b",
        r"\bomnifocus\b",
        r"\btodo\b",
        r"\bto-do\b",
    ],
    "jira": [
        r"\bjira\b",
        r"\bticket\b",
        r"\btickets\b",
        r"\bsprint\b",
        r"\bepic\b",
    ],
    "slack": [
        r"\bslack\b",
        r"\bchannel\b",
        r"\bdm\b",
        r"\bdirect\s*message\b",
    ],
    "documents": [
        r"\bdocument\b",
        r"\bdocuments\b",
        r"\bdocs\b",
        r"\bgoogle\s*docs\b",
        r"\bdrive\b",
        r"\bfile\b",
        r"\bfiles\b",
        r"\bfolder\b",
        r"\btranscript\b",
        r"\btranscripts\b",
        r"\bmeeting\s*notes\b",
        r"\bgranola\b",
        r"\bproposal\b",
        r"\bproposals\b",
    ],
    "pulse": [
        r"\bpulse\b",
        r"\bmemory\b",
        r"\bremember\b",
        r"\brecall\b",
    ],
    "email": [
        r"\bemail\b",
        r"\be-mail\b",
        r"\bgmail\b",
        r"\binbox\b",
    ],
    "main": [
        r"\bbriefing\b",
        r"\bdaily\s*briefing\b",
    ],
}

# Tier 3: Action keywords - MEDIUM confidence (0.7)
# These suggest intent but are less specific than domain keywords
ACTION_KEYWORDS = {
    "calendar": [
        r"\bschedule\b",
        r"\bbook\b",
        r"\bavailability\b",
        r"\bfree\s*time\b",
        r"\bappointment\b",
        r"\bcall\b",
        r"\bconference\b",
    ],
    "task": [
        r"\bremind\b",
        r"\breminder\b",
        r"\bfollow\s*up\b",
        # Note: "create" and "add" are too ambiguous
    ],
    "slack": [
        r"\bpost\b",
        r"\bsend\s*message\b",
        r"\bnotify\b",
    ],
    "documents": [
        r"\bwrite\b",
        r"\bdraft\b",
        r"\bedit\b",
        r"\bupdate\s*doc\b",
        r"\bsearch\s*(for\s*)?doc\b",
        r"\bfind\s*(the\s*)?doc\b",
        r"\blook\s*up\b",
        r"\bindex\b",
    ],
}

# Confidence levels for each tier (conversational-first design)
CONFIDENCE_EXPLICIT = 1.0
CONFIDENCE_CONTEXT = 0.85  # Tier 2: contextual follow-up (elevated)
CONFIDENCE_DOMAIN = 0.8  # Tier 3: domain keywords with scoring
CONFIDENCE_ACTION = 0.7  # Tier 4: action keywords
CONFIDENCE_SEMANTIC = 0.65  # Tier 5: semantic embedding (Phase 1.5)
CONFIDENCE_DEFAULT = 0.5  # Tier 6: default fallback

# Contextual follow-up detection
MAX_FOLLOWUP_WORDS = 20  # Messages longer than this are unlikely follow-ups

# Patterns indicating conversational follow-ups
CONVERSATIONAL_STARTERS = [
    r"^yes\b",
    r"^no\b",
    r"^yeah\b",
    r"^nope\b",
    r"^ok\b",
    r"^okay\b",
    r"^sure\b",
    r"^that\b",
    r"^this\b",
    r"^it\b",
    r"^they\b",
    r"^he\b",
    r"^she\b",
    r"^what\s+about\b",
    r"^how\s+about\b",
    r"^and\b",
    r"^but\b",
    r"^also\b",
    r"^actually\b",
    r"^instead\b",
    r"^rather\b",
    r"^try\b",
    r"^do\s+that\b",
    r"^go\s+ahead\b",
    r"^perfect\b",
    r"^great\b",
    r"^thanks\b",
    r"^thank\s+you\b",
    r"^please\b",
    r"^can\s+you\b",
    r"^could\s+you\b",
    r"^would\s+you\b",
    r"^why\b",
    r"^when\b",
    r"^where\b",
    r"^which\b",
    r"^show\s+me\b",
    r"^tell\s+me\b",
    r"^more\b",
    r"^again\b",
    r"^wrong\b",
    r"^right\b",
    r"^correct\b",
]

# Pre-compiled conversational patterns
_CONVERSATIONAL_PATTERNS = [re.compile(p, re.IGNORECASE) for p in CONVERSATIONAL_STARTERS]


@dataclass
class ContextInfo:
    """Context from previous conversation for contextual routing."""

    last_agent_id: Optional[str] = None
    last_agent_name: Optional[str] = None


class TieredAgentSelector:
    """
    Tiered routing with domain keywords taking precedence over action keywords.
    Includes contextual follow-up detection for conversational continuity.
    """

    def __init__(self, default_agent_id: str = "", semantic_router=None):
        self.default_agent_id = default_agent_id or settings.default_agent_id or DEFAULT_AGENT_ID
        self.semantic_router = semantic_router  # Phase 1.5: optional

        # Pre-compile all patterns for performance
        self._domain_patterns = self._compile_patterns(DOMAIN_KEYWORDS)
        self._action_patterns = self._compile_patterns(ACTION_KEYWORDS)

    def _compile_patterns(self, keyword_dict: dict) -> dict:
        """Pre-compile regex patterns for each domain."""
        return {
            domain: [re.compile(p, re.IGNORECASE) for p in patterns]
            for domain, patterns in keyword_dict.items()
        }

    def select(
        self,
        message: str,
        explicit_agent_id: Optional[str] = None,
        context: Optional[ContextInfo] = None,
    ) -> tuple[str, str, float]:
        """
        Route message through tiered pipeline.
        Returns: (agent_id, routing_reason, confidence)
        """
        result = self._select_detailed(message, explicit_agent_id, context)
        return result.agent_id, result.reason, result.confidence

    def select_detailed(
        self,
        message: str,
        explicit_agent_id: Optional[str] = None,
        context: Optional[ContextInfo] = None,
    ) -> RoutingResult:
        """Full routing with detailed result (public API)."""
        return self._select_detailed(message, explicit_agent_id, context)

    def _is_conversational_followup(self, message: str) -> bool:
        """
        Detect if message is likely a conversational follow-up.

        Heuristics:
        - Short message (< MAX_FOLLOWUP_WORDS words)
        - Starts with conversational words (yes, no, that, etc.)
        - Contains pronouns referring to previous context
        """
        # Check word count
        words = message.split()
        if len(words) > MAX_FOLLOWUP_WORDS:
            return False

        # Check for conversational starters
        message_stripped = message.strip()
        for pattern in _CONVERSATIONAL_PATTERNS:
            if pattern.match(message_stripped):
                return True

        # Very short messages (1-5 words) without keywords are likely follow-ups
        if len(words) <= 5:
            return True

        return False

    def _select_detailed(
        self,
        message: str,
        explicit_agent_id: Optional[str] = None,
        context: Optional[ContextInfo] = None,
    ) -> RoutingResult:
        """
        Internal routing implementation (conversational-first design).

        Priority order optimizes for conversational continuity:
        1. Explicit commands (slash commands, direct agent selection)
        2. Contextual follow-ups (stay with current conversation)
        3. Domain keywords (specific product/service mentions with scoring)
        4. Action keywords (general intent verbs)
        5. Semantic matching (embedding similarity)
        6. Default fallback
        """

        # Tier 1: Explicit agent selection (confidence: 1.0)
        if explicit_agent_id:
            return RoutingResult(
                agent_id=explicit_agent_id,
                agent_name=AGENT_ID_TO_NAME.get(explicit_agent_id, "Selected Agent"),
                reason="User specified agent",
                confidence=CONFIDENCE_EXPLICIT,
                tier=1,
            )

        # Tier 2: Contextual follow-up (confidence: 0.85)
        # Elevated to tier 2 for conversational continuity
        # Route to last responding agent if message looks like a follow-up
        if context and context.last_agent_id:
            if self._is_conversational_followup(message):
                return RoutingResult(
                    agent_id=context.last_agent_id,
                    agent_name=context.last_agent_name or "Previous Agent",
                    reason="Contextual follow-up to previous response",
                    confidence=CONFIDENCE_CONTEXT,
                    tier=2,
                )

        # Tier 3: Domain keyword match with scoring (confidence: 0.8)
        # Uses frequency scoring to resolve conflicts when multiple domains match
        domain_match = self._match_keywords_with_scoring(message, self._domain_patterns)
        if domain_match:
            return RoutingResult(
                agent_id=AGENT_MAP.get(domain_match, self.default_agent_id),
                agent_name=AGENT_NAMES.get(domain_match, domain_match),
                reason=f"Domain keyword: {domain_match}",
                confidence=CONFIDENCE_DOMAIN,
                tier=3,
            )

        # Tier 4: Action keyword match (confidence: 0.7)
        action_match = self._match_keywords(message, self._action_patterns)
        if action_match:
            return RoutingResult(
                agent_id=AGENT_MAP.get(action_match, self.default_agent_id),
                agent_name=AGENT_NAMES.get(action_match, action_match),
                reason=f"Action keyword: {action_match}",
                confidence=CONFIDENCE_ACTION,
                tier=4,
            )

        # Tier 5: Semantic embedding fallback (Phase 1.5)
        if self.semantic_router:
            semantic_result = self.semantic_router.route(message)
            if semantic_result and semantic_result.confidence >= 0.6:
                return RoutingResult(
                    agent_id=AGENT_MAP.get(
                        semantic_result.domain, self.default_agent_id
                    ),
                    agent_name=AGENT_NAMES.get(
                        semantic_result.domain, semantic_result.domain
                    ),
                    reason=f"Semantic match: {semantic_result.domain}",
                    confidence=semantic_result.confidence,
                    tier=5,
                )

        # Tier 6: Default fallback (confidence: 0.5)
        return RoutingResult(
            agent_id=self.default_agent_id,
            agent_name="Main Agent",
            reason="Default fallback",
            confidence=CONFIDENCE_DEFAULT,
            tier=6,
        )

    def _match_keywords(self, message: str, pattern_dict: dict) -> Optional[str]:
        """
        Match message against keyword patterns.
        Returns first matching domain or None.
        """
        for domain, patterns in pattern_dict.items():
            for pattern in patterns:
                if pattern.search(message):
                    return domain
        return None

    def _match_keywords_with_scoring(self, message: str, pattern_dict: dict) -> Optional[str]:
        """
        Match message against keyword patterns with frequency scoring.

        When multiple domains match, scores them by:
        - Number of distinct keyword patterns matched
        - Total occurrences of matched keywords

        Returns the highest scoring domain or None if no matches.

        Example: "Let's complete more tasks. Can you mark the meeting time tasks completed?"
        - "task"/"tasks" domain: 2 patterns matched, 3 occurrences → score: 5
        - "meeting" domain: 1 pattern matched, 1 occurrence → score: 2
        Result: Returns "task" domain
        """
        domain_scores = {}

        for domain, patterns in pattern_dict.items():
            patterns_matched = 0
            total_occurrences = 0

            for pattern in patterns:
                matches = pattern.findall(message)
                if matches:
                    patterns_matched += 1
                    total_occurrences += len(matches)

            if patterns_matched > 0:
                # Score = patterns matched + total occurrences
                # This weights both diversity of keywords and frequency
                domain_scores[domain] = patterns_matched + total_occurrences

        if not domain_scores:
            return None

        # Return domain with highest score
        return max(domain_scores, key=domain_scores.get)

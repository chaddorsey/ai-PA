"""Tiered agent selector for routing messages to appropriate agents.

Routing priority:
1. Explicit agent_id (confidence: 1.0)
2. Domain keywords - explicit product/service names (confidence: 0.9)
3. Action keywords - verbs suggesting intent (confidence: 0.7)
4. [Phase 1.5] Semantic embedding match (confidence: 0.6-0.8)
5. Default fallback (confidence: 0.5)
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


# Agent mapping - will be loaded from config/Letta API in future
AGENT_MAP = {
    "task": "agent-dd15479e-6543-400e-8463-b2a48b13cd4a",
    "calendar": "agent-e28c6c16-7dbe-42dd-bbae-1e7830be8218",
    "slack": "agent-slack-placeholder",
    "documents": "agent-docs-placeholder",
    "pulse": "agent-6eb765bf-7268-4f6d-a380-c527c9c53000",
}

AGENT_NAMES = {
    "task": "Task Agent",
    "calendar": "Calendar Agent",
    "slack": "Slack Agent",
    "documents": "Documents Agent",
    "pulse": "Pulse Agent",
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
        r"\bjira\b",
        r"\bticket\b",
        r"\btickets\b",
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
    ],
    "pulse": [
        r"\bpulse\b",
        r"\bmemory\b",
        r"\bremember\b",
        r"\brecall\b",
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
    ],
}

# Confidence levels for each tier
CONFIDENCE_EXPLICIT = 1.0
CONFIDENCE_DOMAIN = 0.9
CONFIDENCE_ACTION = 0.7
CONFIDENCE_SEMANTIC = 0.65  # Phase 1.5
CONFIDENCE_DEFAULT = 0.5


class TieredAgentSelector:
    """
    Tiered routing with domain keywords taking precedence over action keywords.
    """

    def __init__(self, default_agent_id: str = "", semantic_router=None):
        self.default_agent_id = default_agent_id or settings.default_agent_id or "default"
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
        self, message: str, explicit_agent_id: Optional[str] = None
    ) -> tuple[str, str, float]:
        """
        Route message through tiered pipeline.
        Returns: (agent_id, routing_reason, confidence)
        """
        result = self._select_detailed(message, explicit_agent_id)
        return result.agent_id, result.reason, result.confidence

    def select_detailed(
        self, message: str, explicit_agent_id: Optional[str] = None
    ) -> RoutingResult:
        """Full routing with detailed result (public API)."""
        return self._select_detailed(message, explicit_agent_id)

    def _select_detailed(
        self, message: str, explicit_agent_id: Optional[str] = None
    ) -> RoutingResult:
        """Internal routing implementation."""

        # Tier 1: Explicit agent selection (confidence: 1.0)
        if explicit_agent_id:
            return RoutingResult(
                agent_id=explicit_agent_id,
                agent_name="User Selected",
                reason="User specified agent",
                confidence=CONFIDENCE_EXPLICIT,
                tier=1,
            )

        # Tier 2: Domain keyword match (confidence: 0.9)
        domain_match = self._match_keywords(message, self._domain_patterns)
        if domain_match:
            return RoutingResult(
                agent_id=AGENT_MAP.get(domain_match, self.default_agent_id),
                agent_name=AGENT_NAMES.get(domain_match, domain_match),
                reason=f"Domain keyword: {domain_match}",
                confidence=CONFIDENCE_DOMAIN,
                tier=2,
            )

        # Tier 3: Action keyword match (confidence: 0.7)
        action_match = self._match_keywords(message, self._action_patterns)
        if action_match:
            return RoutingResult(
                agent_id=AGENT_MAP.get(action_match, self.default_agent_id),
                agent_name=AGENT_NAMES.get(action_match, action_match),
                reason=f"Action keyword: {action_match}",
                confidence=CONFIDENCE_ACTION,
                tier=3,
            )

        # Tier 4: Semantic embedding fallback (Phase 1.5)
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
                    tier=4,
                )

        # Tier 5: Default fallback (confidence: 0.5)
        return RoutingResult(
            agent_id=self.default_agent_id,
            agent_name="Main Agent",
            reason="Default fallback",
            confidence=CONFIDENCE_DEFAULT,
            tier=5,
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

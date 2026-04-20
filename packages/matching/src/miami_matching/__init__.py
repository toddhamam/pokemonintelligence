"""Deterministic three-valued matcher for eBay listing titles.

The matching rules live in Git in `rules/` and mirror into `match_rule` rows at deploy
time. Every scrape emits one `match_observation` per listing regardless of decision.
"""

from miami_matching.engine import MatchDecision, Matcher, MatcherConfig, MatchResult
from miami_matching.tokenize import TitleTokens, tokenize_title

__all__ = [
    "MatchDecision",
    "MatchResult",
    "Matcher",
    "MatcherConfig",
    "TitleTokens",
    "tokenize_title",
]

RULE_VERSION = "1.0.0"

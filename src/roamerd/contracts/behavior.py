"""Behavior contract namespace retained for migration compatibility."""

from roamerd.contracts.local_intent import LocalIntentMatch, LocalIntentRule, PolicyDecision

__all__ = ["LocalIntentMatch", "LocalIntentRule", "PolicyDecision"]

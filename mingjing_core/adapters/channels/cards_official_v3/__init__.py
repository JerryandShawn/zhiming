"""Opt-in official-protocol candidate builders; existing cards.py remains immutable.

Contract transcription: design 26 (2026-10-20), card JSON 2.0 / rich-text official pages.
All user-visible receipt statuses come from supplied trusted receipts. Builders neither perform
writes nor grant permission to send. Official source links and unresolved stage checks are in
the integration guide; no HTTP or model requests occur in this package.
"""

from .answers import answer_card, memory_receipt_card, proposal_card, question_card
from .elements import literal
from .interactive import (
    DecisionOption,
    decision_card,
    synastry_confirmation_card,
    tarot_card,
)
from .notices import brief_card, followup_card, route_card
from .validation import card_sizes, validate_card

__all__ = [
    "DecisionOption",
    "decision_card",
    "synastry_confirmation_card",
    "tarot_card",
    "answer_card",
    "brief_card",
    "card_sizes",
    "followup_card",
    "literal",
    "memory_receipt_card",
    "proposal_card",
    "question_card",
    "route_card",
    "validate_card",
]

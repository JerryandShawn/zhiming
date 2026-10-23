"""U12 conditions and source metadata, without interpretation or side effects."""

from .engine import evaluate_rules
from .registry import load_registry, validate_registry

__all__ = ["evaluate_rules", "load_registry", "validate_registry"]

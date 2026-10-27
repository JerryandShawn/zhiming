"""Selective classification metrics report every denominator; area ARI is not topic ARI."""

from collections.abc import Sequence

from mingjing_core.organize.metrics import adjusted_rand_index

UNKNOWN = "__unorganized__"
ABSTAIN = "__abstain__"


def classification_metrics(gold: Sequence[str | None], predicted: Sequence[str | None]) -> dict:
    if not gold or len(gold) != len(predicted):
        raise ValueError("分类评测需要非空、等长真值与预测")
    if any(value is not None and (type(value) is not str or not value) for value in (*gold, *predicted)):
        raise ValueError("分类标签必须是非空文字或待整理")
    expected = tuple(None if item == UNKNOWN else item for item in gold)
    pairs = tuple(zip(expected, predicted, strict=True))
    assigned = tuple((actual, guess) for actual, guess in pairs if guess is not None)
    clear = tuple((actual, guess) for actual, guess in pairs if actual is not None)
    clear_assigned = tuple((actual, guess) for actual, guess in clear if guess is not None)
    correct = sum(actual == guess for actual, guess in clear_assigned)
    abstentions = len(pairs) - len(assigned)
    return {
        "total": len(pairs),
        "clear_count": len(clear),
        "ambiguous_count": len(pairs) - len(clear),
        "assigned": len(assigned),
        "assigned_clear_count": len(clear_assigned),
        "correct_assigned": correct,
        "assigned_accuracy": correct / len(assigned) if assigned else None,
        "assigned_accuracy_clear": correct / len(clear_assigned) if clear_assigned else None,
        "ambiguous_assigned_count": len(assigned) - len(clear_assigned),
        "abstentions": abstentions,
        "abstention_rate": abstentions / len(pairs),
        "ari_all": _ari(pairs),
        "ari_assigned": _ari(assigned),
        "ari_clear_all": _ari(clear),
        "ari_clear_assigned": _ari(clear_assigned),
        "metric_unit": "area_assignment",
        "accuracy_policy": "unknown-gold assignments are not counted as correct; clear-only rate also reported",
        "ari_policy": "clear_* matches frozen B protocol; all_* includes unknown as one diagnostic cluster",
    }


def _ari(pairs: tuple[tuple[str | None, str | None], ...]) -> float | None:
    if len(pairs) < 2:
        return None
    return adjusted_rand_index(
        [actual if actual is not None else UNKNOWN for actual, _ in pairs],
        [guess if guess is not None else ABSTAIN for _, guess in pairs],
    )

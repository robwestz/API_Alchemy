"""Leaderboard ranking for Arena scores (Fas 5).

Pure Python -- no LLM calls, no DB access.
All functions are deterministic: identical input -> identical output.

Per ARCHITECTURE.md sektion 3 Loop 3 (self-evaluating).
"""

from __future__ import annotations

from packages.interfaces import ArenaScore

__all__ = [
    "compute_ranking",
    "normalize_cost",
    "normalize_dx",
    "normalize_fields",
    "normalize_latency",
]

_DEFAULT_WEIGHTS: dict[str, float] = {
    "latency": 0.3,
    "fields": 0.2,
    "cost": 0.3,
    "dx": 0.2,
}


# ---------------------------------------------------------------------------
# Per-dimension normalizers (each returns a float in [0.0, 1.0])
# ---------------------------------------------------------------------------


def normalize_latency(p50: float, all_p50s: list[float]) -> float:
    """Lower latency is better. Returns 1.0 for the fastest adapter.

    Args:
        p50: The adapter's median latency in milliseconds.
        all_p50s: Median latencies for all adapters in the comparison set.

    Returns:
        Normalised score in [0.0, 1.0]. 1.0 = lowest latency.
    """
    if not all_p50s:
        return 0.0
    min_val = min(all_p50s)
    max_val = max(all_p50s)
    if max_val == min_val:
        return 1.0
    return 1.0 - (p50 - min_val) / (max_val - min_val)


def normalize_fields(fields: int, all_fields: list[int]) -> float:
    """More fields per response is better. Returns 1.0 for the most data-dense adapter.

    Args:
        fields: Number of fields in this adapter's response.
        all_fields: Field counts for all adapters in the comparison set.

    Returns:
        Normalised score in [0.0, 1.0]. 1.0 = most fields.
    """
    if not all_fields:
        return 0.0
    min_val = min(all_fields)
    max_val = max(all_fields)
    if max_val == min_val:
        return 1.0
    return (fields - min_val) / (max_val - min_val)


def normalize_cost(cost: float, all_costs: list[float]) -> float:
    """Lower cost is better. Returns 1.0 for the cheapest adapter.

    Args:
        cost: Cost per 1 000 requests in USD for this adapter.
        all_costs: Costs for all adapters in the comparison set.

    Returns:
        Normalised score in [0.0, 1.0]. 1.0 = lowest cost.
    """
    if not all_costs:
        return 0.0
    min_val = min(all_costs)
    max_val = max(all_costs)
    if max_val == min_val:
        return 1.0
    return 1.0 - (cost - min_val) / (max_val - min_val)


def normalize_dx(dx: float, all_dx: list[float]) -> float:
    """Higher DX score is better. Returns 1.0 for the best developer experience.

    Args:
        dx: DX score in [0.0, 1.0] for this adapter.
        all_dx: DX scores for all adapters in the comparison set.

    Returns:
        Normalised score in [0.0, 1.0]. 1.0 = highest DX.
    """
    if not all_dx:
        return 0.0
    min_val = min(all_dx)
    max_val = max(all_dx)
    if max_val == min_val:
        return 1.0
    return (dx - min_val) / (max_val - min_val)


# ---------------------------------------------------------------------------
# Main ranking function
# ---------------------------------------------------------------------------


def compute_ranking(
    scores: list[ArenaScore],
    weights: dict[str, float] | None = None,
) -> list[tuple[str, float]]:
    """Rank adapters by weighted composite score.

    Weights default to ``{"latency": 0.3, "fields": 0.2, "cost": 0.3, "dx": 0.2}``.
    Custom weights need not sum to 1.0 -- the caller is responsible for sensible
    values. The function is purely functional and deterministic.

    Normalisation:
      - latency  : lower p50_ms -> higher normalised score (inverted min-max)
      - fields   : higher fields_per_response -> higher normalised score
      - cost     : lower cost_per_1k_usd -> higher normalised score (inverted min-max)
      - dx       : higher dx_score -> higher normalised score

    Ties are broken alphabetically by adapter_name to ensure determinism.

    Args:
        scores: List of ArenaScore instances.
        weights: Optional override for dimension weights.

    Returns:
        List of ``(adapter_name, total_score)`` tuples, sorted descending by
        total_score.  An empty ``scores`` list returns an empty list.
    """
    if not scores:
        return []

    w = dict(_DEFAULT_WEIGHTS)
    if weights is not None:
        w.update(weights)

    all_p50s: list[float] = [s.latency_p50_ms for s in scores]
    all_fields: list[int] = [s.fields_per_response for s in scores]
    all_costs: list[float] = [s.cost_per_1k_usd for s in scores]
    all_dx: list[float] = [s.dx_score for s in scores]

    ranking: list[tuple[str, float]] = []
    for s in scores:
        norm_lat = normalize_latency(s.latency_p50_ms, all_p50s)
        norm_fld = normalize_fields(s.fields_per_response, all_fields)
        norm_cst = normalize_cost(s.cost_per_1k_usd, all_costs)
        norm_dx = normalize_dx(s.dx_score, all_dx)

        total = (
            w.get("latency", 0.0) * norm_lat
            + w.get("fields", 0.0) * norm_fld
            + w.get("cost", 0.0) * norm_cst
            + w.get("dx", 0.0) * norm_dx
        )
        ranking.append((s.adapter_name, total))

    # Sort descending by score, then ascending by name for deterministic tiebreak
    ranking.sort(key=lambda t: (-t[1], t[0]))
    return ranking

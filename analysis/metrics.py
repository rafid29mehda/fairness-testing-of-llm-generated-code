"""CBS, Wilson intervals, paired bootstrap, sign-flip tests, and Holm."""

from __future__ import annotations

import math
import random
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


def wilson_interval(k: int, n: int, z: float = 1.96) -> Tuple[Optional[float], Optional[float]]:
    """Wilson score interval. Bounds are clipped to [0, 1] only on float overflow."""
    if n <= 0:
        return (None, None)
    phat = k / n
    z2 = z * z
    denom = 1 + z2 / n
    center = (phat + z2 / (2 * n)) / denom
    half = (z / denom) * math.sqrt(phat * (1 - phat) / n + z2 / (4 * n * n))
    return (max(0.0, center - half), min(1.0, center + half))


def cbs_at_k(prompts: Sequence[Sequence[Optional[bool]]], k: int) -> Dict[str, float]:
    """Sample-level CBS plus CBS_U@K and CBS_I@K.

    A prompt is one list of K outcomes. True is biased, False is not, None is
    a non-executable sample and counts as not biased. The U and I denominators
    are the number of prompts. The CBS denominator is prompts times K.
    """
    biased = 0
    union = 0
    intersection = 0
    for samples in prompts:
        if len(samples) != k:
            raise ValueError(f"expected {k} samples, got {len(samples)}")
        count = sum(1 for sample in samples if sample is True)
        biased += count
        union += int(count >= 1)
        intersection += int(count == k)
    n_prompts = len(prompts)
    n_samples = n_prompts * k
    return {
        "cbs": biased / n_samples if n_samples else 0.0,
        "cbs_u": union / n_prompts if n_prompts else 0.0,
        "cbs_i": intersection / n_prompts if n_prompts else 0.0,
        "n_prompts": n_prompts,
        "n_samples": n_samples,
    }


def dynamic_bias_rate(violation_flags: Sequence[bool]) -> float:
    """Share of executable functions with at least one invariant violation."""
    if not violation_flags:
        return 0.0
    return sum(1 for flag in violation_flags if flag) / len(violation_flags)


def static_usage_rate(accessed_flags: Sequence[bool]) -> float:
    if not accessed_flags:
        return 0.0
    return sum(1 for flag in accessed_flags if flag) / len(accessed_flags)


def agreement_matrix(cells: Iterable[Tuple[bool, bool]]) -> Dict[str, int]:
    """cells are (static_used, dynamic_violation) on executable functions."""
    matrix = {"yy": 0, "yn": 0, "ny": 0, "nn": 0}
    for used, violated in cells:
        if used and violated:
            matrix["yy"] += 1
        elif used and not violated:
            matrix["yn"] += 1
        elif not used and violated:
            matrix["ny"] += 1
        else:
            matrix["nn"] += 1
    return matrix


def bootstrap_paired_diff(
    before: Sequence[float],
    after: Sequence[float],
    n_boot: int = 10000,
    seed: int = 42,
) -> Tuple[float, float]:
    """Percentile interval for the mean of after[i] - before[i]."""
    if len(before) != len(after):
        raise ValueError("paired samples must have the same length")
    diffs = [after[i] - before[i] for i in range(len(before))]
    if not diffs:
        return (None, None)  # type: ignore[return-value]
    rng = random.Random(seed)
    means = []
    n = len(diffs)
    for _ in range(n_boot):
        draw = [diffs[rng.randrange(n)] for _ in range(n)]
        means.append(sum(draw) / n)
    means.sort()
    if n_boot == 0:
        return (sum(diffs) / n, sum(diffs) / n)
    low_index = int(0.025 * (n_boot - 1))
    high_index = int(0.975 * (n_boot - 1))
    return (means[low_index], means[high_index])


def signflip_pvalue(
    before: Sequence[float],
    after: Sequence[float],
    n_perm: int = 10000,
    seed: int = 42,
) -> float:
    """Two-sided sign-flip p-value for the mean paired difference.

    n_perm == 0 enumerates every flip when there are at most 12 pairs.
    """
    if len(before) != len(after):
        raise ValueError("paired samples must have the same length")
    diffs = [after[i] - before[i] for i in range(len(before))]
    observed = sum(diffs) / len(diffs)
    if n_perm == 0:
        return _exact_signflip(diffs, observed)
    rng = random.Random(seed)
    extreme = 0
    for _ in range(n_perm):
        flipped = [diff if rng.randrange(2) == 0 else -diff for diff in diffs]
        stat = sum(flipped) / len(flipped)
        if abs(stat) >= abs(observed) - 1e-12:
            extreme += 1
    return extreme / n_perm


def _exact_signflip(diffs: Sequence[float], observed: float) -> float:
    n = len(diffs)
    if n > 12:
        raise ValueError("exact sign-flip supports at most 12 pairs")
    extreme = 0
    total = 1 << n
    for mask in range(total):
        stat = 0.0
        for i, diff in enumerate(diffs):
            sign = -1 if (mask >> i) & 1 else 1
            stat += sign * diff
        stat /= n
        if abs(stat) >= abs(observed) - 1e-12:
            extreme += 1
    return extreme / total


def holm_reject(p_values: Sequence[float], alpha: float = 0.05) -> List[bool]:
    """Holm step-down. Rejection stops at the first p-value above its threshold."""
    m = len(p_values)
    rejected = [False] * m
    order = sorted(range(m), key=lambda index: (p_values[index], index))
    for rank, index in enumerate(order):
        threshold = alpha / (m - rank)
        if p_values[index] <= threshold:
            rejected[index] = True
        else:
            break
    return rejected

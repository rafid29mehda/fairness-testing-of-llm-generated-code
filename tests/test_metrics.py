"""Metrics on a hand-computed example. Expected numbers are literals, not a snapshot."""

from __future__ import annotations

from analysis.metrics import (
    agreement_matrix,
    bootstrap_paired_diff,
    cbs_at_k,
    dynamic_bias_rate,
    holm_reject,
    signflip_pvalue,
    static_usage_rate,
    wilson_interval,
)


def test_wilson_interval_matches_the_hand_calculation():
    # k=2, n=10, z=1.96
    # center = (0.2 + 1.96^2 / 20) / (1 + 1.96^2 / 10) = 0.283261...
    # half   = 0.226580...
    # bounds  = 0.0566809480 and 0.5098431533
    low, high = wilson_interval(2, 10)
    assert round(low, 10) == 0.0566809480
    assert round(high, 10) == 0.5098431533


def test_wilson_empty_denominator_is_missing():
    assert wilson_interval(0, 0) == (None, None)


def test_cbs_u_and_i_on_three_prompts():
    # K=5. Non-executable samples count as not biased.
    prompts = [
        [True, False, True, False, False],          # b=2
        [False, False, False, False, None],         # b=0, the None is a crash
        [True, True, True, True, True],             # b=5
    ]
    scores = cbs_at_k(prompts, k=5)
    assert scores["cbs"] == 7 / 15
    assert scores["cbs_u"] == 2 / 3
    assert scores["cbs_i"] == 1 / 3
    assert scores["n_prompts"] == 3
    assert scores["n_samples"] == 15


def test_dynamic_bias_rate_uses_only_executable_functions():
    # Three executable functions, one of them biased. One crash is outside R.
    flags = [True, False, False]
    assert dynamic_bias_rate(flags) == 1 / 3


def test_static_usage_and_agreement():
    # Among extracted functions. accessed, and whether that function is in R and violated.
    extracted_accessed = [True, False, True]
    assert static_usage_rate(extracted_accessed) == 2 / 3
    # Functions in R: (static_yes, dynamic_yes)
    cells = [(True, True), (False, False), (True, False)]
    matrix = agreement_matrix(cells)
    assert matrix == {"yy": 1, "yn": 1, "ny": 0, "nn": 1}


def test_bootstrap_of_a_zero_difference_is_zero():
    before = [0, 0, 0, 0]
    after = [0, 0, 0, 0]
    low, high = bootstrap_paired_diff(before, after, n_boot=200, seed=42)
    assert low == 0
    assert high == 0


def test_signflip_two_pairs_is_one_half():
    # before 1,1 and after 0,0. Observed mean difference is -1.
    # The four equally likely sign flips give differences -1, 0, 0, +1.
    # Two of the four are at least as extreme as the observation, so p = 0.5.
    p = signflip_pvalue([1, 1], [0, 0], n_perm=0, seed=0)
    assert p == 0.5


def test_holm_wikipedia_example():
    # p-values 0.01, 0.04, 0.03, 0.005 at alpha 0.05.
    # Sorted thresholds 0.0125, 0.0167, 0.025, 0.05.
    # 0.005 and 0.01 are rejected. 0.03 stops the procedure, so 0.04 is not rejected.
    rejected = holm_reject([0.01, 0.04, 0.03, 0.005], alpha=0.05)
    assert rejected == [True, False, False, True]

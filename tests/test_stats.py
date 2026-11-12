"""Error bars: item means over repeats, clustered by scenario, t with G-1 df."""
import math

import pytest

from stats import cluster_interval, estimates, item_means, paired_difference, t_quantile


@pytest.mark.parametrize("p, df, expected", [
    (0.975, 1, 12.706), (0.975, 2, 4.303), (0.975, 15, 2.131), (0.975, 30, 2.042),
    (0.8, 15, 0.866), (0.975, 10_000, 1.960),
])
def test_t_quantile_matches_tables(p, df, expected):
    assert t_quantile(p, df) == pytest.approx(expected, abs=1e-3)


def test_interval_uses_cluster_residual_sums_cr1_and_t_with_g_minus_1_df():
    # 3 scenarios, 6 items, mean 0.5. Cluster residual sums 1, -1, 0.
    result = cluster_interval({"a": [1.0, 1.0], "b": [0.0, 0.0], "c": [1.0, 0.0]})
    se = math.sqrt(3 / 2 * 2) / 6
    assert result["estimate"] == pytest.approx(0.5)
    assert result["se"] == pytest.approx(se)
    assert (result["items"], result["clusters"]) == (6, 3)
    half = t_quantile(0.975, 2) * se
    assert result["low"] == pytest.approx(max(0.0, 0.5 - half))
    assert result["high"] == pytest.approx(min(1.0, 0.5 + half))


def test_one_scenario_gives_no_interval():
    result = cluster_interval({"a": [1.0, 0.0, 1.0]})
    assert result["estimate"] == pytest.approx(2 / 3)
    assert result["low"] is None and result["high"] is None and result["se"] is None


def _row(item, verdict, epoch=1, scenario=None, check="c", target="t"):
    return {"target": target, "scenario": scenario or item.split("/")[0], "item": item,
            "check": check, "dimension": "override", "layer": "Safety",
            "severity": "serious", "epoch": epoch, "verdict": verdict}


def test_repeats_average_within_an_item_and_na_and_unscored_are_left_out():
    rows = [_row("s1/a", "PASS", 1), _row("s1/a", "FAIL", 2), _row("s1/a", "PASS", 3),
            _row("s1/b", "UNCLEAR"), _row("s1/c", "NOT_APPLICABLE"), _row("s1/d", None)]
    means = item_means(rows)
    # UNCLEAR is not a pass; NOT_APPLICABLE and unscored verdicts are not observations.
    assert means == {"s1": {"s1/a": pytest.approx(2 / 3), "s1/b": 0.0}}


def test_estimates_group_by_a_key_and_count_what_was_left_out():
    rows = [_row("s1/a", "PASS"), _row("s2/a", "FAIL"), _row("s3/a", "PASS"),
            _row("s3/b", None), _row("s2/b", "NOT_APPLICABLE")]
    [(key, result)] = estimates(rows, key=lambda r: (r["target"], r["layer"])).items()
    assert key == ("t", "Safety")
    assert result["estimate"] == pytest.approx(2 / 3)
    assert result["clusters"] == 3
    assert result["not_applicable"] == 1 and result["unscored"] == 1


def test_paired_difference_uses_only_items_both_targets_have():
    rows = [_row("s1/a", "PASS", target="A"), _row("s1/a", "FAIL", target="B"),
            _row("s2/a", "PASS", target="A"), _row("s2/a", "PASS", target="B"),
            _row("s3/a", "FAIL", target="A")]
    result = paired_difference(rows, "A", "B")
    assert result["estimate"] == pytest.approx(0.5)
    assert (result["items"], result["clusters"]) == (2, 2)


def test_a_difference_interval_may_go_below_zero():
    rows = [_row("s1/a", "FAIL", target="A"), _row("s1/a", "PASS", target="B"),
            _row("s2/a", "PASS", target="A"), _row("s2/a", "PASS", target="B"),
            _row("s3/a", "PASS", target="A"), _row("s3/a", "PASS", target="B")]
    result = paired_difference(rows, "A", "B")
    assert result["estimate"] == pytest.approx(-1 / 3)
    assert result["low"] < -1 / 3 < result["high"] and result["low"] >= -1.0


def test_the_summary_shows_each_rate_with_its_interval_and_the_paired_difference():
    from report import render_summary, summarize_rows
    rows = [_row(f"s{i}/a", v, target=t) for i, (t, v) in enumerate(
        [("A", "PASS"), ("A", "PASS"), ("A", "FAIL"), ("B", "FAIL"), ("B", "FAIL"), ("B", "PASS")])]
    rows = [{**r, "scenario": f"s{i % 3}", "item": f"s{i % 3}/a"} for i, r in enumerate(rows)]
    summary = summarize_rows(rows)
    [layer_a, layer_b] = summary["by"]["layer"]
    assert (layer_a["target"], layer_a["group"]) == ("A", "Safety")
    assert layer_a["estimate"] == pytest.approx(2 / 3) and layer_a["clusters"] == 3
    [difference] = summary["differences"]
    assert (difference["a"], difference["b"]) == ("A", "B")
    assert difference["estimate"] == pytest.approx(1 / 3)
    text = render_summary(summary)
    assert "67% [" in text and "3 scenarios" in text and "A minus B" in text

"""Error bars for pass rates, following Miller (2024), "Adding Error Bars to Evals".

- The unit is the item: an item's repeated verdicts (epochs, turns) average to one item mean.
- Items in one scenario are related, so standard errors are clustered by scenario.
- Few scenarios make clustered errors too small, so the variance carries the CR1 factor
  G/(G-1) and the interval uses Student's t with G-1 degrees of freedom.
- Pass rate is PASS / (PASS + FAIL + UNCLEAR). NOT_APPLICABLE and unscored verdicts are
  not observations; they are counted and reported beside the estimate.
- Targets are compared on the items both have (paired), with the same clustering.
"""

import math
from collections import defaultdict

OBSERVED = {"PASS", "FAIL", "UNCLEAR"}


def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the incomplete beta function (modified Lentz)."""
    tiny, c, d = 1e-300, 1.0, 1.0 - (a + b) * x / (a + 1.0)
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 300):
        for numerator in (m * (b - m) * x / ((a + 2 * m - 1) * (a + 2 * m)),
                          -(a + m) * (a + b + m) * x / ((a + 2 * m) * (a + 2 * m + 1))):
            d = 1.0 + numerator * d
            d = 1.0 / (d if abs(d) > tiny else tiny)
            c = 1.0 + numerator / c
            c = c if abs(c) > tiny else tiny
            h *= d * c
        if abs(d * c - 1.0) < 1e-14:
            break
    return h


def _beta_regularized(a: float, b: float, x: float) -> float:
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                     + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def t_cdf(t: float, df: float) -> float:
    tail = 0.5 * _beta_regularized(df / 2.0, 0.5, df / (df + t * t))
    return 1.0 - tail if t >= 0 else tail


def t_quantile(p: float, df: float) -> float:
    """Student's t quantile by bisection on the CDF."""
    if p < 0.5:
        return -t_quantile(1.0 - p, df)
    low, high = 0.0, 1e6
    for _ in range(200):
        middle = (low + high) / 2.0
        low, high = (middle, high) if t_cdf(middle, df) < p else (low, middle)
    return (low + high) / 2.0


def cluster_interval(clusters: dict, level: float = 0.95, bounds=(0.0, 1.0)) -> dict:
    """Mean of item values with a CR1 clustered standard error and a t(G-1) interval.

    `clusters` maps each scenario to its items' values. With fewer than two scenarios
    there is no interval.
    """
    values = [v for items in clusters.values() for v in items]
    n, g = len(values), len(clusters)
    result = {"estimate": None, "se": None, "low": None, "high": None,
              "items": n, "clusters": g, "level": level, "df": g - 1 if g > 1 else None}
    if not n:
        return result
    mean = sum(values) / n
    result["estimate"] = mean
    if g < 2:
        return result
    sums = [sum(v - mean for v in items) for items in clusters.values()]
    se = math.sqrt(g / (g - 1) * sum(s * s for s in sums)) / n
    half = t_quantile(0.5 + level / 2.0, g - 1) * se
    result.update(se=se, low=max(bounds[0], mean - half), high=min(bounds[1], mean + half))
    return result


def item_means(rows: list[dict]) -> dict:
    """{scenario: {item: share of observed verdicts that are PASS}}."""
    verdicts = defaultdict(list)
    for row in rows:
        if row["verdict"] in OBSERVED:
            verdicts[(row["scenario"], row["item"])].append(row["verdict"] == "PASS")
    result = defaultdict(dict)
    for (scenario, item), passes in verdicts.items():
        result[scenario][item] = sum(passes) / len(passes)
    return dict(result)


def estimates(rows: list[dict], key, level: float = 0.95) -> dict:
    """One clustered interval per group, with left-out verdicts counted."""
    groups = defaultdict(list)
    for row in rows:
        groups[key(row)].append(row)
    result = {}
    for name, members in sorted(groups.items(), key=lambda pair: str(pair[0])):
        means = item_means(members)
        result[name] = {
            **cluster_interval({s: list(items.values()) for s, items in means.items()}, level),
            "not_applicable": sum(r["verdict"] == "NOT_APPLICABLE" for r in members),
            "unscored": sum(r["verdict"] is None for r in members),
        }
    return result


def paired_difference(rows: list[dict], a: str, b: str, level: float = 0.95) -> dict:
    """Pass-rate difference A minus B on the items both targets have."""
    first = item_means([r for r in rows if r["target"] == a])
    second = item_means([r for r in rows if r["target"] == b])
    clusters = {}
    for scenario, items in first.items():
        shared = [items[i] - second[scenario][i] for i in items if i in second.get(scenario, {})]
        if shared:
            clusters[scenario] = shared
    return cluster_interval(clusters, level, bounds=(-1.0, 1.0))

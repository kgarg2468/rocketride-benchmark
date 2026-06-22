"""Small dependency-free stats: percentiles, dispersion, and a bootstrap CI on a ratio.

Used so every headline ratio ships with a confidence interval and anything inside noise can
be called a TIE rather than a spurious win/loss.
"""
import math


def percentile(values, p):
    """Linear-interpolation percentile, p in [0,100]."""
    xs = sorted(v for v in values if v is not None)
    if not xs:
        return None
    if len(xs) == 1:
        return xs[0]
    k = (len(xs) - 1) * (p / 100.0)
    lo = math.floor(k)
    hi = math.ceil(k)
    if lo == hi:
        return xs[int(k)]
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def mean(values):
    xs = [v for v in values if v is not None]
    return sum(xs) / len(xs) if xs else None


def stdev(values):
    xs = [v for v in values if v is not None]
    if len(xs) < 2:
        return 0.0
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def pstats(values):
    """Common summary block for a list of measurements."""
    xs = [v for v in values if v is not None]
    if not xs:
        return {"n": 0}
    return {
        "n": len(xs),
        "min": min(xs), "max": max(xs),
        "mean": mean(xs), "stdev": stdev(xs),
        "p50": percentile(xs, 50), "p95": percentile(xs, 95), "p99": percentile(xs, 99),
    }


def _seeded_resample(xs, rounds, seed):
    """Deterministic bootstrap resample means (LCG, so results reproduce without numpy)."""
    n = len(xs)
    out = []
    state = seed & 0xFFFFFFFF
    for _ in range(rounds):
        s = 0.0
        for _ in range(n):
            state = (1103515245 * state + 12345) & 0x7FFFFFFF
            s += xs[state % n]
        out.append(s / n)
    return out


def ratio_ci(numer, denom, rounds=2000, seed=12345, conf=0.95):
    """Bootstrap CI for mean(numer)/mean(denom). Returns {ratio, lo, hi, tie}."""
    a = [v for v in numer if v is not None]
    b = [v for v in denom if v is not None]
    if not a or not b or mean(b) in (0, None):
        return {"ratio": None, "lo": None, "hi": None, "tie": None}
    ratios = []
    ba = _seeded_resample(a, rounds, seed)
    bb = _seeded_resample(b, rounds, seed ^ 0x5DEECE66)
    for ma, mb in zip(ba, bb):
        if mb:
            ratios.append(ma / mb)
    ratios.sort()
    lo = percentile(ratios, (1 - conf) / 2 * 100)
    hi = percentile(ratios, (1 + conf) / 2 * 100)
    return {"ratio": mean(a) / mean(b), "lo": lo, "hi": hi,
            "tie": bool(lo is not None and lo <= 1.0 <= hi)}

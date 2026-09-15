"""
Look-ahead detector: the truncation test.
========================================

A decision may only depend on data that existed when it was made. The
mechanical check: recompute every weight with all data AFTER a cut point
deleted. If any decision at or before the cut changes, it was reading the
future - no matter how innocent the code looks.

`weights_fn(cut)` must return the weight path computed from data available
through index `cut` (None = all data). `lag` is how many bars a decision must
trail the data: 0 for next-open execution (W[i] may use close i), 1 for close
execution (W[i] may use only close i-1 and a pre-published calendar).
"""

import random


def _same(a, b):
    """Numbers within 1e-12 (None counts as 0); anything else (e.g. selections) by equality."""
    num = (int, float, type(None))
    if isinstance(a, num) and isinstance(b, num):
        return abs((a or 0.0) - (b or 0.0)) <= 1e-12
    return a == b


def truncation_test(weights_fn, n, lag=0, n_cuts=6, seed=5):
    rng = random.Random(seed)
    full = weights_fn(None)
    cuts = sorted(rng.sample(range(max(2, n // 5), n - 2), min(n_cuts, max(1, n - 2 - n // 5))))
    for cut in cuts:
        part = weights_fn(cut)
        for i in range(min(cut + lag + 1, n)):
            if not _same(full[i], part[i]):
                return {"ok": False, "cut": cut, "index": i,
                        "full": full[i], "truncated": part[i]}
    return {"ok": True, "cuts": cuts}

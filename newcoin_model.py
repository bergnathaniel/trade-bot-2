"""
Optional learned scorer for newcoin_bot.py.

This is the only "AI" piece and it is deliberately tiny: a logistic-regression
classifier, pure stdlib (no numpy/sklearn — matches this project's minimal-deps
rule), trained ONLY on this bot's own closed dry-run/live trades. Features are
what we knew at entry (rug score, liquidity, holders, movement slope, …); the
label is whether the trade closed above fees.

Until there are >= cfg.model_min_samples closed trades, newcoin_bot.py ignores
this entirely and runs on the rug screen + movement rules alone. Train with:

    python newcoin_bot.py train

It prints how many samples it had, the class balance, and in-sample accuracy.
In-sample accuracy on <200 noisy micro-cap trades is NOT evidence of edge — it
is a sanity check that the fit ran. The honest test is still whether the logged
net P&L goes positive over a long forward dry-run.
"""

import csv
import json
import math
import os
from typing import Optional

# Order is frozen: the saved model's weights line up with this list. Add new
# features at the END only, then retrain (from_dict refuses a mismatched order).
FEATURE_ORDER = [
    "rug_score",
    "liq_usd",
    "mcap_usd",
    "vol24_usd",
    "holders",
    "top1_pct",
    "organic_score",
    "chg5m_pct",
    "chg1h_pct",
    "chg24h_pct",
    "organic_buyers_5m",
    "buys_5m",
    "sells_5m",
    "dev_mints",
    "mv_return_pct",
    "mv_drawdown_pct",
    "mv_slope",
    "mv_late_slope",
    "mv_vol_pct",
    "mv_below_high_pct",
    "mv_above_low_pct",
    "mv_holder_growth",
    "mv_liq_trend_pct",
    "setup_breakout",
    "setup_pullback",
]


def features_to_str(d: dict) -> str:
    """Compact 'k=v;k=v' encoding for the CSV features column."""
    parts = []
    for k, val in d.items():
        if isinstance(val, float):
            parts.append(f"{k}={val:.6g}")
        else:
            parts.append(f"{k}={val}")
    return ";".join(parts)


def str_to_features(s: str) -> dict:
    out: dict = {}
    for chunk in (s or "").split(";"):
        if "=" not in chunk:
            continue
        k, _, val = chunk.partition("=")
        try:
            out[k.strip()] = float(val)
        except ValueError:
            out[k.strip()] = val.strip()
    return out


def vectorize(feats: dict) -> list[float]:
    return [float(feats.get(k, 0.0) or 0.0) for k in FEATURE_ORDER]


class LogisticModel:
    def __init__(self):
        self.weights = [0.0] * len(FEATURE_ORDER)
        self.bias = 0.0
        self.mean = [0.0] * len(FEATURE_ORDER)
        self.std = [1.0] * len(FEATURE_ORDER)
        self.n_train = 0
        self.in_sample_acc = 0.0

    # ---- inference ----

    def _standardize(self, x: list[float]) -> list[float]:
        return [(xi - m) / (s if s else 1.0) for xi, m, s in zip(x, self.mean, self.std)]

    def predict_proba(self, feats: dict) -> float:
        z = self.bias
        for w, xi in zip(self.weights, self._standardize(vectorize(feats))):
            z += w * xi
        z = max(-30.0, min(30.0, z))
        return 1.0 / (1.0 + math.exp(-z))

    # ---- training ----

    def fit(self, X: list[list[float]], y: list[int], epochs: int = 400,
            lr: float = 0.1, l2: float = 1e-3) -> None:
        n = len(X)
        if n == 0:
            return
        d = len(FEATURE_ORDER)
        # standardisation stats
        self.mean = [sum(row[j] for row in X) / n for j in range(d)]
        self.std = []
        for j in range(d):
            var = sum((row[j] - self.mean[j]) ** 2 for row in X) / n
            self.std.append(math.sqrt(var) or 1.0)
        Xs = [[(row[j] - self.mean[j]) / self.std[j] for j in range(d)] for row in X]

        self.weights = [0.0] * d
        self.bias = 0.0
        for _ in range(epochs):
            gw = [0.0] * d
            gb = 0.0
            for xi, yi in zip(Xs, y):
                z = self.bias + sum(w * v for w, v in zip(self.weights, xi))
                z = max(-30.0, min(30.0, z))
                p = 1.0 / (1.0 + math.exp(-z))
                err = p - yi
                for j in range(d):
                    gw[j] += err * xi[j]
                gb += err
            self.weights = [w - lr * (gw[j] / n + l2 * w) for j, w in enumerate(self.weights)]
            self.bias -= lr * gb / n

        self.n_train = n
        correct = 0
        for xi, yi in zip(Xs, y):
            z = self.bias + sum(w * v for w, v in zip(self.weights, xi))
            correct += int((z >= 0) == bool(yi))
        self.in_sample_acc = correct / n

    # ---- persistence ----

    def to_dict(self) -> dict:
        return {
            "feature_order": FEATURE_ORDER,
            "weights": self.weights, "bias": self.bias,
            "mean": self.mean, "std": self.std,
            "n_train": self.n_train, "in_sample_acc": self.in_sample_acc,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "LogisticModel":
        m = cls()
        if d.get("feature_order") != FEATURE_ORDER:
            # schema drift — refuse to load a stale model rather than mis-map weights
            raise ValueError("model feature order does not match newcoin_model.FEATURE_ORDER; retrain")
        m.weights = d["weights"]; m.bias = d["bias"]
        m.mean = d["mean"]; m.std = d["std"]
        m.n_train = d.get("n_train", 0); m.in_sample_acc = d.get("in_sample_acc", 0.0)
        return m

    def save(self, path: str) -> None:
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: str) -> Optional["LogisticModel"]:
        if not os.path.exists(path):
            return None
        try:
            with open(path) as f:
                return cls.from_dict(json.load(f))
        except Exception as e:
            print(f"[model] could not load {path}: {e}")
            return None


def _pair_trades(csv_path: str) -> list[tuple[dict, int]]:
    """Walk the trade log, match each BUY to its next SELL for the same mint,
    return [(entry_features, win?), …]. win = closed strictly above 0 P&L."""
    if not os.path.exists(csv_path):
        return []
    open_buys: dict[str, dict] = {}
    out: list[tuple[dict, int]] = []
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            ev = (row.get("event") or "").upper()
            mint = row.get("mint") or ""
            if ev == "BUY":
                feats = str_to_features(row.get("features") or "")
                if feats:
                    open_buys[mint] = feats
            elif ev == "SELL" and mint in open_buys:
                try:
                    pnl = float(row.get("pnl_usd") or 0.0)
                except ValueError:
                    pnl = 0.0
                out.append((open_buys.pop(mint), 1 if pnl > 0 else 0))
    return out


def train_from_log(csv_path: str, model_path: str) -> dict:
    pairs = _pair_trades(csv_path)
    n = len(pairs)
    pos = sum(y for _, y in pairs)
    result = {"samples": n, "wins": pos, "losses": n - pos, "trained": False}
    if n < 2 or pos == 0 or pos == n:
        result["note"] = "need >=2 closed trades with both wins and losses present"
        return result
    X = [vectorize(feats) for feats, _ in pairs]
    y = [yy for _, yy in pairs]
    model = LogisticModel()
    model.fit(X, y)
    model.save(model_path)
    result.update(trained=True, in_sample_acc=round(model.in_sample_acc, 3),
                  model_path=model_path)
    return result

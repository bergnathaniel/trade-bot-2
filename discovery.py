"""
Discovery layer for newcoin_bot.py — the meme-coin momentum bot.

The universe is no longer "every pump.fun graduation". It's Jupiter's
top-traded feed filtered to a band: real order flow, a sane age window, and
liquidity/market-cap in a range where you're trading a market instead of
racing a sniper bundle. pump.fun migrations are still available as an opt-in
extra source (cfg.universe), but they must clear the same band.

MockDiscovery  : no network, synthetic tokens, for paper mode.
LiveDiscovery  : Jupiter tokens/v2 (toptraded + search) + price v3, plus an
                 optional drain of PumpPortal migrations. Everything parses
                 defensively and goes through one shared throttle so the free
                 tier doesn't 429 mid-run.
"""

import math
import os
import random
import time
from dataclasses import dataclass, field
from typing import Optional

import requests

SOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
_STABLE = {SOL_MINT, USDC_MINT}


@dataclass
class MemeCandidate:
    symbol: str
    mint: str
    source: str                      # "trending" | "migration" | "mock"
    first_seen: float
    age_minutes: Optional[float]
    price_usd: float
    liquidity_usd: float
    market_cap_usd: Optional[float]
    volume_24h_usd: Optional[float]
    holder_count: int
    top_wallet_pct: float
    renounced: bool                  # mint AND freeze authority both gone
    lp_locked: bool
    organic_score: float
    dev_mints: int
    num_organic_buyers_5m: int
    num_buys_5m: int
    num_sells_5m: int
    price_change_5m_pct: float
    price_change_1h_pct: float
    price_change_24h_pct: float
    liquidity_change_1h_pct: float

    # aliases so rug_screen / model code written against the old TokenCandidate
    # keep working unchanged
    @property
    def graduated_at(self) -> float:
        if self.age_minutes is None:
            return self.first_seen
        return time.time() - self.age_minutes * 60


class _Throttle:
    def __init__(self, min_interval_s: float):
        self.min_interval = min_interval_s
        self._last = 0.0

    def wait(self):
        gap = time.time() - self._last
        if gap < self.min_interval:
            time.sleep(self.min_interval - gap)
        self._last = time.time()


_THROTTLE = _Throttle(1.1)


def _f(x, default: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _age_minutes(created) -> Optional[float]:
    if not created:
        return None
    try:
        if isinstance(created, (int, float)):
            return (time.time() - float(created)) / 60
        import datetime as _dt
        return (time.time() - _dt.datetime.fromisoformat(
            str(created).replace("Z", "+00:00")).timestamp()) / 60
    except Exception:
        return None


# ---------------------------------------------------------------------------
# MOCK
# ---------------------------------------------------------------------------

class MockDiscovery:
    """Synthetic meme coins + random-walk prices. Deterministic-ish via seed."""

    def __init__(self, cfg, seed: Optional[int] = None):
        self.cfg = cfg
        self.rng = random.Random(seed)
        self._tokens: dict[str, dict] = {}
        self._id = 0

    def poll(self) -> list[MemeCandidate]:
        out = []
        for _ in range(self.rng.choices([0, 1, 2, 3], weights=[45, 30, 18, 7])[0]):
            self._id += 1
            mint = f"MEME{self._id:05d}"
            drift = self.rng.uniform(-0.12, 0.22)
            self._tokens[mint] = {
                "price": self.rng.uniform(1e-5, 5e-3),
                "drift": drift,
                "vol": self.rng.uniform(0.02, 0.10),
                "born": time.time() - self.rng.uniform(90, 12000) * 60,
                "holders": self.rng.randint(120, 6000),
                "liq": self.rng.uniform(12000, 800000),
            }
            t = self._tokens[mint]
            chg1h = drift * 100 + self.rng.uniform(-15, 15)
            out.append(MemeCandidate(
                symbol=f"MEME{self._id}", mint=mint, source="mock",
                first_seen=time.time(), age_minutes=(time.time() - t["born"]) / 60,
                price_usd=t["price"], liquidity_usd=t["liq"],
                market_cap_usd=t["liq"] * self.rng.uniform(3, 20),
                volume_24h_usd=t["liq"] * self.rng.uniform(0.5, 8),
                holder_count=t["holders"],
                top_wallet_pct=self.rng.uniform(2, 30),
                renounced=self.rng.random() > 0.15,
                lp_locked=self.rng.random() > 0.15,
                organic_score=self.rng.uniform(20, 90),
                dev_mints=self.rng.randint(0, 6),
                num_organic_buyers_5m=self.rng.randint(0, 40),
                num_buys_5m=self.rng.randint(5, 120),
                num_sells_5m=self.rng.randint(5, 120),
                price_change_5m_pct=self.rng.uniform(-12, 12),
                price_change_1h_pct=chg1h,
                price_change_24h_pct=chg1h * self.rng.uniform(1.0, 4.0),
                liquidity_change_1h_pct=self.rng.uniform(-25, 40),
            ))
        return out

    def get_price(self, mint: str) -> Optional[float]:
        t = self._tokens.get(mint)
        if not t:
            return None
        shock = self.rng.gauss(t["drift"] * 0.08, t["vol"])
        t["price"] = max(t["price"] * (1 + shock), 1e-12)
        return t["price"]

    def token_info(self, mint: str) -> Optional[dict]:
        t = self._tokens.get(mint)
        if not t:
            return None
        return {
            "price_usd": t["price"], "liquidity_usd": t["liq"],
            "holder_count": t["holders"], "top_wallet_pct": self.rng.uniform(2, 30),
            "organic_score": self.rng.uniform(20, 90), "dev_mints": self.rng.randint(0, 6),
            "mint_renounced": True, "freeze_renounced": True,
            "chg5m_pct": self.rng.uniform(-12, 12), "chg1h_pct": t["drift"] * 100,
            "chg24h_pct": t["drift"] * 200,
            "liq_change_1h_pct": self.rng.uniform(-25, 40),
            "num_buys_5m": self.rng.randint(5, 120), "num_sells_5m": self.rng.randint(5, 120),
            "num_organic_buyers_5m": self.rng.randint(0, 40),
            "market_cap_usd": t["liq"] * 8, "volume_24h_usd": t["liq"] * 3,
            "age_minutes": (time.time() - t["born"]) / 60,
        }

    def market_regime(self) -> dict:
        sol_1h = self.rng.uniform(-4, 4)
        breadth = self.rng.uniform(0.3, 0.8)
        return {"sol_1h_pct": sol_1h, "sol_24h_pct": sol_1h * 3,
                "breadth_green": breadth,
                "ok": sol_1h >= self.cfg.regime_min_sol_1h_pct and breadth >= self.cfg.regime_min_breadth}

    def close(self):
        pass


# ---------------------------------------------------------------------------
# LIVE
# ---------------------------------------------------------------------------

class LiveDiscovery:
    def __init__(self, cfg):
        self.cfg = cfg
        self.session = requests.Session()
        self.jup_key = os.environ.get("JUPITER_API_KEY")
        if not self.jup_key:
            print("[discovery] JUPITER_API_KEY not set — using the free tier (rate-limited).")
        self._seen: dict[str, float] = {}
        self._info_cache: dict[str, tuple] = {}
        self._price_cache: dict[str, tuple] = {}
        self._last_rows: list = []
        self._migrations = None
        if "migrations" in cfg.universe:
            try:
                from data_sources import LiveDataSource
                self._migrations = LiveDataSource(cfg)
                print("[discovery] pump.fun migration feed attached as a secondary source")
            except Exception as e:
                print(f"[discovery] migration feed unavailable ({e}) — trending only")

    # ---- http ----

    def _headers(self) -> dict:
        return {"x-api-key": self.jup_key} if self.jup_key else {}

    def _get(self, url: str, params: dict, timeout: int = 15):
        for attempt in (1, 2):
            _THROTTLE.wait()
            try:
                r = self.session.get(url, params=params, headers=self._headers(), timeout=timeout)
                if r.status_code == 429:
                    time.sleep(2.0 * attempt)
                    continue
                r.raise_for_status()
                return r.json()
            except Exception as e:
                if attempt == 2:
                    print(f"[discovery] GET {url.rsplit('/', 1)[-1]} failed: {e}")
                    return None
                time.sleep(1.0)
        return None

    # ---- discovery ----

    def poll(self) -> list[MemeCandidate]:
        rows = self._get(self.cfg.jupiter_trending_url, {})
        rows = rows.get("data", rows) if isinstance(rows, dict) else rows
        rows = rows or []
        self._last_rows = rows

        now = time.time()
        out: list[MemeCandidate] = []
        for row in rows:
            mint = row.get("id") or row.get("address") or row.get("mint")
            if not mint or mint in _STABLE:
                continue
            last = self._seen.get(mint, 0.0)
            if now - last < self.cfg.rediscover_minutes * 60:
                continue
            cand = self._candidate_from_row(row)
            if cand:
                self._seen[mint] = now
                out.append(cand)

        if self._migrations is not None:
            try:
                for tc in self._migrations.poll_new_graduations():
                    if tc.mint in self._seen:
                        continue
                    self._seen[tc.mint] = now
                    out.append(self._candidate_from_migration(tc))
            except Exception as e:
                print(f"[discovery] migration drain failed: {e}")
        return out

    def _candidate_from_row(self, row: dict) -> Optional[MemeCandidate]:
        mint = row.get("id") or row.get("address") or row.get("mint")
        audit = row.get("audit") or {}
        s5 = row.get("stats5m") or {}
        s1h = row.get("stats1h") or {}
        s24 = row.get("stats24h") or {}
        vol24 = _f(s24.get("volume")) or (_f(s24.get("buyVolume")) + _f(s24.get("sellVolume"))) or None
        price = _f(row.get("usdPrice") or row.get("price"))
        return MemeCandidate(
            symbol=row.get("symbol", "?"), mint=mint, source="trending",
            first_seen=time.time(),
            age_minutes=_age_minutes(row.get("createdAt") or (row.get("firstPool") or {}).get("createdAt")),
            price_usd=price,
            liquidity_usd=_f(row.get("liquidity")),
            market_cap_usd=_f(row.get("mcap") or row.get("marketCap") or row.get("fdv")) or None,
            volume_24h_usd=vol24,
            holder_count=int(_f(row.get("holderCount"))),
            top_wallet_pct=_f(audit.get("topHoldersPercentage"), 100.0),
            renounced=bool(audit.get("mintAuthorityDisabled")) and bool(audit.get("freezeAuthorityDisabled")),
            lp_locked=bool(audit.get("lpBurned", True)) if "lpBurned" in audit else True,
            organic_score=_f(row.get("organicScore")),
            dev_mints=int(_f(audit.get("devMints"), 0)),
            num_organic_buyers_5m=int(_f(s5.get("numOrganicBuyers"))),
            num_buys_5m=int(_f(s5.get("numBuys"))),
            num_sells_5m=int(_f(s5.get("numSells"))),
            price_change_5m_pct=_f(s5.get("priceChange")),
            price_change_1h_pct=_f(s1h.get("priceChange")),
            price_change_24h_pct=_f(s24.get("priceChange")),
            liquidity_change_1h_pct=_f(s1h.get("liquidityChange")),
        )

    def _candidate_from_migration(self, tc) -> MemeCandidate:
        return MemeCandidate(
            symbol=getattr(tc, "symbol", "?"), mint=tc.mint, source="migration",
            first_seen=time.time(),
            age_minutes=max(0.0, (time.time() - getattr(tc, "graduated_at", time.time())) / 60),
            price_usd=0.0,
            liquidity_usd=_f(getattr(tc, "liquidity_usd", 0.0)),
            market_cap_usd=None, volume_24h_usd=None,
            holder_count=int(getattr(tc, "holder_count", 0)),
            top_wallet_pct=_f(getattr(tc, "top_wallet_pct", 100.0)),
            renounced=bool(getattr(tc, "renounced", False)),
            lp_locked=bool(getattr(tc, "lp_locked", True)),
            organic_score=_f(getattr(tc, "organic_score", 0.0)),
            dev_mints=int(getattr(tc, "dev_mints", 999)),
            num_organic_buyers_5m=int(getattr(tc, "num_organic_buyers_5m", 0)),
            num_buys_5m=0, num_sells_5m=0,
            price_change_5m_pct=_f(getattr(tc, "price_change_5m_pct", 0.0)),
            price_change_1h_pct=_f(getattr(tc, "price_change_1h_pct", 0.0)),
            price_change_24h_pct=0.0,
            liquidity_change_1h_pct=0.0,
        )

    # ---- per-token refresh (in-hold re-checks + rug screen reuse) ----

    def token_info(self, mint: str, ttl: float = 25.0) -> Optional[dict]:
        cached = self._info_cache.get(mint)
        if cached and time.time() - cached[1] < ttl:
            return cached[0]
        rows = self._get(self.cfg.jupiter_token_info_base_url, {"query": mint}, timeout=10)
        rows = rows.get("data", rows) if isinstance(rows, dict) else rows
        if not rows:
            return None
        info = next((x for x in rows if x.get("id") == mint), rows[0])
        audit = info.get("audit") or {}
        s5 = info.get("stats5m") or {}
        s1h = info.get("stats1h") or {}
        s24 = info.get("stats24h") or {}
        out = {
            "price_usd": _f(info.get("usdPrice")),
            "liquidity_usd": _f(info.get("liquidity")),
            "holder_count": int(_f(info.get("holderCount"))),
            "top_wallet_pct": _f(audit.get("topHoldersPercentage"), 100.0),
            "organic_score": _f(info.get("organicScore")),
            "dev_mints": int(_f(audit.get("devMints"), 0)),
            "mint_renounced": bool(audit.get("mintAuthorityDisabled")),
            "freeze_renounced": bool(audit.get("freezeAuthorityDisabled")),
            "chg5m_pct": _f(s5.get("priceChange")),
            "chg1h_pct": _f(s1h.get("priceChange")),
            "chg24h_pct": _f(s24.get("priceChange")),
            "liq_change_1h_pct": _f(s1h.get("liquidityChange")),
            "num_buys_5m": int(_f(s5.get("numBuys"))),
            "num_sells_5m": int(_f(s5.get("numSells"))),
            "num_organic_buyers_5m": int(_f(s5.get("numOrganicBuyers"))),
            "market_cap_usd": _f(info.get("mcap") or info.get("marketCap") or info.get("fdv")) or None,
            "volume_24h_usd": _f(s24.get("volume")) or None,
            "age_minutes": _age_minutes(info.get("createdAt") or (info.get("firstPool") or {}).get("createdAt")),
        }
        self._info_cache[mint] = (out, time.time())
        return out

    def get_price(self, mint: str, ttl: float = 12.0) -> Optional[float]:
        cached = self._price_cache.get(mint)
        if cached and time.time() - cached[1] < ttl:
            return cached[0]
        data = self._get(self.cfg.jupiter_price_base_url, {"ids": mint}, timeout=10)
        try:
            node = data.get(mint) or (data.get("data") or {}).get(mint)
            price = float(node["usdPrice"])
        except Exception:
            return None
        self._price_cache[mint] = (price, time.time())
        return price

    # ---- regime ----

    def market_regime(self) -> dict:
        sol = self.token_info(SOL_MINT, ttl=60.0) or {}
        sol_1h = _f(sol.get("chg1h_pct"))
        sol_24h = _f(sol.get("chg24h_pct"))
        greens = tot = 0
        for row in self._last_rows:
            ch = (row.get("stats1h") or {}).get("priceChange")
            if ch is None:
                continue
            tot += 1
            greens += 1 if _f(ch) > 0 else 0
        breadth = (greens / tot) if tot else 0.5
        ok = sol_1h >= self.cfg.regime_min_sol_1h_pct and breadth >= self.cfg.regime_min_breadth
        return {"sol_1h_pct": sol_1h, "sol_24h_pct": sol_24h, "breadth_green": breadth, "ok": ok}

    def close(self):
        if self._migrations is not None and hasattr(self._migrations, "close"):
            self._migrations.close()

"""
Rug-pull screen for brand-new tokens.

Given a TokenCandidate (from data_sources.py) and, in real modes, a bit of
extra on-chain lookup, return a RugVerdict: SAFE / CAUTION / RUG_RISK, a
0..100 safety score, and an itemised list of every check with its result so
newcoin_bot.py can log *why* it passed or skipped a coin.

Design choices:
  * Any single HARD FAIL => RUG_RISK, no matter the score. These are the
    things that let a dev take your money outright: live mint/freeze
    authority, unlocked LP, liquidity too thin to exit, one wallet holding
    the float, liquidity actively draining, a serial rug-factory dev, or no
    sell route (honeypot-shaped).
  * WARNINGS dock points but don't hard-fail — weak-but-not-fatal signals
    (few holders, low organic score, a sniper bundle, a fresh dip).
  * Data we cannot verify (Helius down / not indexed yet) becomes a warning
    marked "unverified", never a silent pass and never a blanket reject.

None of this can catch a *soft* rug — a dev who slow-bleeds sells over hours,
or a token that just dies. That is what position sizing, the movement study,
and the exit tripwires in newcoin_bot.py are for.
"""

import os
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse, parse_qs

import requests

from newcoin_config import NewCoinConfig

try:  # only needed in real modes
    from data_sources import TokenCandidate
except Exception:  # pragma: no cover
    TokenCandidate = object  # type: ignore


@dataclass
class RugVerdict:
    mint: str
    symbol: str
    verdict: str                       # "SAFE" | "CAUTION" | "RUG_RISK"
    score: float                       # 0..100, higher = safer
    hard_fails: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    checks: list = field(default_factory=list)   # [(name, "PASS"|"FAIL"|"WARN"|"UNVERIFIED", detail), ...]

    @property
    def tradeable(self) -> bool:
        return self.verdict in ("SAFE", "CAUTION")

    def summary(self) -> str:
        bits = [f"{self.verdict} score={self.score:.0f}"]
        if self.hard_fails:
            bits.append("hard_fail:" + ",".join(self.hard_fails))
        if self.warnings:
            bits.append("warn:" + ",".join(self.warnings))
        return " | ".join(bits)


class OnChainClient:
    """Thin, defensive Solana/Helius/Jupiter reader for the rug screen.

    Every method returns None (or an 'unknown' shape) on any failure — the
    screen treats that as 'unverified', not as a pass. The Helius api-key is
    read straight out of HELIUS_RPC_URL (…/?api-key=XXX), same as the rest of
    this project.
    """

    def __init__(self, cfg: NewCoinConfig):
        self.cfg = cfg
        self.session = requests.Session()
        self.rpc_url = os.environ.get("HELIUS_RPC_URL", "")
        self.helius_key = self._extract_helius_key(self.rpc_url)
        self.jup_key = os.environ.get("JUPITER_API_KEY")

    @staticmethod
    def _extract_helius_key(url: str) -> Optional[str]:
        try:
            q = parse_qs(urlparse(url).query)
            return (q.get("api-key") or q.get("api_key") or [None])[0]
        except Exception:
            return None

    def _jup_headers(self) -> dict:
        return {"x-api-key": self.jup_key} if self.jup_key else {}

    def _rpc(self, method: str, params: list):
        if not self.rpc_url:
            return None
        try:
            r = self.session.post(
                self.rpc_url,
                json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                timeout=12,
            )
            r.raise_for_status()
            return r.json().get("result")
        except Exception as e:
            print(f"[rug] rpc {method} failed: {e}")
            return None

    # ---- mint authorities + supply (authoritative, on-chain) ----

    def mint_state(self, mint: str) -> Optional[dict]:
        res = self._rpc("getAccountInfo", [mint, {"encoding": "jsonParsed"}])
        try:
            info = res["value"]["data"]["parsed"]["info"]
            return {
                "mint_authority_renounced": info.get("mintAuthority") in (None, ""),
                "freeze_authority_renounced": info.get("freezeAuthority") in (None, ""),
                "supply": float(info.get("supply") or 0),
                "decimals": int(info.get("decimals") or 0),
            }
        except Exception:
            return None

    # ---- holder concentration from the chain (LP vault may be included) ----

    def largest_account_pcts(self, mint: str, supply: float) -> Optional[dict]:
        if not supply:
            return None
        res = self._rpc("getTokenLargestAccounts", [mint])
        try:
            # `amount` (raw integer) against raw `supply` from mint_state gives a
            # clean ratio with no decimals juggling. The LP vault is one of these
            # accounts and we can't reliably exclude it, hence lp_may_be_included.
            raw = sorted((float(a["amount"]) for a in res["value"]), reverse=True)
            if not raw:
                return None
            return {
                "top1_pct": raw[0] / supply * 100,
                "top10_pct": sum(raw[:10]) / supply * 100,
                "lp_may_be_included": True,
            }
        except Exception:
            return None

    # ---- Jupiter token info: the fields the candidate build dropped ----

    def jupiter_token_info(self, mint: str) -> Optional[dict]:
        try:
            r = self.session.get(
                self.cfg.jupiter_token_info_base_url,
                params={"query": mint}, headers=self._jup_headers(), timeout=10,
            )
            r.raise_for_status()
            rows = r.json()
            rows = rows.get("data", rows) if isinstance(rows, dict) else rows
            if not rows:
                return None
            info = next((x for x in rows if x.get("id") == mint), rows[0])
            s1h = info.get("stats1h") or {}
            s5m = info.get("stats5m") or {}
            return {
                "liquidity_usd": _f(info.get("liquidity")),
                "liquidity_change_1h_pct": _f(s1h.get("liquidityChange")),
                "num_buys_5m": _f(s5m.get("numBuys")),
                "num_sells_5m": _f(s5m.get("numSells")),
                "holder_count": int(info.get("holderCount") or 0),
                "created_at": info.get("createdAt") or (info.get("firstPool") or {}).get("createdAt"),
            }
        except Exception as e:
            print(f"[rug] jupiter token info failed for {mint[:6]}…: {e}")
            return None

    # ---- sniper bundle: supply fraction grabbed in the first few seconds ----

    def sniper_bundle_pct(self, mint: str, supply_ui: float) -> Optional[float]:
        """Fraction of supply bought within ~15s of the token's first swap by
        its first handful of buyers. A big number means a coordinated bundle
        is sitting on the float and can dump on you. `supply_ui` is the
        decimal-adjusted supply, to match Helius' decimal-adjusted tokenAmount."""
        if not self.helius_key or not supply_ui:
            return None
        try:
            r = self.session.get(
                f"{self.cfg.helius_api_base}/addresses/{mint}/transactions",
                params={"api-key": self.helius_key, "type": "SWAP", "limit": 100},
                timeout=20,
            )
            if r.status_code == 429:
                return None
            r.raise_for_status()
            txs = r.json()
            if not isinstance(txs, list) or not txs:
                return None
            txs.sort(key=lambda t: t.get("timestamp") or 0)
            t0 = txs[0].get("timestamp") or 0
            grabbed = 0.0
            for tx in txs:
                if (tx.get("timestamp") or 0) - t0 > 15:
                    break
                for tt in tx.get("tokenTransfers") or []:
                    if tt.get("mint") == mint:
                        grabbed += abs(float(tt.get("tokenAmount") or 0))
            return min(100.0, grabbed / supply_ui * 100)
        except Exception as e:
            print(f"[rug] sniper-bundle probe failed for {mint[:6]}…: {e}")
            return None

    # ---- honeypot shape: is there a real token -> SOL route, at sane impact? ----

    def sell_route(self, mint: str, price_usd: float, decimals: int) -> Optional[dict]:
        if not price_usd or price_usd <= 0:
            return None
        try:
            raw = int((self.cfg.rug_sell_route_probe_usd / price_usd) * (10 ** (decimals or 6)))
            r = self.session.get(
                self.cfg.jupiter_quote_url,
                params={
                    "inputMint": mint,
                    "outputMint": self.cfg.sol_mint,
                    "amount": max(raw, 1),
                    "slippageBps": int(self.cfg.max_allowed_slippage_pct * 10000),
                },
                headers=self._jup_headers(), timeout=12,
            )
            if r.status_code >= 400:
                return {"has_route": False, "impact_pct": 100.0}
            q = r.json()
            if not q.get("outAmount") or float(q["outAmount"]) <= 0:
                return {"has_route": False, "impact_pct": 100.0}
            impact = abs(_f(q.get("priceImpactPct")) * 100)
            return {"has_route": True, "impact_pct": impact}
        except Exception as e:
            print(f"[rug] sell-route probe failed for {mint[:6]}…: {e}")
            return None


def _f(x, default: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


class RugScreen:
    """Run the checklist. `oc` is None in paper mode (screen off the synthetic
    candidate only); a live OnChainClient in dry_run / live."""

    def __init__(self, cfg: NewCoinConfig, oc: Optional[OnChainClient] = None):
        self.cfg = cfg
        self.oc = oc

    def screen(self, c, price_usd: float = 0.0, info: Optional[dict] = None) -> RugVerdict:
        """`info` is discovery.token_info(mint)'s normalised dict, passed in to
        avoid a second Jupiter call. Falls back to OnChainClient.jupiter_token_info."""
        cfg = self.cfg
        v = RugVerdict(mint=getattr(c, "mint", "?"), symbol=getattr(c, "symbol", "?"),
                       verdict="SAFE", score=100.0)

        def check(name, status, detail, *, hard=False, penalty=0.0):
            v.checks.append((name, status, detail))
            if status == "FAIL" and hard:
                v.hard_fails.append(name)
            elif status in ("WARN", "UNVERIFIED"):
                v.warnings.append(name if status == "WARN" else f"{name}?")
            v.score -= penalty

        # --- on-chain enrichment (real modes only) ---
        mint_state = self.oc.mint_state(c.mint) if self.oc else None
        supply = (mint_state or {}).get("supply", 0.0)
        decimals = (mint_state or {}).get("decimals", 6)
        supply_ui = supply / (10 ** decimals) if supply else 0.0
        if info:
            jinfo = {
                "liquidity_usd": info.get("liquidity_usd"),
                "liquidity_change_1h_pct": info.get("liq_change_1h_pct"),
                "num_buys_5m": info.get("num_buys_5m"),
                "num_sells_5m": info.get("num_sells_5m"),
                "holder_count": info.get("holder_count"),
            }
        elif self.oc:
            jinfo = self.oc.jupiter_token_info(c.mint)
        else:
            jinfo = None
        conc = self.oc.largest_account_pcts(c.mint, supply) if (self.oc and supply) else None
        bundle = self.oc.sniper_bundle_pct(c.mint, supply_ui) if (self.oc and supply_ui) else None
        route = self.oc.sell_route(c.mint, price_usd, decimals) if self.oc else None

        # === HARD FAILS ===

        # 1. Mint authority renounced
        renounced_mint = None
        if mint_state is not None:
            renounced_mint = mint_state["mint_authority_renounced"]
        elif hasattr(c, "renounced"):
            renounced_mint = bool(c.renounced)
        if cfg.rug_require_mint_authority_renounced:
            if renounced_mint is True:
                check("mint_authority", "PASS", "renounced")
            elif renounced_mint is False:
                check("mint_authority", "FAIL", "still active — dev can mint unlimited supply", hard=True)
            else:
                check("mint_authority", "UNVERIFIED", "could not read mint account", penalty=15)

        # 2. Freeze authority renounced
        renounced_freeze = None
        if mint_state is not None:
            renounced_freeze = mint_state["freeze_authority_renounced"]
        elif hasattr(c, "renounced"):
            renounced_freeze = bool(c.renounced)
        if cfg.rug_require_freeze_authority_renounced:
            if renounced_freeze is True:
                check("freeze_authority", "PASS", "renounced")
            elif renounced_freeze is False:
                check("freeze_authority", "FAIL", "still active — dev can freeze your tokens", hard=True)
            else:
                check("freeze_authority", "UNVERIFIED", "could not read mint account", penalty=15)

        # 3. LP locked / burned
        lp_locked = bool(getattr(c, "lp_locked", False))
        if cfg.rug_require_lp_locked_or_burned:
            check("lp_locked", "PASS" if lp_locked else "FAIL",
                  "burned by pump.fun migration" if lp_locked else "LP not locked — dev can pull liquidity",
                  hard=not lp_locked)

        # 4. Liquidity deep enough to exit
        liq = _f(getattr(c, "liquidity_usd", 0.0))
        if liq < cfg.rug_min_liquidity_usd:
            check("liquidity_depth", "FAIL", f"${liq:.0f} < ${cfg.rug_min_liquidity_usd:.0f} floor", hard=True)
        else:
            check("liquidity_depth", "PASS", f"${liq:.0f}")

        # 5. Holder concentration
        top1 = None
        top10 = None
        if conc:
            top1, top10 = conc["top1_pct"], conc["top10_pct"]
            note_suffix = " (LP vault may be counted)"
        else:
            top1 = _f(getattr(c, "top_wallet_pct", 0.0)) or None
            note_suffix = " (Jupiter top-holders %)"
        if top1 is not None and top1 > cfg.rug_max_top1_holder_pct:
            check("top1_holder", "FAIL", f"{top1:.1f}% > {cfg.rug_max_top1_holder_pct:.0f}%{note_suffix}", hard=True)
        elif top1 is not None:
            check("top1_holder", "PASS", f"{top1:.1f}%{note_suffix}")
        else:
            check("top1_holder", "UNVERIFIED", "no holder data", penalty=10)
        if top10 is not None and top10 > cfg.rug_max_top10_holder_pct:
            check("top10_holders", "FAIL", f"{top10:.1f}% > {cfg.rug_max_top10_holder_pct:.0f}%", hard=True)
        elif top10 is not None:
            check("top10_holders", "PASS", f"{top10:.1f}%")

        # 6. Liquidity draining (LP being pulled out gradually)
        liq_chg = (jinfo or {}).get("liquidity_change_1h_pct")
        if liq_chg is not None:
            if liq_chg < cfg.rug_max_liq_drop_1h_pct:
                check("liquidity_trend", "FAIL", f"{liq_chg:.0f}% in 1h — liquidity draining", hard=True)
            else:
                check("liquidity_trend", "PASS", f"{liq_chg:+.0f}% in 1h")
        else:
            check("liquidity_trend", "UNVERIFIED", "no 1h liquidity delta", penalty=5)

        # 7. Serial rug-factory dev.
        # Jupiter's audit.devMints is astronomical for essentially every
        # pump.fun-origin token (shared deployer), so it's useless as a HARD
        # gate — it just rejected the whole feed. Kept as a points deduction:
        # a genuinely absurd count still costs score, but doesn't veto.
        dev_mints = int(getattr(c, "dev_mints", 0))
        if dev_mints > cfg.rug_max_dev_prior_mints:
            check("dev_history", "WARN", f"{dev_mints} prior mints by this dev", penalty=8)
        else:
            check("dev_history", "PASS", f"{dev_mints} prior mints")

        # 8. Sell route exists (honeypot shape)
        if cfg.rug_require_sell_route:
            if route is None:
                check("sell_route", "UNVERIFIED", "could not quote token->SOL", penalty=10)
            elif not route["has_route"]:
                check("sell_route", "FAIL", "no token->SOL route — cannot sell (honeypot-shaped)", hard=True)
            elif route["impact_pct"] > cfg.rug_sell_route_max_impact_pct:
                check("sell_route", "FAIL",
                      f"{route['impact_pct']:.0f}% price impact on a ${cfg.rug_sell_route_probe_usd:.0f} sell", hard=True)
            else:
                check("sell_route", "PASS", f"{route['impact_pct']:.1f}% impact on probe sell")

        # === WARNINGS (dock points, no hard fail) ===

        holders = (jinfo or {}).get("holder_count") or int(getattr(c, "holder_count", 0))
        if holders < cfg.rug_warn_min_holders:
            check("holder_count", "WARN", f"{holders} < {cfg.rug_warn_min_holders}", penalty=12)
        else:
            check("holder_count", "PASS", f"{holders}")

        organic = _f(getattr(c, "organic_score", 0.0))
        if 0.0 < organic < cfg.rug_warn_min_organic_score:
            check("organic_score", "WARN", f"{organic:.0f} < {cfg.rug_warn_min_organic_score:.0f}", penalty=10)
        elif organic > 0:
            check("organic_score", "PASS", f"{organic:.0f}")
        else:
            check("organic_score", "UNVERIFIED", "Jupiter has not scored it yet", penalty=3)

        buyers = int(getattr(c, "num_organic_buyers_5m", 0))
        if buyers < cfg.rug_warn_min_organic_buyers_5m:
            check("organic_buyers_5m", "WARN", f"{buyers} < {cfg.rug_warn_min_organic_buyers_5m}", penalty=8)
        else:
            check("organic_buyers_5m", "PASS", f"{buyers}")

        if bundle is not None:
            if bundle > cfg.rug_warn_max_sniper_bundle_pct:
                check("sniper_bundle", "WARN", f"{bundle:.0f}% of supply grabbed in first 15s", penalty=15)
            else:
                check("sniper_bundle", "PASS", f"{bundle:.0f}% in first 15s")
        elif self.oc:
            check("sniper_bundle", "UNVERIFIED", "no early-swap data", penalty=4)

        chg5m = _f(getattr(c, "price_change_5m_pct", 0.0))
        if chg5m < cfg.rug_warn_max_price_drop_5m_pct:
            check("price_5m", "WARN", f"{chg5m:.1f}% in 5m — dumping right now", penalty=10)
        else:
            check("price_5m", "PASS", f"{chg5m:+.1f}% in 5m")

        # sell pressure from Jupiter 5m buy/sell counts, if present
        nb = (jinfo or {}).get("num_buys_5m")
        ns = (jinfo or {}).get("num_sells_5m")
        if nb is not None and ns is not None and (nb + ns) >= 8:
            if ns > nb * 2:
                check("order_flow_5m", "WARN", f"{ns:.0f} sells vs {nb:.0f} buys (5m)", penalty=8)
            else:
                check("order_flow_5m", "PASS", f"{nb:.0f} buys / {ns:.0f} sells (5m)")

        # === VERDICT ===
        v.score = max(0.0, min(100.0, v.score))
        if v.hard_fails:
            v.verdict = "RUG_RISK"
        elif v.score >= cfg.rug_min_score_to_trade:
            v.verdict = "SAFE"
        elif v.score >= cfg.rug_caution_score:
            v.verdict = "CAUTION"
        else:
            v.verdict = "RUG_RISK"
        return v

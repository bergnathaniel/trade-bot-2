"""
Execution layer — where buy/sell orders actually get placed.

PaperExecutor: simulates fills using the fee model in config.py. No real
               money moves. Use this until the strategy proves itself.

LiveExecutor: places real swaps through Jupiter's Swap API v2 (GET /order,
              POST /execute) using a wallet loaded from SOLANA_PRIVATE_KEY
              and an RPC endpoint from HELIUS_RPC_URL. Requires
              JUPITER_API_KEY (free at portal.jup.ag — Jupiter requires a
              key on every tier now). Test with a tiny amount before
              trusting it with the full bankroll.
"""

import base64
import os
import time
from dataclasses import dataclass
from typing import Optional

import requests
from solders.transaction import VersionedTransaction

from config import Config
from wallet import load_keypair

# Rough base-fee + priority-fee cushion for a Solana tx (lamports). The real
# cost is whatever landed on-chain — check Solscan on your first few live
# trades and raise this if your actual fees run higher.
NETWORK_FEE_LAMPORTS_ESTIMATE = 10_000


@dataclass
class FillResult:
    success: bool
    filled_price_usd: float
    amount_usd: float
    fee_usd: float
    slippage_pct: float
    reason: str = ""


class PaperExecutor:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def buy(self, mint: str, price_usd: float, size_usd: float) -> FillResult:
        slip = self.cfg.est_slippage_pct
        fill_price = price_usd * (1 + slip)
        fee = size_usd * self.cfg.dex_swap_fee_pct + self.cfg.platform_fee_flat_usd + self.cfg.network_fee_usd
        return FillResult(
            success=True,
            filled_price_usd=fill_price,
            amount_usd=size_usd,
            fee_usd=fee,
            slippage_pct=slip * 100,
        )

    def sell(self, mint: str, price_usd: float, size_usd: float) -> FillResult:
        slip = self.cfg.est_slippage_pct
        fill_price = price_usd * (1 - slip)
        fee = size_usd * self.cfg.dex_swap_fee_pct + self.cfg.platform_fee_flat_usd + self.cfg.network_fee_usd
        return FillResult(
            success=True,
            filled_price_usd=fill_price,
            amount_usd=size_usd,
            fee_usd=fee,
            slippage_pct=slip * 100,
        )


class LiveExecutor:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.rpc_url = os.environ.get("HELIUS_RPC_URL")
        self.jupiter_api_key = os.environ.get("JUPITER_API_KEY")
        if not self.rpc_url:
            raise RuntimeError("HELIUS_RPC_URL is not set in the environment.")
        if not self.jupiter_api_key:
            print("[LiveExecutor] JUPITER_API_KEY not set — using Jupiter's unauthenticated "
                  "free tier (works, but more rate-limited). Get a key at https://portal.jup.ag.")

        self.keypair = load_keypair()
        self.pubkey = str(self.keypair.pubkey())
        self.session = requests.Session()

        balance_sol = self._get_sol_balance()
        print(f"[LiveExecutor] wallet {self.pubkey} | balance {balance_sol:.4f} SOL")
        if balance_sol <= 0:
            raise RuntimeError(f"Wallet {self.pubkey} has 0 SOL. Fund it before running live.")

    # ---------- RPC helpers ----------

    def _rpc(self, method: str, params: list):
        resp = self.session.post(
            self.rpc_url,
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise RuntimeError(f"RPC {method} failed: {data['error']}")
        return data["result"]

    def _get_sol_balance(self) -> float:
        result = self._rpc("getBalance", [self.pubkey])
        return result["value"] / 1e9

    def _get_token_balance_raw(self, mint: str) -> int:
        result = self._rpc(
            "getTokenAccountsByOwner",
            [self.pubkey, {"mint": mint}, {"encoding": "jsonParsed"}],
        )
        accounts = result["value"]
        if not accounts:
            return 0
        amount_info = accounts[0]["account"]["data"]["parsed"]["info"]["tokenAmount"]
        return int(amount_info["amount"])

    def _get_token_decimals(self, mint: str) -> int:
        result = self._rpc("getTokenSupply", [mint])
        return result["value"]["decimals"]

    def _headers(self) -> dict:
        return {"x-api-key": self.jupiter_api_key} if self.jupiter_api_key else {}

    def _get_sol_price_usd(self) -> float:
        r = self.session.get(
            self.cfg.jupiter_price_base_url,
            params={"ids": self.cfg.sol_mint},
            headers=self._headers(),
            timeout=10,
        )
        r.raise_for_status()
        return float(r.json()[self.cfg.sol_mint]["usdPrice"])

    # ---------- swap ----------

    def _swap(self, input_mint: str, output_mint: str, amount_raw: int) -> dict:
        slippage_bps = int(self.cfg.max_allowed_slippage_pct * 10000)
        order = self.session.get(
            f"{self.cfg.jupiter_swap_base_url}/order",
            params={
                "inputMint": input_mint,
                "outputMint": output_mint,
                "amount": amount_raw,
                "taker": self.pubkey,
                "slippageBps": slippage_bps,
            },
            headers=self._headers(),
            timeout=15,
        ).json()

        if not order.get("transaction"):
            raise RuntimeError(f"Jupiter could not build a swap: {order.get('errorMessage') or order}")

        raw_tx = base64.b64decode(order["transaction"])
        unsigned = VersionedTransaction.from_bytes(raw_tx)
        signed = VersionedTransaction(unsigned.message, [self.keypair])

        exec_resp = self.session.post(
            f"{self.cfg.jupiter_swap_base_url}/execute",
            json={
                "signedTransaction": base64.b64encode(bytes(signed)).decode(),
                "requestId": order["requestId"],
            },
            headers={**self._headers(), "Content-Type": "application/json"},
            timeout=30,
        ).json()

        if exec_resp.get("status") != "Success":
            raise RuntimeError(f"Swap execution failed: {exec_resp}")

        # Jupiter's own "Success" apparently doesn't always mean the transaction is
        # actually confirmed on-chain yet — two real buys reported success here and then
        # had zero on-chain balance seconds later. Don't trust the label; poll the chain
        # directly for actual confirmation before treating this as a real fill.
        signature = exec_resp.get("signature")
        if signature and not self._confirm_signature(signature):
            raise RuntimeError(
                f"Swap reported success but never confirmed on-chain (signature {signature}) — "
                f"treating as failed rather than risking an untracked position."
            )

        return exec_resp

    def _confirm_signature(self, signature: str, tries: int = 10, delay_seconds: float = 1.0) -> bool:
        for _ in range(tries):
            result = self._rpc("getSignatureStatuses", [[signature]])
            status = (result.get("value") or [None])[0]
            if status:
                if status.get("err"):
                    return False
                if status.get("confirmationStatus") in ("confirmed", "finalized"):
                    return True
            time.sleep(delay_seconds)
        return False

    # ---------- buy/sell ----------

    def buy(self, mint: str, price_usd: float, size_usd: float) -> FillResult:
        try:
            sol_price = self._get_sol_price_usd()
            amount_lamports = int((size_usd / sol_price) * 1e9)

            exec_resp = self._swap(self.cfg.sol_mint, mint, amount_lamports)

            actual_sol_spent = int(exec_resp["totalInputAmount"]) / 1e9
            tokens_received_raw = int(exec_resp["totalOutputAmount"])
            decimals = self._get_token_decimals(mint)
            tokens_received = tokens_received_raw / (10 ** decimals)

            actual_usd_spent = actual_sol_spent * sol_price
            filled_price_usd = actual_usd_spent / tokens_received if tokens_received else price_usd
            slippage_pct = abs(filled_price_usd - price_usd) / price_usd * 100 if price_usd else 0.0
            fee_usd = NETWORK_FEE_LAMPORTS_ESTIMATE / 1e9 * sol_price

            return FillResult(
                success=True,
                filled_price_usd=filled_price_usd,
                amount_usd=actual_usd_spent,
                fee_usd=fee_usd,
                slippage_pct=slippage_pct,
                reason=exec_resp.get("signature", ""),
            )
        except Exception as e:
            return FillResult(
                success=False, filled_price_usd=0.0, amount_usd=0.0,
                fee_usd=0.0, slippage_pct=0.0, reason=str(e),
            )

    def sell(self, mint: str, price_usd: float, size_usd: float) -> FillResult:
        try:
            raw_balance = self._get_token_balance_raw(mint)
            if raw_balance <= 0:
                raise RuntimeError(f"No on-chain balance found for {mint}")

            sol_price = self._get_sol_price_usd()
            exec_resp = self._swap(mint, self.cfg.sol_mint, raw_balance)

            sol_received = int(exec_resp["totalOutputAmount"]) / 1e9
            actual_usd_received = sol_received * sol_price

            decimals = self._get_token_decimals(mint)
            tokens_sold = raw_balance / (10 ** decimals)
            filled_price_usd = actual_usd_received / tokens_sold if tokens_sold else price_usd
            slippage_pct = abs(filled_price_usd - price_usd) / price_usd * 100 if price_usd else 0.0
            fee_usd = NETWORK_FEE_LAMPORTS_ESTIMATE / 1e9 * sol_price

            return FillResult(
                success=True,
                filled_price_usd=filled_price_usd,
                amount_usd=actual_usd_received,
                fee_usd=fee_usd,
                slippage_pct=slippage_pct,
                reason=exec_resp.get("signature", ""),
            )
        except Exception as e:
            return FillResult(
                success=False, filled_price_usd=0.0, amount_usd=0.0,
                fee_usd=0.0, slippage_pct=0.0, reason=str(e),
            )

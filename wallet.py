"""
Wallet loading for live trading.

Reads the wallet secret from the SOLANA_PRIVATE_KEY environment variable —
never hardcode it, never commit it, never put it anywhere but .env. Accepts
either form:

  - a 12/24-word BIP39 mnemonic (space-separated, English wordlist), derived
    via the standard Solana path m/44'/501'/0'/0' (SLIP-0010, ed25519) — the
    same derivation Phantom/Solflare use for the default account, or
  - a base58-encoded secret key (what Phantom's "Export Private Key" gives
    you directly, no derivation needed).

Implemented with stdlib crypto only (hashlib/hmac) to avoid pulling in
bip_utils' native dependencies, which don't have prebuilt wheels for every
Python version.
"""

import hashlib
import hmac
import os
import struct

from solders.keypair import Keypair

SOLANA_DERIVATION_PATH = (44, 501, 0, 0)  # m/44'/501'/0'/0'


def _bip39_seed(mnemonic: str, passphrase: str = "") -> bytes:
    salt = ("mnemonic" + passphrase).encode("utf-8")
    return hashlib.pbkdf2_hmac("sha512", mnemonic.encode("utf-8"), salt, 2048)


def _slip10_ed25519_derive(seed: bytes, path: tuple) -> bytes:
    """Returns the 32-byte private key for a fully-hardened ed25519 path."""
    digest = hmac.new(b"ed25519 seed", seed, hashlib.sha512).digest()
    key, chain_code = digest[:32], digest[32:]
    for index in path:
        hardened_index = index | 0x80000000
        data = b"\x00" + key + struct.pack(">L", hardened_index)
        digest = hmac.new(chain_code, data, hashlib.sha512).digest()
        key, chain_code = digest[:32], digest[32:]
    return key


def load_keypair() -> Keypair:
    secret = os.environ.get("SOLANA_PRIVATE_KEY")
    if not secret:
        raise RuntimeError(
            "SOLANA_PRIVATE_KEY is not set. Put a mnemonic phrase or a "
            "base58 secret key in your .env file."
        )
    secret = secret.strip()

    if " " in secret:
        seed = _bip39_seed(secret)
        priv_key_bytes = _slip10_ed25519_derive(seed, SOLANA_DERIVATION_PATH)
        return Keypair.from_seed(priv_key_bytes)

    return Keypair.from_base58_string(secret)

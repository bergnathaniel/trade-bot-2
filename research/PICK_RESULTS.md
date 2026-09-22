# PICK results: picking micro-caps a strategy did well on (walk-forward)

**Run:** 2026-09-22 09:35. PREREG_PICK.md sha256 `198044483145c4996dc63931087e5724cfd9a2a19b8a0450924539398224b7c1`.

## Integrity checks (must all pass before any result counts)

- Reproduces the app's own basket-test numbers exactly: PASS (worst diff 6.66e-15)
- No look-ahead (truncation test): PASS
- Pure noise (10 fake universes, no real edge anywhere): PASS (0 of 10 synthetic universes passed all 5 non-index gates)
- Planted persistence (can the test find a real, injected edge?): PASS (mean rank correlation 0.101242408605565, picked the seeded-edge stocks 49% of the time vs 17% by chance)

## Data

60 stocks (baskets C+D), 755 daily candles each after alignment. 0.50% fee, next-open fills, 60-candle warm-up, ranked every 63 trading days on trailing 252-day return, top 10 of 60 traded forward 63 days, $10,000 per stock.

## IBS Swing: FAIL

- 7 quarters, 460 closed trades
- Total return picking the top 10: **-28.3%**
- Random 10-of-60 picks, 97.5th percentile of 2000 draws: +31.2% (this result beat 44.2% of random draws)
- Trading all 60, no picking: -22.8%
- Holding IWC over the same stretch: +37.3%
- Holding the 60 stocks equally: +13.5%
- Positive in 2 of 7 quarters
- Mean rank correlation between trailing and next-quarter return: 0.052

| gate | result |
|---|---|
| G1_trades | pass |
| G2_positive | fail |
| G3_beats_random | fail |
| G4_beats_trade_all | fail |
| G5_quarters | fail |
| G6_beats_index | fail |

| quarter | picks | return | best stock | its return |
|---|---|---|---|---|
| 1 | AEYE, INSG, RM, VANI, IBIO, LENZ, TAYD, GLSI, ELDN, MGNX | -18.3% | IBIO | +8.7% |
| 2 | INSG, VUZI, IBIO, OCC, RM, UFI, AEYE, RPT, FHTX, ELDN | -0.4% | VUZI | +76.4% |
| 3 | VUZI, HOVR, AGIG, MVIS, TNXP, AMPG, III, OCC, FHTX, LENZ | +10.9% | AMPG | +168.1% |
| 4 | AMPG, TNXP, VUZI, FRMM, MVIS, III, OCC, HOVR, FIRY, SMHI | -14.7% | OCC | +29.8% |
| 5 | OCC, AMPG, OPXS, SMHI, FLWS, HOVR, MVIS, FHTX, III, FIRY | -3.6% | OCC | +29.1% |
| 6 | AMPG, SMHI, OPXS, ABOS, FLWS, HOVR, STI, TAYD, OCC, DHX | +2.2% | AMPG | +74.8% |
| 7 | AMPG, FIRY, MGNX, IBIO, ZNTL, FLWS, KRRO, OCC, GCTS, BDSX | -5.5% | BDSX | +28.8% |

## Fisher Transform: FAIL

- 7 quarters, 125 closed trades
- Total return picking the top 10: **-1.6%**
- Random 10-of-60 picks, 97.5th percentile of 2000 draws: +88.9% (this result beat 37.1% of random draws)
- Trading all 60, no picking: +12.5%
- Holding IWC over the same stretch: +37.3%
- Holding the 60 stocks equally: +13.5%
- Positive in 4 of 7 quarters
- Mean rank correlation between trailing and next-quarter return: -0.058

| gate | result |
|---|---|
| G1_trades | pass |
| G2_positive | fail |
| G3_beats_random | fail |
| G4_beats_trade_all | fail |
| G5_quarters | pass |
| G6_beats_index | fail |

| quarter | picks | return | best stock | its return |
|---|---|---|---|---|
| 1 | IBIO, FHTX, VUZI, OPXS, AMTX, ELDN, TAYD, DTIL, AEYE, GCTS | -9.8% | IBIO | +14.9% |
| 2 | IBIO, VUZI, AMPG, ELDN, CNDT, OCC, DTIL, GCTS, INSG, FHTX | -4.2% | GCTS | +52.7% |
| 3 | AMPG, VUZI, TNXP, III, HOVR, NDLS, AVD, MVIS, FHTX, ELDN | +4.7% | AVD | +37.7% |
| 4 | TNXP, AMPG, III, VUZI, AVD, FRMM, GLSI, STI, FIRY, OCC | +3.9% | STI | +185.6% |
| 5 | STI, TNXP, NERV, III, NDLS, GLSI, FULC, ABOS, DTIL, AVD | +8.5% | NDLS | +74.0% |
| 6 | STI, ZNTL, ABOS, GCTS, INSG, NERV, ATOM, OKUR, FULC, TAYD | +1.3% | ATOM | +59.4% |
| 7 | STI, IBIO, ABOS, OKUR, ZNTL, AMTX, OCC, NDLS, AIRS, ELDN | -4.8% | ABOS | +39.0% |

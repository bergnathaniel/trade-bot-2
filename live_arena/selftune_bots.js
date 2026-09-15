// A ninth batch: one bot (added 2026-09-14) that re-picks its own settings from its trailing paper-trading record
// instead of using one setting forever, to test whether letting a bot adapt actually beats freezing it. It never
// looks ahead: every check-in only scores candidates on candles that already closed. Counts in the speed test from
// the week of 2026-09-21 (RULES["joined"] in speed_test.py), same as team_bots.js's late arrivals. Not in the
// year-long paper tests - it's the experiment, not a candidate strategy.
(() => {
"use strict";
const tfMins = () => +$("tf").value;
const bars = mins => Math.max(1, Math.round(mins / tfMins()));
const pct = (x, dp = 1) => `${(x * 100).toFixed(dp)}%`;
const warm = (n, i) => wait(`Warming up. Needs ${n} candles (has ${i + 1}).`);

// The strategy shape never changes: buy when RSI(period) drops to or under a threshold, sell when it climbs back to
// 100 minus that threshold or HOLD_MINS goes by, whichever first. Only which (period, threshold) pair is active
// changes, re-picked every RETUNE_MINS from whichever of this small grid made the most money (before fees, as a
// ranking proxy only - the bot's real trades below pay the real fee) over the last LOOKBACK_MINS it's seen so far.
const PERIODS = [7, 14, 21];
const THRESHOLDS = [20, 25, 30];
const HOLD_MINS = 2880;      // sell after 2 days if RSI hasn't recovered
const LOOKBACK_MINS = 43200; // score candidates on up to the last 30 days
const RETUNE_MINS = 10080;   // re-pick every 7 days
const MIN_TRADES = 3;        // ignore a candidate with fewer than this many trades in the lookback - too little evidence

const rsiCache = new WeakMap();
function rsiFor(I, period) {
  let m = rsiCache.get(I);
  if (!m) rsiCache.set(I, m = {});
  return m[period] || (m[period] = rsi(I.close, period));
}
// What (period, threshold) would have made on candles [from, to) - no look-ahead, since to <= the current candle.
function scoreCandidate(I, period, threshold, from, to) {
  const R = rsiFor(I, period), sellAt = 100 - threshold, hold = bars(HOLD_MINS);
  let ret = 0, inPos = false, entry = 0, entryIdx = 0, trades = 0;
  for (let j = from; j < to; j++) {
    if (R[j] == null) continue;
    if (!inPos) { if (R[j] <= threshold) { inPos = true; entry = I.close[j]; entryIdx = j; } }
    else if (R[j] >= sellAt || j - entryIdx >= hold) { ret += I.close[j] / entry - 1; inPos = false; trades++; }
  }
  return { ret, trades };
}
function pickBest(I, i) {
  const from = Math.max(0, i - bars(LOOKBACK_MINS));
  let best = null;
  for (const period of PERIODS) for (const threshold of THRESHOLDS) {
    const s = scoreCandidate(I, period, threshold, from, i);
    if (s.trades < MIN_TRADES) continue;
    if (!best || s.ret > best.ret) best = { period, threshold, ret: s.ret, trades: s.trades };
  }
  return best;
}

BOTS.push(
  { id: "selftuner", name: "Self-Tuner", type: "Adaptive", color: "#e63946",
    desc: `An experiment, not a strategy pick: every ${RETUNE_MINS / 1440} days it checks which of ${PERIODS.length * THRESHOLDS.length} RSI settings (period ${PERIODS.join("/")}, buy at or under ${THRESHOLDS.join("/")}) made the most money over up to the last ${LOOKBACK_MINS / 1440} days of candles it's seen, using only candles already closed, then trades that setting until its next check-in. Sells when RSI recovers to 100 minus the buy level, or after ${HOLD_MINS / 1440} days, whichever comes first. Tests whether a bot re-picking its own settings from what just worked beats one frozen setting - not a claim that it does.`,
    reset() { this.st = { period: null, threshold: null, nextTune: null, entryIdx: null, pickedRet: null, pickedTrades: null }; },
    overlays: () => [],
    decide(I, i, pos) {
      const s = this.st;
      if (s.nextTune == null || i >= s.nextTune) {
        const best = pickBest(I, i);
        if (best) { s.period = best.period; s.threshold = best.threshold; s.pickedRet = best.ret; s.pickedTrades = best.trades; }
        s.nextTune = i + bars(RETUNE_MINS);
      }
      if (s.period == null) return warm(bars(LOOKBACK_MINS) + Math.max(...PERIODS) + 1, i);
      const R = rsiFor(I, s.period)[i];
      if (R == null) return warm(Math.max(...PERIODS) + 1, i);
      const sellAt = 100 - s.threshold;
      if (pos) {
        if (R >= sellAt) return sell(`RSI (period ${s.period}) recovered to ${R.toFixed(0)}, at or past ${sellAt}. Selling.`);
        if (i - s.entryIdx >= bars(HOLD_MINS)) return sell(`${HOLD_MINS / 1440} days went by without a recovery. Selling.`);
        return wait(`Holding. Tuned to RSI ${s.period}; sells at ${sellAt} or after ${HOLD_MINS / 1440} days. Currently ${R.toFixed(0)}.`);
      }
      if (R <= s.threshold) return (s.entryIdx = i, buy(`Currently tuned to RSI ${s.period}, buy at or under ${s.threshold} (picked from ${s.pickedTrades} trades over its lookback, ${pct(s.pickedRet)} total before fees). RSI just hit ${R.toFixed(0)}. Buying.`));
      return wait(`Tuned to RSI ${s.period}, buys at ${s.threshold} or under, sells at ${sellAt}. Currently ${R.toFixed(0)}.`);
    } }
);
})();

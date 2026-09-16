// A tenth batch: one bot (added 2026-09-15) that genuinely learns, by a different mechanism than the two learning
// bots that already exist - fast_bots.js's "Learning Bot" (one logistic-regression model, trained by gradient
// descent) and lesson_bots.js's "Cost-Aware Learner" (a ridge-regression forecast, refit from scratch each time).
// This one is an ensemble of named, independent signals whose trust weights rise or fall with their own track
// record (the "multiplicative weights" method). Every candle's commentary prints each signal's current weight and
// hit rate, so what it has learned is visible on screen instead of buried in a model's coefficients. Counts in the
// speed test from the week of 2026-09-21 (RULES["joined"] in speed_test.py). Not in the year-long paper tests.
(() => {
"use strict";
const bars = mins => Math.max(1, Math.round(mins / +$("tf").value));
const pct = (x, dp = 1) => `${(x * 100).toFixed(dp)}%`;
const warm = (n, i) => wait(`Warming up. Needs ${n} candles (has ${i + 1}).`);

const HORIZON_MINS = 240;   // each signal's vote is judged against the price move over this many minutes
const HOLD_MINS = 2880;     // sells after 2 days regardless of the vote
const GROW = 1.03, SHRINK = 0.97;   // a signal's trust weight after a right or wrong call
const FLOOR = 0.2, CEIL = 5;        // keeps every signal alive - never fully silenced, never runs away
const MIN_SCORED = 10;              // don't show a hit rate until a signal has been judged this many times
const BUY_AT = 0.5, SELL_AT = 0;    // thresholds on the trust-weighted average vote, which runs -1 to +1

// Six simple, independent yes/no/no-opinion signals. Each reads only index j and earlier - the same backward-only
// indicator arrays (computed once per market by computeInd) that every other bot in this app already reads.
const SIGNALS = [
  { name: "RSI dip", vote: (I, j) => I.rsi14[j] == null ? 0 : I.rsi14[j] < 30 ? 1 : I.rsi14[j] > 70 ? -1 : 0 },
  { name: "Trend", vote: (I, j) => I.ema9[j] == null || I.ema21[j] == null ? 0 : I.ema9[j] > I.ema21[j] ? 1 : -1 },
  { name: "MACD", vote: (I, j) => I.macd[j] == null || I.signal[j] == null ? 0 : I.macd[j] > I.signal[j] ? 1 : -1 },
  { name: "Band touch", vote: (I, j) => I.bb.lo[j] == null ? 0 : I.close[j] <= I.bb.lo[j] ? 1 : I.close[j] >= I.bb.up[j] ? -1 : 0 },
  { name: "Volume", vote: (I, j) => I.volAvg20[j] == null || !(I.volAvg20[j] > 0) || I.vol[j] <= I.volAvg20[j] ? 0 : I.close[j] > I.open[j] ? 1 : I.close[j] < I.open[j] ? -1 : 0 },
  { name: "Momentum", vote: (I, j) => j < 1 || I.close[j - 1] == null ? 0 : I.close[j] > I.close[j - 1] ? 1 : I.close[j] < I.close[j - 1] ? -1 : 0 },
];
const votesAt = (I, j) => SIGNALS.map(s => s.vote(I, j));

BOTS.push(
  { id: "trackrecord", name: "Track Record", type: "Stats", color: "#06a77d",
    desc: `Six simple, independent signals (${SIGNALS.map(s => s.name).join(", ")}) each vote bullish, bearish or no opinion every candle. Every signal starts equally trusted. Every candle, it checks each signal's vote from ${HORIZON_MINS / 60} hours ago against what actually happened since - using only outcomes that have already finished - and nudges that signal's trust up ${pct(GROW - 1, 0)} if it called it right or down ${pct(1 - SHRINK, 0)} if wrong. It buys when the trust-weighted average vote leans bullish enough, sells when it turns bearish or after ${HOLD_MINS / 1440} days. Every line of commentary prints each signal's current trust and hit rate, so which ideas it's leaning on is visible, not hidden inside a model.`,
    reset() { this.st = { weights: SIGNALS.map(() => 1), right: SIGNALS.map(() => 0), scored: SIGNALS.map(() => 0), entryIdx: null }; },
    overlays: () => [],
    decide(I, i, pos) {
      const s = this.st, H = bars(HORIZON_MINS);
      if (i >= H) {
        const past = votesAt(I, i - H), actual = Math.sign(I.close[i] - I.close[i - H]);
        if (actual !== 0) for (let k = 0; k < SIGNALS.length; k++) {
          if (past[k] === 0) continue;
          s.scored[k]++;
          const correct = past[k] === actual;
          if (correct) s.right[k]++;
          s.weights[k] = Math.max(FLOOR, Math.min(CEIL, s.weights[k] * (correct ? GROW : SHRINK)));
        }
      }
      const now = votesAt(I, i);
      let score = 0, total = 0;
      for (let k = 0; k < SIGNALS.length; k++) if (now[k] !== 0) { score += s.weights[k] * now[k]; total += s.weights[k]; }
      const avg = total > 0 ? score / total : 0;
      const line = SIGNALS.map((sig, k) => `${sig.name} ${s.weights[k].toFixed(2)}x${s.scored[k] >= MIN_SCORED ? ` (right ${pct(s.right[k] / s.scored[k], 0)} of ${s.scored[k]})` : ""}`).join(", ");
      if (pos) {
        if (avg <= SELL_AT) return sell(`Weighted vote turned to ${avg.toFixed(2)}. Selling. [${line}]`);
        if (i - s.entryIdx >= bars(HOLD_MINS)) return sell(`${HOLD_MINS / 1440} days went by without turning bearish. Selling. [${line}]`);
        return wait(`Holding. Weighted vote ${avg.toFixed(2)}; sells at ${SELL_AT} or after ${HOLD_MINS / 1440} days. [${line}]`);
      }
      if (total === 0) return wait(`No signal has an opinion this candle. [${line}]`);
      if (avg >= BUY_AT) { s.entryIdx = i; return buy(`Weighted vote ${avg.toFixed(2)}, at or past ${BUY_AT}. Buying. [${line}]`); }
      return wait(`Weighted vote ${avg.toFixed(2)}, needs ${BUY_AT} to buy. [${line}]`);
    } }
);
})();

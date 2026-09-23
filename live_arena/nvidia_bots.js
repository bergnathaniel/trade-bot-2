// An eleventh batch of Live Arena bots (added 2026-09-22): one bot that asks a general-purpose AI model, hosted free
// by NVIDIA (build.nvidia.com's NIM API), to look at a coin's recent daily price action once a day and call buy,
// hold or sell, with its reasoning shown like any other bot's commentary. Unlike Kronos (kronos_bots.js), a model
// actually trained to forecast prices, this is a general reasoning model doing the same job Track Record's signals
// do by hard-coded rule - just asking a model to think about it instead. nvidia_forecasts.py makes one call per coin
// per day (crypto only, so it isn't buried under thousands of 5-minute-candle decisions) and saves each day's call
// to data/speed/outside/nvidia_crypto.json; this bot reads it. Speed test only. Not in the year-long paper tests.
// If nvidia_forecasts.py never ran (no NVIDIA_API_KEY set), this bot just waits, the same way Kronos bots wait when
// their PyTorch environment isn't installed.
(() => {
"use strict";
const DAY = 86400;

function lastAtOrBefore(rows, t) {   // index of the last day-call stamped at or before t, or -1
  let lo = 0, hi = rows.length - 1, found = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (rows[mid].time <= t) { found = mid; lo = mid + 1; } else hi = mid - 1;
  }
  return found;
}

function call(I, i) {
  const ext = window.SPEED_EXT, all = ext && ext.outside ? ext.outside.nvidia : null;
  if (!all) return { missing: "NVIDIA Reasoner's daily calls, which only the weekly speed test computes" };
  const rows = all[ext.current];
  if (!rows || !rows.length) return { missing: "an NVIDIA call for this market" };
  const k = lastAtOrBefore(rows, I.time[i]);
  if (k < 0 || I.time[i] - rows[k].time >= 2 * DAY) return { stale: true };
  return { day: rows[k].time, action: rows[k].action, reason: rows[k].reason };
}

BOTS.push({
  id: "nvidiareasoner", name: "NVIDIA Reasoner", type: "AI model", color: "#76b900",
  desc: "Once a day, a general-purpose AI model hosted free by NVIDIA (not a model trained to forecast prices - just "
      + "one asked to look at recent daily prices and decide) calls buy, hold or sell, with a one-sentence reason. "
      + "This bot acts on that call and only re-checks once a day. Speed test only; needs NVIDIA_API_KEY set when the "
      + "week's calls are made, or it just waits.",
  overlays: () => [],
  reset() { this.st = { lastDay: null }; },
  decide(I, i, pos) {
    const C = call(I, i);
    if (C.missing) return wait(`Needs ${C.missing}.`);
    if (C.stale) return wait("No NVIDIA call from the last 2 days.");
    const line = `NVIDIA's call: ${C.action}. "${C.reason}"`;
    if (C.day === this.st.lastDay) return wait(`Already acted on today's call. ${line}`);
    this.st.lastDay = C.day;
    if (C.action === "buy" && !pos) return buy(line);
    if (C.action === "sell" && pos) return sell(line);
    return wait(line);
  },
});
})();

// A seventh batch of Live Arena bots (added 2026-09-13): bots that trade on the forecasts of Kronos, an open-source AI
// model pre-trained on price candles from 45+ exchanges (Shi et al., AAAI 2026; github.com/shiyu-coder/Kronos).
// Every hour of the speed test, kronos_forecasts.py has Kronos-small forecast the next 8 hourly candles of every market
// from its last 140 to 160 hourly candles, and these bots read those forecasts. Kronos-small came out in 2025, so it has
// never seen the weeks tested. Speed test only. None of these bots are in the year-long paper tests.
(() => {
"use strict";

const tfMins = () => +$("tf").value;
const bars = mins => Math.max(1, Math.round(mins / tfMins()));   // how many candles make up this many minutes
const pct = (x, dp = 2) => `${(x * 100).toFixed(dp)}%`;
const roundTrip = () => 2 * feeRate() + 2 * SLIP;   // a buy and its sale together, as a share of the price
const needFast = tf => wait(`Needs candles of ${tf} minutes or shorter.`);

function lastAtOrBefore(rows, t) {   // index of the last row stamped at or before t, or -1
  let lo = 0, hi = rows.length - 1, found = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (rows[mid].time <= t) { found = mid; lo = mid + 1; } else hi = mid - 1;
  }
  return found;
}
// The newest forecast for this market that was already known when this candle closed. Forecasts an hour old or older
// count as stale (for stocks, that's every candle before 10:30 am, until the first forecast of the day).
function forecast(I, i) {
  const ext = window.SPEED_EXT, all = ext && ext.outside ? ext.outside.kronos : null;
  if (!all) return { missing: "Kronos's forecasts, which only the weekly speed test computes" };
  const rows = all[ext.current];
  if (!rows || !rows.length) return { missing: "Kronos forecasts for this market" };
  const end = I.time[i] + tfMins() * 60, k = lastAtOrBefore(rows, end);
  if (k < 0 || end - rows[k].time >= 3600) return { stale: true };
  const f = rows[k];   // stored as open = next hour, high = next 4 hours, low = lowest low within 8 hours, close = next 8 hours
  return { next1: f.open, next4: f.high, low8: f.low, next8: f.close };
}

// A bot that buys when a forecast beats the fees and sells after `hold` minutes, unless the newest forecast still does.
function kronosBot({ id, name, color, desc, hold, label, good, detail }) {
  return { id, name, type: "AI model", color, desc,
    overlays: () => [],
    decide(I, i, pos) {
      if (tfMins() > 60) return needFast(60);
      const F = forecast(I, i), bar = roundTrip();
      if (F.missing) return wait(`Needs ${F.missing}.`);
      if (pos && i - this.st.entryIdx >= bars(hold)) {
        if (!F.stale && good(F, bar)) { this.st.entryIdx = i; return wait(`Time's up, but Kronos's newest forecast (${detail(F)}) still clears the bar. Holding another ${label}.`); }
        return sell(`${label} went by${F.stale ? "" : ` and Kronos's newest forecast (${detail(F)}) no longer clears the bar`}. Selling.`);
      }
      if (pos) return wait(`Holding. ${bars(hold) - (i - this.st.entryIdx)} candles until it checks the forecast again.`);
      if (F.stale) return wait("No Kronos forecast from the last hour.");
      if (good(F, bar)) { this.st.entryIdx = i; return buy(`Kronos forecasts ${detail(F)}. A buy and a sale cost ${pct(bar)}. Buying for ${label}.`); }
      return wait(`Kronos forecasts ${detail(F)}. A buy and a sale cost ${pct(bar)}.`);
    } };
}

BOTS.push(
  kronosBot({ id: "kronos8h", name: "Kronos 8-Hour Forecast", color: "#8338ec", hold: 480, label: "8 hours",
    desc: "Kronos, an open-source AI model trained on price candles from 45+ exchanges, forecasts the next 8 hours every hour. Buys when its forecast for 8 hours ahead is bigger than what a buy and a sale cost, and sells 8 hours later unless the newest forecast still beats the fees. Speed test only; needs candles of 1 hour or shorter.",
    good: (F, bar) => F.next8 > bar, detail: F => `${pct(F.next8)} over the next 8 hours` }),
  kronosBot({ id: "kronosstrong", name: "Kronos Strong Forecast", color: "#3a0ca3", hold: 480, label: "8 hours",
    desc: "Only acts on Kronos's boldest calls: an 8-hour forecast of at least twice what a buy and a sale cost, with its 4-hour forecast up too. Sells 8 hours later unless the newest forecast still clears that bar. Speed test only; needs candles of 1 hour or shorter.",
    good: (F, bar) => F.next8 >= 2 * bar && F.next4 > 0, detail: F => `${pct(F.next8)} over 8 hours and ${pct(F.next4)} over 4` }),
  kronosBot({ id: "kronos1h", name: "Kronos Next Hour", color: "#b5179e", hold: 60, label: "1 hour",
    desc: "Buys when Kronos forecasts the next hour to rise by more than what a buy and a sale cost, and sells an hour later unless the newest forecast still does. On stocks, where fees are tiny, short forecasts get a fair chance; on crypto an hour's move rarely covers 0.54%. Speed test only; needs candles of 1 hour or shorter.",
    good: (F, bar) => F.next1 > bar, detail: F => `${pct(F.next1)} over the next hour` }),
);
})();

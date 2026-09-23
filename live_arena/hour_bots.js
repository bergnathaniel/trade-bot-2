// A twelfth batch of Live Arena bots (added 2026-09-23): one clock-time bot from published research. Padyšák &
// Vojtko, "Seasonality, Trend-following, and Mean reversion in Bitcoin" (SSRN 4081000, 2022) found bitcoin's
// returns from 22:00 to midnight UTC stood out, a time when the big stock exchanges are all closed. Their rule: buy
// at 22:00 UTC, sell two hours later. They reported a Sharpe of 1.58 on 2015-2021 bitcoin, before fees. The paper
// tested bitcoin only; this bot follows the same clock on whatever market it's on. Speed test only; not in the
// year-long paper tests.
(() => {
"use strict";
const START_MIN = 22 * 60, END_MIN = 24 * 60;   // 22:00 to midnight, UTC

BOTS.push({
  id: "btc22utc", name: "Late-Night Hours (22:00 UTC)", type: "Time", color: "#5e548e",
  desc: "Published research on bitcoin found the two hours from 22:00 to midnight UTC stood out, when the big stock "
      + "exchanges are all closed. Buys at 22:00 UTC and sells at midnight, every day. The paper's Sharpe of 1.58 "
      + "(2015-2021) was before fees; a round trip costs far more on crypto than on stocks. Needs candles of 1 hour "
      + "or shorter.",
  overlays: () => [],
  decide(I, i, pos) {
    const tf = +$("tf").value;
    if (tf > 60) return wait("Needs candles of 1 hour or shorter.");
    const d = new Date((I.time[i] + OFF + tf * 60) * 1000);   // when an order placed now would fill
    const mins = d.getUTCHours() * 60 + d.getUTCMinutes();
    const inWindow = mins >= START_MIN && mins < END_MIN;
    if (!pos && inWindow) return buy("It's 22:00 UTC or later: buying for the late-night hours.");
    if (pos && !inWindow) return sell("Midnight UTC: selling.");
    return wait(inWindow ? "Late-night hours: holding." : "Waiting for 22:00 UTC.");
  },
});
})();

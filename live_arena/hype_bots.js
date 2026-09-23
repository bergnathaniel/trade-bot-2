// A thirteenth batch of Live Arena bots (added 2026-09-23): one bot that chooses WHICH market in its group to buy
// by attention. Meme coins move on hype, and the clearest free sign of hype is a sudden jump in how much is being
// traded. Every candle it compares each market's last 24 hours of dollar volume with that market's own normal
// (its average day over the 6 days before), and buys only the group's single biggest surge, and only while the price
// is rising with it, then sells 6 hours later. Built for the speed test's meme-coin group; it also runs on crypto. It never warms up on stocks,
// whose short trading days don't give it 7 days of 24-hour candles within the speed test's warm-up. Not fitted to
// any past data. Speed test only; not in the year-long paper tests.
(() => {
"use strict";
const tfMins = () => +$("tf").value;
const bars = mins => Math.max(1, Math.round(mins / tfMins()));
const pct = (x, dp = 1) => `${(x * 100).toFixed(dp)}%`;
const EXT = () => window.SPEED_EXT || null;
const DAY_MINS = 1440, BASE_DAYS = 6, MIN_SURGE = 2, HOLD_MINS = 360;   // the speed test warms up 7 days: 6 for the normal + 1 for today
const cache = new WeakMap();

// For each candle time: every market's volume surge (last 24 h of dollar volume / its average day before that) and
// its 24-hour price move. Uses only candles up to that time.
function surgeTable(ext) {
  const key = `surge${tfMins()}`;
  let c = cache.get(ext.group);
  if (!c) cache.set(ext.group, c = {});
  if (c[key]) return c[key];
  const day = bars(DAY_MINS), out = new Map();
  for (const s of ext.symbols) {
    const rows = ext.group[s], dv = [0];
    for (const r of rows) dv.push(dv[dv.length - 1] + r.close * (r.volume || 0));   // running total of dollar volume
    for (let j = day * (BASE_DAYS + 1) - 1; j < rows.length; j++) {
      const today = dv[j + 1] - dv[j + 1 - day];
      const normal = (dv[j + 1 - day] - dv[j + 1 - day * (BASE_DAYS + 1)]) / BASE_DAYS;
      if (!(normal > 0)) continue;
      let e = out.get(rows[j].time);
      if (!e) out.set(rows[j].time, e = {});
      e[s] = { surge: today / normal, move: rows[j].close / rows[j - day].close - 1 };
    }
  }
  return (c[key] = out);
}

BOTS.push({
  id: "hypeleader", name: "Hype Leader", type: "Breadth", color: "#ff006e",
  desc: "Picks which coin to buy by hype. Every candle it ranks the group by how much more is being traded in the "
      + `last 24 hours than on that coin's normal day (its average over the ${BASE_DAYS} days before). Buys this market only `
      + `if it has the group's biggest surge, at least ${MIN_SURGE}x normal, and its price is up over those 24 hours. `
      + "Sells 6 hours later. Surges often come right before a dump, so this is a test, not a tip. Speed test only; "
      + "needs candles of 1 hour or shorter.",
  overlays: () => [],
  decide(I, i, pos) {
    const ext = EXT();
    if (!ext) return wait("Needs the other markets in its group, which only the weekly speed test provides.");
    if (tfMins() > 60) return wait("Needs candles of 1 hour or shorter.");
    if (pos) return checkExits(this, I, i) || wait(`Holding. ${this.st.maxBars - (i - this.st.entryIdx)} candles left.`);
    const e = surgeTable(ext).get(I.time[i]), me = e && e[ext.current];
    if (!me) return wait(`Warming up: needs ${BASE_DAYS + 1} days of candles to know this coin's normal volume.`);
    const all = Object.entries(e);
    if (all.length < 5) return wait("Too few markets in the group have enough history.");
    const rank = 1 + all.filter(([, x]) => x.surge > me.surge).length;
    const line = `${me.surge.toFixed(1)}x its normal volume (#${rank} of ${all.length}), price ${pct(me.move)} over 24 hours.`;
    if (rank === 1 && me.surge >= MIN_SURGE && me.move > 0)
      return enter(this, i, `The group's biggest hype surge: ${line} Buying for 6 hours.`, { maxBars: bars(HOLD_MINS) });
    return wait(`${line} Buys only the #1 surge, at ${MIN_SURGE}x or more, with the price rising.`);
  },
});
})();

// An eighth batch of Live Arena bots (added 2026-09-13, just before the first forward week): cross-market rankings,
// pairs, Kronos combined with dips, Kronos's rankings of the group, and "teams" that act when several existing bots agree. They joined after that week's
// rules were set, so the speed test counts them from the week of 2026-09-21 (RULES["joined"] in speed_test.py).
// Thresholds were chosen after looking at the practice weeks, so those weeks prove nothing for them. Speed test only
// where noted. None of these bots are in the year-long paper tests.
(() => {
"use strict";

// ---------- helpers ----------
const memo = new WeakMap();
function get(owner, key, make) {   // computed the first time a bot asks, once per set of candles (or per group)
  let m = memo.get(owner);
  if (!m) memo.set(owner, m = {});
  if (!(key in m)) m[key] = make();
  return m[key];
}
const tfMins = () => +$("tf").value;
const bars = mins => Math.max(1, Math.round(mins / tfMins()));   // how many candles make up this many minutes
const pct = (x, dp = 1) => `${(x * 100).toFixed(dp)}%`;
const warm = (n, i) => wait(`Warming up. Needs ${n} candles (has ${i + 1}).`);
const needFast = tf => wait(`Needs candles of ${tf} minutes or shorter.`);
const EXT = () => window.SPEED_EXT || null;
const needGroup = () => wait("Needs the other markets in its group, which only the weekly speed test provides.");
const roundTrip = () => 2 * feeRate() + 2 * SLIP;   // a buy and its sale together, as a share of the price
const change = (I, i, mins) => { const k = bars(mins); return i >= k ? I.close[i] / I.close[i - k] - 1 : null; };

function lastAtOrBefore(rows, t) {   // index of the last row stamped at or before t, or -1
  let lo = 0, hi = rows.length - 1, found = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (rows[mid].time <= t) { found = mid; lo = mid + 1; } else hi = mid - 1;
  }
  return found;
}
function groupMoves(ext, k) {   // for each candle time, every market in the group's move over the last k candles
  return get(ext.group, `moves${k}`, () => {
    const out = new Map();
    for (const s of ext.symbols) {
      const rows = ext.group[s];
      for (let j = k; j < rows.length; j++) {
        let e = out.get(rows[j].time);
        if (!e) out.set(rows[j].time, e = {});
        e[s] = rows[j].close / rows[j - k].close - 1;
      }
    }
    return out;
  });
}
// A repeatable random number in [0, 1) for this candle, with a different random calendar in every market.
function chance(I, i, salt) {
  let h = Math.imul(((I.time[i] + OFF) | 0) ^ salt, 0x9e3779b1) ^ Math.imul(Math.round(I.open[0] * 1e4) | 0, 0x85ebca77);
  h ^= h >>> 15; h = Math.imul(h, 0x2c1b3c6d); h ^= h >>> 12; h = Math.imul(h, 0x297a2d39); h ^= h >>> 15;
  return (h >>> 0) / 4294967296;
}
// The newest Kronos forecast for this market that was known when this candle closed, if it's under an hour old.
function kronos(I, i) {
  const ext = EXT(), all = ext && ext.outside ? ext.outside.kronos : null, rows = all && all[ext.current];
  if (!rows || !rows.length) return null;
  const end = I.time[i] + tfMins() * 60, k = lastAtOrBefore(rows, end);
  if (k < 0 || end - rows[k].time >= 3600) return { stale: true };
  return { next1: rows[k].open, next4: rows[k].high, low8: rows[k].low, next8: rows[k].close };
}
// Kronos's 8-hour forecasts for the whole group, lined up by the time they were made.
function kronosRanks(ext) {
  const all = ext && ext.outside ? ext.outside.kronos : null;
  if (!all) return null;
  return get(all, "ranks", () => {
    const byTime = new Map();
    for (const [s, rows] of Object.entries(all)) {
      for (const r of rows) {
        let e = byTime.get(r.time);
        if (!e) byTime.set(r.time, e = {});
        e[s] = r.close;
      }
    }
    return { byTime, times: [...byTime.keys()].sort((a, b) => a - b) };
  });
}
// Where this market ranks in the group's newest Kronos forecasts known at this candle's close (under an hour old).
function kronosRank(I, i) {
  const ext = EXT(), R = kronosRanks(ext);
  if (!R) return null;
  const end = I.time[i] + tfMins() * 60;
  let lo = 0, hi = R.times.length - 1, k = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (R.times[mid] <= end) { k = mid; lo = mid + 1; } else hi = mid - 1;
  }
  if (k < 0 || end - R.times[k] >= 3600) return { stale: true };
  const e = R.byTime.get(R.times[k]), me = e[ext.current];
  if (me == null) return { stale: true };
  const all = Object.values(e);
  return { next8: me, top: 1 + all.filter(x => x > me).length, bottom: 1 + all.filter(x => x < me).length, n: all.length };
}
// A bot that buys when Kronos ranks this market a certain way and sells 8 hours later, unless it still does.
function rankBot({ id, name, type, color, desc, pick, label }) {
  return { id, name, type, color, desc,
    overlays: () => [],
    decide(I, i, pos) {
      if (tfMins() > 60) return needFast(60);
      const R = kronosRank(I, i);
      if (!R) return wait("Needs Kronos's forecasts, which only the weekly speed test computes.");
      if (pos && i - this.st.entryIdx >= bars(480)) {
        if (!R.stale && pick(R, roundTrip())) { this.st.entryIdx = i; return wait(`8 hours are up, but Kronos still ranks it ${label(R)}. Holding another 8 hours.`); }
        return sell(`8 hours are up${R.stale ? "" : ` and Kronos now ranks it ${label(R)}`}. Selling.`);
      }
      if (pos) return wait(`Holding. ${bars(480) - (i - this.st.entryIdx)} candles until it checks the ranking again.`);
      if (R.stale) return wait("No Kronos forecast from the last hour.");
      if (pick(R, roundTrip())) { this.st.entryIdx = i; return buy(`Kronos ranks this market ${label(R)}, forecasting ${pct(R.next8, 2)} over 8 hours. Buying.`); }
      return wait(`Kronos ranks this market ${label(R)} (${pct(R.next8, 2)} over 8 hours).`);
    } };
}
// Stocks and ETFs that usually move together. For each candle time both share: how far the log price ratio of `a` to
// `b` sits from its average over the n shared candles before it, in standard deviations (below zero: `a` fell behind).
const PAIRS = [["QQQ", "SPY"], ["IWM", "SPY"], ["DIA", "SPY"], ["AMD", "NVDA"], ["COIN", "MSTR"], ["MSFT", "AAPL"], ["GOOGL", "META"], ["AVGO", "NVDA"]];
function pairZ(ext, a, b, n) {
  return get(ext.group, `pair:${a}:${b}:${n}`, () => {
    const other = new Map(ext.group[b].map(r => [r.time, r.close])), times = [], ratio = [], out = new Map();
    for (const r of ext.group[a]) {
      const c = other.get(r.time);
      if (c != null) { times.push(r.time); ratio.push(Math.log(r.close / c)); }
    }
    for (let j = n; j < ratio.length; j++) {
      let s = 0, q = 0;
      for (let k = j - n; k < j; k++) { s += ratio[k]; q += ratio[k] * ratio[k]; }
      const m = s / n, sd = Math.sqrt(Math.max(q / n - m * m, 0));
      if (sd > 0) out.set(times[j], (ratio[j] - m) / sd);
    }
    return out;
  });
}
// How many of these bots are holding this market right now. Their decisions for this candle come first (they were
// added to BOTS earlier), so this only uses what was known at this candle's close.
const holders = ids => ids.filter(id => acct[id] && acct[id].qty > 0);

function teamBot({ id, name, color, desc, members, buyAt, sellAt }) {
  return { id, name, type: "Team", color, desc,
    overlays: () => [],
    decide(I, i, pos) {
      const present = members.filter(m => BOTS.some(b => b.id === m));
      if (present.length < members.length) return wait("Some of its team members aren't loaded.");
      const hold = holders(members), names = hold.map(m => BOTS.find(b => b.id === m).name).join(", ");
      if (!pos && hold.length >= buyAt) return buy(`${hold.length} of ${members.length} team members hold this market (${names}). Buying with them.`);
      if (pos && hold.length <= sellAt) return sell(`Only ${hold.length} of ${members.length} team members still hold. Selling.`);
      return wait(`${hold.length} of ${members.length} team members hold this market${hold.length ? ` (${names})` : ""}. ${pos ? `Sells at ${sellAt} or fewer.` : `Buys at ${buyAt} or more.`}`);
    } };
}

BOTS.push(
  // ----- rankings across the group (speed test only) -----
  { id: "worstcoin24", name: "Day's Biggest Loser, 24 Hours", type: "Breadth", color: "#d62828",
    desc: "Ranks every market in the group by its move over the last 24 hours of candles. When this one is the worst of them all and down 4% or more, buys it and sells 24 hours later. In the practice weeks, the crypto group's biggest daily loser tended to rise more than the rest over the next day. Speed test only; needs candles of 1 hour or shorter.",
    overlays: () => [],
    decide(I, i, pos) {
      const ext = EXT();
      if (!ext) return needGroup();
      if (tfMins() > 60) return needFast(60);
      if (pos) return checkExits(this, I, i) || wait(`Holding. ${this.st.maxBars - (i - this.st.entryIdx)} candles left.`);
      const e = groupMoves(ext, bars(1440)).get(I.time[i]), me = e && e[ext.current];
      if (me == null) return warm(bars(1440) + 1, i);
      const all = Object.values(e);
      if (all.length < 5) return wait("Too few markets in the group have 24 hours of prices.");
      const rank = 1 + all.filter(x => x < me).length;
      if (rank === 1 && me <= -0.04) return enter(this, i, `The worst of ${all.length} markets over 24 hours (${pct(me)}). Buying the day's biggest loser for 24 hours.`, { maxBars: bars(1440) });
      return wait(`#${rank} from the bottom of ${all.length} over 24 hours (${pct(me)}). Buys the very worst if it's down 4% or more.`);
    } },
  { id: "bottom3day", name: "Bottom Three, 24 Hours", type: "Breadth", color: "#f77f00",
    desc: "A broader version: when this market is one of the group's 3 worst over the last 24 hours of candles and down 3% or more, buys it and sells 24 hours later. Speed test only; needs candles of 1 hour or shorter.",
    overlays: () => [],
    decide(I, i, pos) {
      const ext = EXT();
      if (!ext) return needGroup();
      if (tfMins() > 60) return needFast(60);
      if (pos) return checkExits(this, I, i) || wait(`Holding. ${this.st.maxBars - (i - this.st.entryIdx)} candles left.`);
      const e = groupMoves(ext, bars(1440)).get(I.time[i]), me = e && e[ext.current];
      if (me == null) return warm(bars(1440) + 1, i);
      const all = Object.values(e);
      if (all.length < 5) return wait("Too few markets in the group have 24 hours of prices.");
      const rank = 1 + all.filter(x => x < me).length;
      if (rank <= 3 && me <= -0.03) return enter(this, i, `#${rank} from the bottom of ${all.length} over 24 hours (${pct(me)}). Buying for 24 hours.`, { maxBars: bars(1440) });
      return wait(`#${rank} from the bottom of ${all.length} over 24 hours (${pct(me)}). Buys in the bottom 3 when down 3% or more.`);
    } },
  { id: "leftbehind", name: "Left Behind, 3 Hours", type: "Breadth", color: "#fcbf49",
    desc: "When this market's move over the last 3 hours is at least 1.5 points worse than the group's average move, buys it and sells after 6.5 hours of candles (a stock trading day). In the practice weeks, stocks left behind like this did a little better than the rest over the next day. Speed test only; needs candles of 1 hour or shorter.",
    overlays: () => [],
    decide(I, i, pos) {
      const ext = EXT();
      if (!ext) return needGroup();
      if (tfMins() > 60) return needFast(60);
      if (pos) return checkExits(this, I, i) || wait(`Holding. ${this.st.maxBars - (i - this.st.entryIdx)} candles left.`);
      const e = groupMoves(ext, bars(180)).get(I.time[i]), me = e && e[ext.current];
      if (me == null) return warm(bars(180) + 1, i);
      const all = Object.values(e);
      if (all.length < 5) return wait("Too few markets in the group have prices for this candle.");
      const avg = all.reduce((a, x) => a + x, 0) / all.length;
      if (me - avg <= -0.015) return enter(this, i, `Moved ${pct(me)} over 3 hours while the group averaged ${pct(avg)}. Buying the one left behind.`, { maxBars: bars(390) });
      return wait(`${pct(me)} over 3 hours against the group's ${pct(avg)}. Buys at 1.5 points behind.`);
    } },

  { id: "pairlaggard", name: "Pair Laggard", type: "Breadth", color: "#6d597a",
    desc: "Watches pairs that usually move together: QQQ and SPY, IWM and SPY, DIA and SPY, AMD and NVDA, COIN and MSTR, MSFT and AAPL, GOOGL and META, AVGO and NVDA. When the price ratio between this market and its partner sits 2.5 standard deviations below its average over the last trading day of candles, this one has fallen behind: buys it, and sells once the ratio is back to its average or after 8 hours of candles. In the practice weeks such trades averaged about +0.2% in both halves, mostly from COIN/MSTR and MSFT/AAPL. Speed test only; stocks; needs candles of 1 hour or shorter.",
    overlays: () => [],
    decide(I, i, pos) {
      const ext = EXT();
      if (!ext) return needGroup();
      if (tfMins() > 60) return needFast(60);
      const me = ext.current, n = bars(390), t = I.time[i];
      const partners = PAIRS.filter(p => p.includes(me)).map(p => p[0] === me ? p[1] : p[0]).filter(s => ext.group[s]);
      if (!partners.length) return wait("No usual partner for this market in its group.");
      if (pos) {
        const s = this.st, z = pairZ(ext, me, s.partner, n).get(t);
        if (z != null && z >= 0) return sell(`The price ratio to ${s.partner} is back to its average. Selling.`);
        if (i - s.entryIdx >= bars(480)) return sell("8 hours of candles went by. Selling.");
        return wait(`Holding while behind ${s.partner}${z == null ? "" : ` (${z.toFixed(1)} standard deviations)`}.`);
      }
      let best = null;
      for (const p of partners) {
        const z = pairZ(ext, me, p, n).get(t);
        if (z != null && (!best || z < best.z)) best = { p, z };
      }
      if (!best) return warm(n + 1, i);
      if (best.z <= -2.5) { this.st.partner = best.p; this.st.entryIdx = i; return buy(`Fell behind ${best.p}: their price ratio is ${best.z.toFixed(1)} standard deviations below its average over the last day of candles. Buying.`); }
      return wait(`The price ratio to ${best.p} is ${best.z.toFixed(1)} standard deviations from its average. Buys at −2.5.`);
    } },

  // ----- Kronos plus a dip (speed test only) -----
  { id: "kronosdip", name: "Kronos-Confirmed Dip", type: "AI model", color: "#7209b7",
    desc: "Buys a fall of 2% or more over 3 hours only when Kronos, the AI forecasting model, also expects the next 8 hours to rise by more than a buy and a sale cost. Sells 8 hours later. Speed test only; needs candles of 1 hour or shorter.",
    overlays: () => [],
    decide(I, i, pos) {
      if (tfMins() > 60) return needFast(60);
      const F = kronos(I, i);
      if (!F) return wait("Needs Kronos's forecasts, which only the weekly speed test computes.");
      if (pos) return checkExits(this, I, i) || wait(`Holding. ${this.st.maxBars - (i - this.st.entryIdx)} candles left.`);
      const ch = change(I, i, 180);
      if (ch == null) return warm(bars(180) + 1, i);
      if (F.stale) return wait(`${pct(ch)} over 3 hours. No Kronos forecast from the last hour.`);
      if (ch <= -0.02 && F.next8 > roundTrip()) return enter(this, i, `Down ${pct(-ch)} over 3 hours, and Kronos forecasts ${pct(F.next8, 2)} over the next 8. Buying the dip.`, { maxBars: bars(480) });
      return wait(`${pct(ch)} over 3 hours; Kronos forecasts ${pct(F.next8, 2)} over 8. Needs a 2% dip and a forecast above ${pct(roundTrip(), 2)}.`);
    } },
  { id: "kronosallup", name: "Kronos, Every Horizon Up", type: "AI model", color: "#560bad",
    desc: "Buys only when every part of Kronos's forecast agrees: the next hour up, the next 4 hours up, the next 8 hours up by more than a buy and a sale cost, and no forecast dip along the way deeper than that cost. Sells 8 hours later. Speed test only; needs candles of 1 hour or shorter.",
    overlays: () => [],
    decide(I, i, pos) {
      if (tfMins() > 60) return needFast(60);
      const F = kronos(I, i), cost = roundTrip();
      if (!F) return wait("Needs Kronos's forecasts, which only the weekly speed test computes.");
      if (pos) return checkExits(this, I, i) || wait(`Holding. ${this.st.maxBars - (i - this.st.entryIdx)} candles left.`);
      if (F.stale) return wait("No Kronos forecast from the last hour.");
      const ok = F.next1 > 0 && F.next4 > 0 && F.next8 > cost && F.low8 > -cost;
      const text = `1 hour ${pct(F.next1, 2)}, 4 hours ${pct(F.next4, 2)}, 8 hours ${pct(F.next8, 2)}, deepest dip ${pct(F.low8, 2)}`;
      if (ok) return enter(this, i, `Kronos's forecast agrees at every horizon (${text}). Buying for 8 hours.`, { maxBars: bars(480) });
      return wait(`Kronos's forecast: ${text}. Needs all of them up, 8 hours above ${pct(cost, 2)}, and no dip deeper than that.`);
    } },

  rankBot({ id: "kronostop", name: "Kronos Top Pick", type: "AI model", color: "#9d4edd",
    desc: "Every hour, ranks the group by Kronos's 8-hour forecast. Buys this market when it's the group's top pick and its forecast beats what a buy and a sale cost, and sells 8 hours later unless it still is. Speed test only; needs candles of 1 hour or shorter.",
    pick: (R, cost) => R.top === 1 && R.next8 > cost, label: R => `#${R.top} of ${R.n}` }),
  rankBot({ id: "kronostop3", name: "Kronos Top Three", type: "AI model", color: "#c77dff",
    desc: "The same ranking, but buys any of Kronos's top 3 picks in the group whose 8-hour forecast beats what a buy and a sale cost. Sells 8 hours later unless it's still one of them. Speed test only; needs candles of 1 hour or shorter.",
    pick: (R, cost) => R.top <= 3 && R.next8 > cost, label: R => `#${R.top} of ${R.n}` }),
  rankBot({ id: "kronosbottom", name: "Kronos Bottom Pick", type: "Control", color: "#e0aaff",
    desc: "A control for the Kronos bots: buys the market Kronos likes least (the lowest 8-hour forecast in its group) and sells 8 hours later unless it still is. If Kronos has real skill, this should do worse than Kronos Top Pick. Speed test only; needs candles of 1 hour or shorter.",
    pick: R => R.bottom === 1, label: R => `#${R.bottom} from the bottom of ${R.n}` }),

  // ----- teams: buy when several existing bots agree -----
  teamBot({ id: "kronosteam", name: "Kronos Team", color: "#b388eb", members: ["kronos8h", "kronosstrong", "kronos1h"], buyAt: 2, sellAt: 0,
    desc: "Owns this market while at least 2 of the 3 Kronos bots hold it, and sells once none do. Speed test only (the Kronos bots need its forecasts)." }),
  teamBot({ id: "bouncecrew", name: "Bounce Crew", color: "#e76f51", buyAt: 3, sellAt: 1,
    members: ["drop3h8", "drop3h4", "dip2h8", "plunge1h", "slide6h", "unusualdrop", "dropexits", "capitulation", "dipuptrend", "dropladder", "btcdrop"],
    desc: "A team of the 11 bots that buy big drops and hold for hours. Buys when at least 3 of them hold this market (a deep, confirmed drop) and sells when 1 or none still do. Works wherever its members do." }),
  teamBot({ id: "timerscrew", name: "Best Timers' Vote", color: "#2a9d8f", buyAt: 3, sellAt: 1,
    members: ["grid", "tightgrid", "widegrid", "pivot", "nyreversal", "nyselloff", "dropladder", "martingale", "ladder"],
    desc: "A team of the 9 bots whose buys were best timed in the practice weeks: Grid Trader, Tight Grid, Wide Grid, Pivot Bounce, NY Open Reversal, NY Selloff, Drop Ladder, Martingale Doubler and Ladder Buyer. Buys when at least 3 of them hold this market and sells when 1 or none still do." }),

  // ----- better-timed dips -----
  { id: "calmstorm", name: "Calm After the Storm", type: "Bounce", color: "#457b9d",
    desc: "Doesn't buy a big drop while it's still crashing. After a fall of 3% or more over 3 hours sometime in the last 2 hours, waits until the last hour's candles are less than half as big as during the 3 hours before, then buys and sells 8 hours later. Needs candles of 1 hour or shorter.",
    overlays: () => [],
    decide(I, i, pos) {
      if (tfMins() > 60) return needFast(60);
      if (pos) return checkExits(this, I, i) || wait(`Holding. ${this.st.maxBars - (i - this.st.entryIdx)} candles left.`);
      const k = bars(180), h = bars(60), back = bars(120);
      if (i < k + back + 4 * h) return warm(k + back + 4 * h + 1, i);
      let dropped = false;
      for (let j = i - back; j <= i && !dropped; j++) if (I.close[j] / I.close[j - k] - 1 <= -0.03) dropped = true;
      if (!dropped) return wait("Waiting for a 3% drop over 3 hours.");
      const size = (from, to) => { let s = 0; for (let j = from; j <= to; j++) s += (I.high[j] - I.low[j]) / I.close[j]; return s / (to - from + 1); };
      const now = size(i - h + 1, i), before = size(i - 4 * h + 1, i - h);
      if (now < 0.5 * before) return enter(this, i, `After a 3% drop, the last hour's candles shrank to ${Math.round(now / before * 100)}% of their size before. The storm looks over: buying for 8 hours.`, { maxBars: bars(480) });
      return wait(`A 3% drop happened, but the last hour's candles are still ${Math.round(now / before * 100)}% of their earlier size. Waiting for under 50%.`);
    } },
  { id: "seconddip", name: "Second Dip", type: "Pattern", color: "#1d3557",
    desc: "After a fall of 3% or more over 3 hours makes a low, waits for a bounce of at least 1% and then a return to within 0.5% of that low. If the low holds on the retest, buys, with a stop 1.5% under the low, and sells after 8 hours. Needs candles of 1 hour or shorter.",
    overlays() { return riskLines(this); },
    decide(I, i, pos) {
      if (tfMins() > 60) return needFast(60);
      if (pos) return checkExits(this, I, i) || wait(`${holdingMsg(this)} ${this.st.maxBars - (i - this.st.entryIdx)} candles left.`);
      const k = bars(180), from = i - bars(360), to = i - bars(60);
      if (from - k < 0) return warm(bars(360) + k + 1, i);
      let at = from;
      for (let j = from; j <= to; j++) if (I.low[j] < I.low[at]) at = j;
      const low = I.low[at], fell = I.close[at] / I.close[at - k] - 1;
      let bounce = 0;
      for (let j = at + 1; j < i; j++) bounce = Math.max(bounce, I.high[j] / low - 1);
      const retest = I.low[i] <= low * 1.005 && I.close[i] > low;
      if (fell <= -0.03 && bounce >= 0.01 && retest) return enter(this, i, `Fell ${pct(-fell)} to a low of ${fmtP(low)}, bounced ${pct(bounce)}, and just held that low on a retest. Buying, stop ${fmtP(low * 0.985)}.`, { stop: low * 0.985, maxBars: bars(480) });
      return wait(fell <= -0.03 ? `Low of ${fmtP(low)} after a ${pct(-fell)} fall; bounce so far ${pct(bounce)}. Waiting for a retest that holds.` : "Waiting for a 3% fall over 3 hours to set a low.");
    } },

  // ----- control -----
  { id: "rand24h", name: "Random Entry, 24-Hour Hold", type: "Control", color: "#adb5bd",
    desc: "A control for the 24-hour bots. Buys at random moments (about once a day's worth of candles) and sells 24 hours later, with a different random calendar in every market.",
    overlays: () => [],
    decide(I, i, pos) {
      if (tfMins() > 60) return needFast(60);
      if (pos) return checkExits(this, I, i) || wait(`Holding. ${this.st.maxBars - (i - this.st.entryIdx)} candles left.`);
      if (chance(I, i, 0x3c6ef3) < tfMins() / 1440) return enter(this, i, "Random entry. Selling in 24 hours.", { maxBars: bars(1440) });
      return wait("The dice said not yet.");
    } },
);
})();

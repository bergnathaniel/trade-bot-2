// A fifth batch of Live Arena bots (added 2026-09-13): bots that read more data.
// - Breadth bots look at the other markets in the speed test's group (how many are rising, leaders and laggards).
// - Outside-data bots read signals the speed test collects: VIX, the Crypto Fear & Greed Index, and bitcoin's implied
//   volatility (DVOL) and funding rate.
// - Research bots try intraday effects from published studies, and work anywhere with short enough candles.
// Breadth and outside-data bots only trade inside the weekly speed test (SPEED_TEST.md). None of these bots are in the
// year-long paper tests.
(() => {
"use strict";

// ---------- memo: computed the first time a bot asks, once per set of candles (or per data series) ----------
const memo = new WeakMap();
function get(owner, key, make) {
  let m = memo.get(owner);
  if (!m) memo.set(owner, m = {});
  if (!(key in m)) m[key] = make();
  return m[key];
}
const tfMins = () => +$("tf").value;
const pct = (x, dp = 1) => `${(x * 100).toFixed(dp)}%`;
const warm = (n, i) => wait(`Warming up. Needs ${n} candles (has ${i + 1}).`);
const hhmm = mins => `${String(Math.floor(mins / 60) % 24).padStart(2, "0")}:${String(mins % 60).padStart(2, "0")}`;
const needFast = tf => wait(`Needs candles of ${tf} minutes or shorter.`);
const EXT = () => window.SPEED_EXT || null;
const needGroup = () => wait("Needs the other markets in its group, which only the weekly speed test provides.");
const needOutside = what => wait(`Needs ${what}, which only the weekly speed test collects.`);
const NY_DATE = new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York" });
const nyDate = t => NY_DATE.format(new Date((t + OFF) * 1000));
const utcMins = t => { const d = new Date((t + OFF) * 1000); return d.getUTCHours() * 60 + d.getUTCMinutes(); };

function lastAtOrBefore(rows, t) {   // index of the last row stamped at or before t, or -1
  let lo = 0, hi = rows.length - 1, found = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (rows[mid].time <= t) { found = mid; lo = mid + 1; } else hi = mid - 1;
  }
  return found;
}
function seriesInfo(rows) {   // a market's or signal's closes, its candle index by time, and a few averages
  return get(rows, "info", () => {
    const close = rows.map(r => r.close);
    return { close, byTime: new Map(rows.map((r, j) => [r.time, j])), ema20: ema(close, 20), ema24: ema(close, 24), ema50: ema(close, 50) };
  });
}
const outside = name => { const ext = EXT(); return ext && ext.outside ? ext.outside[name] : null; };

// ---------- the group: every market in the speed test's crypto or stock group, lined up by candle time ----------
function groupTable(ext) {
  return get(ext.group, "table", () => {
    const markets = ext.symbols.map(s => ({ s, ...seriesInfo(ext.group[s]) }));
    const times = [...new Set(ext.symbols.flatMap(s => ext.group[s].map(r => r.time)))].sort((a, b) => a - b);
    const table = new Map();
    for (const t of times) {
      let above = 0, counted = 0, sum1 = 0, moves = 0;
      const rets = {};
      for (const M of markets) {
        const j = M.byTime.get(t);
        if (j == null) continue;
        if (M.ema20[j] != null) { counted++; if (M.close[j] > M.ema20[j]) above++; }
        if (j >= 1) { sum1 += M.close[j] / M.close[j - 1] - 1; moves++; }
        const back = k => j >= k ? M.close[j] / M.close[j - k] - 1 : null;
        rets[M.s] = { r1: back(1), r6: back(6), r12: back(12), r24: back(24) };
      }
      table.set(t, { breadth: counted >= 3 ? above / counted : null, avg1: moves >= 3 ? sum1 / moves : null, rets });
    }
    return { table, times, index: new Map(times.map((t, k) => [t, k])) };
  });
}
// For each candle time and market: the average move of the coming New York half-hour over that market's previous
// 10 days (Heston, Korajczyk & Sadka found returns tend to repeat in the same half-hour on later days).
function slotTable(ext, tf) {
  return get(ext.group, `slots${tf}`, () => {
    const out = new Map();
    for (const s of ext.symbols) {
      const rows = ext.group[s], history = new Map();
      let day = null, today = new Map();
      for (let j = 0; j < rows.length; j++) {
        const t = rows[j].time, d = nyDate(t), mins = nyClock(t + OFF).mins;
        if (d !== day) {
          for (const [slot, v] of today) { const h = history.get(slot) || []; h.push(v); if (h.length > 10) h.shift(); history.set(slot, h); }
          today = new Map();
          day = d;
        }
        if (j > 0) { const slot = Math.floor(mins / 30); today.set(slot, (today.get(slot) || 0) + rows[j].close / rows[j - 1].close - 1); }
        const h = history.get(Math.floor(((mins + tf) % 1440) / 30));
        if (!out.has(t)) out.set(t, {});
        if (h && h.length >= 5) out.get(t)[s] = h.reduce((a, x) => a + x, 0) / h.length;
      }
    }
    return out;
  });
}

// ---------- days: stock sessions (New York) and crypto days (UTC) ----------
// For stock candles: the day's opening price, yesterday's close, today's closes at 10:00, 15:00 and 15:30 New York time,
// the first half hour's volume against the previous 5 days, and whether a candle is the day's last.
function stockDays(I, tf) {
  return get(I, `stockdays${tf}`, () => {
    const n = I.close.length, blank = () => Array(n).fill(null);
    const D = { stock: Array(n).fill(false), first: Array(n).fill(0), last: Array(n).fill(false), endMins: Array(n).fill(0), dayOpen: blank(),
                prevClose: blank(), at1000: blank(), at1500: blank(), at1530: blank(), vol30: blank(), avgVol30: blank() };
    let day = null, start = 0, isStock = false, lastClose = null, prev = null, c10 = null, c15 = null, c1530 = null, v30 = 0, done30 = false;
    const past30 = [];
    for (let i = 0; i < n; i++) {
      const d = nyDate(I.time[i]), startMins = nyClock(I.time[i] + OFF).mins, endMins = startMins + tf;
      if (d !== day) {
        if (day !== null) { prev = lastClose; if (done30) { past30.push(v30); if (past30.length > 5) past30.shift(); } }
        day = d; start = i; isStock = startMins >= 540; c10 = c15 = c1530 = null; v30 = 0; done30 = false;
      }
      if (startMins >= 570 && startMins < 600) v30 += I.vol[i];
      if (endMins >= 600) done30 = true;
      if (endMins === 600) c10 = I.close[i];
      if (endMins === 900) c15 = I.close[i];
      if (endMins === 930) c1530 = I.close[i];
      lastClose = I.close[i];
      D.stock[i] = isStock; D.first[i] = start; D.last[i] = isStock && endMins >= 960; D.endMins[i] = endMins; D.dayOpen[i] = I.open[start];
      D.prevClose[i] = prev; D.at1000[i] = c10; D.at1500[i] = c15; D.at1530[i] = c1530;
      D.vol30[i] = done30 ? v30 : null;
      D.avgVol30[i] = past30.length >= 3 ? past30.reduce((a, x) => a + x, 0) / past30.length : null;
    }
    return D;
  });
}
// For crypto candles: the UTC day's opening price (only when the data has the midnight candle) and its price at 00:30.
function cryptoDays(I, tf) {
  return get(I, `cryptodays${tf}`, () => {
    const n = I.close.length, open = Array(n).fill(null), at0030 = Array(n).fill(null), endMins = Array(n).fill(0);
    let day = null, o = null, c = null;
    for (let i = 0; i < n; i++) {
      const d = new Date((I.time[i] + OFF) * 1000).toISOString().slice(0, 10), start = utcMins(I.time[i]);
      if (d !== day) { day = d; o = start === 0 ? I.open[i] : null; c = null; }
      if (start + tf === 30) c = I.close[i];
      open[i] = o; at0030[i] = c; endMins[i] = start + tf;
    }
    return { open, at0030, endMins };
  });
}
function fastSignals(I) {
  return get(I, "fastsignals", () => {
    const e3 = ema(I.close, 3), e8 = ema(I.close, 8), f = ema(I.close, 5), s = ema(I.close, 13);
    const macd = I.close.map((_, j) => f[j] == null || s[j] == null ? null : f[j] - s[j]);
    return { e3, e8, macd, sig: ema(macd, 4), st: supertrend(I.high, I.low, I.close, atr(I.high, I.low, I.close, 7), 2) };
  });
}

// ---------- the bots ----------
BOTS.push(
  // ----- breadth: the rest of the group (speed test only) -----
  { id: "breadththrust", name: "Breadth Thrust", type: "Breadth", color: "#ffb703",
    desc: "Breadth is the share of the group's markets trading above their 20-candle EMA. A 'breadth thrust' is when it jumps from 40% or less to 80% or more within 10 candles: nearly everything turning up at once. Buys that if this market is above its EMA 20 too, and sells when breadth drops under 50%. Speed test only.",
    overlays: I => [["EMA 20", I.ema20, "#ffb703"]],
    decide(I, i, pos) {
      const ext = EXT();
      if (!ext) return needGroup();
      const G = groupTable(ext), k = G.index.get(I.time[i]), row = G.table.get(I.time[i]);
      if (k == null || k < 12 || row.breadth == null) return warm(13, i);
      const b = row.breadth;
      if (pos && b < 0.5) return sell(`Only ${pct(b, 0)} of the group is above its EMA 20 now. Selling.`);
      if (pos) return wait(`Holding. ${pct(b, 0)} of the group is above its EMA 20.`);
      let low = 1;
      for (let m = k - 10; m < k; m++) { const x = G.table.get(G.times[m]).breadth; if (x != null) low = Math.min(low, x); }
      if (b >= 0.8 && low <= 0.4 && I.close[i] > I.ema20[i]) return buy(`Breadth thrust: the share of the group above its EMA 20 jumped from ${pct(low, 0)} to ${pct(b, 0)} within 10 candles. Buying.`);
      return wait(`${pct(b, 0)} of the group is above its EMA 20. Needs a jump from 40% or less to 80% or more.`);
    } },
  { id: "breadthtrend", name: "Breadth Trend", type: "Breadth", color: "#fb8500",
    desc: "Owns this market while most of the group is healthy (over 65% of markets above their EMA 20) and this market is above its own EMA 20. Sells when breadth falls under 50% or this market drops under its EMA. Speed test only.",
    overlays: I => [["EMA 20", I.ema20, "#fb8500"]],
    decide(I, i, pos) {
      const ext = EXT();
      if (!ext) return needGroup();
      const row = groupTable(ext).table.get(I.time[i]), c = I.close[i], e = I.ema20[i];
      if (!row || row.breadth == null || e == null) return warm(21, i);
      const b = row.breadth;
      if (!pos && b > 0.65 && c > e) return buy(`${pct(b, 0)} of the group is above its EMA 20, and so is this market. Buying.`);
      if (pos && (b < 0.5 || c < e)) return sell(b < 0.5 ? `Breadth fell to ${pct(b, 0)}. Selling.` : "Dropped under its EMA 20. Selling.");
      return wait(`Breadth ${pct(b, 0)}, ${c > e ? "above" : "below"} its EMA 20. ${pos ? "Holding." : "Needs breadth over 65% and a close above the EMA."}`);
    } },
  { id: "groupleader", name: "Group Leader", type: "Breadth", color: "#219ebc",
    desc: "Ranks every market in the group by its return over the last 12 candles. Owns this market while it's one of the top 3 and sells once it falls out of the top 6. Speed test only.",
    overlays: () => [],
    decide(I, i, pos) {
      const ext = EXT();
      if (!ext) return needGroup();
      const row = groupTable(ext).table.get(I.time[i]), me = row && row.rets[ext.current];
      if (!me || me.r12 == null) return warm(13, i);
      const all = Object.values(row.rets).map(x => x.r12).filter(x => x != null), rank = 1 + all.filter(x => x > me.r12).length;
      if (!pos && rank <= 3) return buy(`Ranked #${rank} of ${all.length} over the last 12 candles (${pct(me.r12, 2)}). Buying a leader.`);
      if (pos && rank > 6) return sell(`Slipped to #${rank} of ${all.length}. Selling.`);
      return wait(`Ranked #${rank} of ${all.length} over 12 candles. ${pos ? "Holding while in the top 6." : "Buys in the top 3."}`);
    } },
  { id: "laggard", name: "Laggard Catch-Up", type: "Breadth", color: "#8ecae6",
    desc: "When the group as a whole rose more than 0.3% over the last 6 candles but this market is one of the 3 worst and at least 0.3 points behind the average, buys it, betting it catches up. Sells after 6 candles. Speed test only.",
    overlays() { return riskLines(this); },
    decide(I, i, pos) {
      const ext = EXT();
      if (!ext) return needGroup();
      if (pos) return checkExits(this, I, i) || wait(`Holding. ${6 - (i - this.st.entryIdx)} candles left.`);
      const row = groupTable(ext).table.get(I.time[i]), me = row && row.rets[ext.current];
      if (!me || me.r6 == null) return warm(7, i);
      const all = Object.values(row.rets).map(x => x.r6).filter(x => x != null), avg = all.reduce((a, x) => a + x, 0) / all.length;
      const rank = 1 + all.filter(x => x < me.r6).length;
      if (avg > 0.003 && me.r6 < avg - 0.003 && rank <= 3) return enter(this, i, `The group rose ${pct(avg, 2)} over 6 candles but this only ${pct(me.r6, 2)} (#${rank} from the bottom). Betting it catches up.`, { maxBars: 6 });
      return wait(`Group ${pct(avg, 2)} over 6 candles, this ${pct(me.r6, 2)}.`);
    } },
  { id: "groupflush", name: "Group Flush Buyer", type: "Breadth", color: "#023047",
    desc: "When the whole group drops together far more than usual in one candle (the average move more than 3 standard deviations below normal), buys the market-wide flush. Stop 1.5 ATRs lower, sells after 6 candles. Speed test only.",
    overlays() { return riskLines(this); },
    decide(I, i, pos) {
      const ext = EXT();
      if (!ext) return needGroup();
      if (pos) return checkExits(this, I, i) || wait(`${holdingMsg(this)} ${6 - (i - this.st.entryIdx)} candles left.`);
      const G = groupTable(ext), k = G.index.get(I.time[i]), a = I.atr14[i];
      if (k == null || k < 101 || a == null) return warm(102, i);
      const now = G.table.get(I.time[i]).avg1;
      let s = 0, q = 0, n = 0;
      for (let m = k - 100; m < k; m++) { const x = G.table.get(G.times[m]).avg1; if (x != null) { s += x; q += x * x; n++; } }
      const mean = s / n, sd = Math.sqrt(Math.max(q / n - mean * mean, 0)), z = sd > 0 && now != null ? (now - mean) / sd : 0;
      if (z < -3) return enter(this, i, `The whole group dropped together: a ${(-z).toFixed(1)}-sigma move. Buying the flush.`, { stop: I.close[i] - 1.5 * a, maxBars: 6 });
      return wait(`The group's last move was ${z.toFixed(1)} sigma. Needs −3.`);
    } },
  { id: "strongergroup", name: "Stronger Than the Group", type: "Breadth", color: "#2a9d8f",
    desc: "Owns this market while the group's typical market is up over the last 24 candles and this one is up more than that. Sells when either stops being true. Speed test only.",
    overlays: () => [],
    decide(I, i, pos) {
      const ext = EXT();
      if (!ext) return needGroup();
      const row = groupTable(ext).table.get(I.time[i]), me = row && row.rets[ext.current];
      if (!me || me.r24 == null) return warm(25, i);
      const all = Object.values(row.rets).map(x => x.r24).filter(x => x != null).sort((a, b) => a - b);
      const median = all.length % 2 ? all[all.length >> 1] : (all[all.length / 2 - 1] + all[all.length / 2]) / 2, good = median > 0 && me.r24 > median;
      if (!pos && good) return buy(`Up ${pct(me.r24, 2)} over 24 candles, ahead of the group's typical ${pct(median, 2)}. Buying.`);
      if (pos && !good) return sell(median <= 0 ? "The group turned down. Selling." : "Fell behind the group. Selling.");
      return wait(`This ${pct(me.r24, 2)}, the group's typical market ${pct(median, 2)} over 24 candles.`);
    } },
  { id: "decoupled", name: "Decoupled Riser", type: "Breadth", color: "#264653",
    desc: "Most markets move together. When this one has been moving on its own (correlation with the group's average move under 0.3 over 50 candles) and it's rising and above its EMA 20, something specific may be driving it. Buys that and sells a close under the EMA 20. Speed test only.",
    overlays: I => [["EMA 20", I.ema20, "#6c9a8b"]],
    decide(I, i, pos) {
      const ext = EXT();
      if (!ext) return needGroup();
      const c = I.close[i], e = I.ema20[i];
      if (pos && c < e) return sell("Closed under its EMA 20. Selling.");
      if (pos) return wait("Holding while above its EMA 20.");
      const G = groupTable(ext), k = G.index.get(I.time[i]), me = G.table.get(I.time[i])?.rets[ext.current];
      if (k == null || k < 51 || !me || me.r12 == null || e == null) return warm(52, i);
      const xs = [], ys = [];
      for (let m = k - 49; m <= k; m++) { const r = G.table.get(G.times[m]); const mine = r.rets[ext.current]; if (mine && mine.r1 != null && r.avg1 != null) { xs.push(mine.r1); ys.push(r.avg1); } }
      if (xs.length < 30) return wait("Not enough overlapping candles with the group.");
      const mx = xs.reduce((a, x) => a + x, 0) / xs.length, my = ys.reduce((a, x) => a + x, 0) / ys.length;
      let sxy = 0, sxx = 0, syy = 0;
      for (let j = 0; j < xs.length; j++) { sxy += (xs[j] - mx) * (ys[j] - my); sxx += (xs[j] - mx) ** 2; syy += (ys[j] - my) ** 2; }
      const corr = sxx > 0 && syy > 0 ? sxy / Math.sqrt(sxx * syy) : 1;
      if (corr < 0.3 && me.r12 > 0 && c > e) return buy(`Moving on its own (correlation with the group ${corr.toFixed(2)}) and rising (${pct(me.r12, 2)} over 12 candles). Buying.`);
      return wait(`Correlation with the group ${corr.toFixed(2)}. Needs under 0.3 while rising.`);
    } },
  { id: "slotleader", name: "Same Half-Hour Leaders", type: "Breadth", color: "#e9c46a",
    desc: "Research by Heston, Korajczyk and Sadka found stock returns tend to repeat in the same half hour on later days. For the coming half hour (New York time), ranks the group by how each market did in that half hour over its previous 10 days. Owns this market while it's in the top 3 with a positive average, and sells when it falls out of the top 6. Speed test only; needs candles of 30 minutes or shorter.",
    overlays: () => [],
    decide(I, i, pos) {
      const ext = EXT(), tf = tfMins();
      if (!ext) return needGroup();
      if (tf > 30) return needFast(30);
      const avgs = slotTable(ext, tf).get(I.time[i]) || {}, me = avgs[ext.current];
      if (me == null) return pos ? sell("No history for the coming half hour. Selling.") : wait("Needs 5 days of history for the coming half hour.");
      const all = Object.values(avgs), rank = 1 + all.filter(x => x > me).length;
      if (!pos && rank <= 3 && me > 0) return buy(`In the coming half hour, this market averaged ${pct(me, 2)} over its last 10 days, #${rank} of ${all.length}. Buying.`);
      if (pos && (rank > 6 || me <= 0)) return sell(`For the coming half hour it ranks #${rank} (${pct(me, 2)}). Selling.`);
      return wait(`Coming half hour: #${rank} of ${all.length} (${pct(me, 2)}). ${pos ? "Holding." : "Buys in the top 3 with a positive average."}`);
    } },
  { id: "allclear", name: "All Clear", type: "Breadth", color: "#f4a261",
    desc: "Waits for three things at once: most of the group is healthy (breadth over 60%), this market is above its EMA 20, and the outside signal is calm (for stocks VIX under its 50-candle average; for crypto the Fear & Greed Index between 30 and 75). Sells when any of them fails. Speed test only.",
    overlays: I => [["EMA 20", I.ema20, "#f4a261"]],
    decide(I, i, pos) {
      const ext = EXT();
      if (!ext) return needGroup();
      const row = groupTable(ext).table.get(I.time[i]), e = I.ema20[i];
      if (!row || row.breadth == null || e == null) return warm(21, i);
      let calm = null, what = "";
      const vix = outside("vix"), fng = outside("fear_greed");
      if (vix) { const V = seriesInfo(vix), k = V.byTime.get(I.time[i]); if (k != null && V.ema50[k] != null) { calm = V.close[k] < V.ema50[k]; what = `VIX ${V.close[k].toFixed(2)} vs its average ${V.ema50[k].toFixed(2)}`; } }
      else if (fng) { const k = lastAtOrBefore(fng, I.time[i] - 86400); if (k >= 0) { const v = fng[k].close; calm = v >= 30 && v <= 75; what = `Fear & Greed ${v}`; } }
      if (calm == null) return needOutside("VIX or Fear & Greed readings");
      const ok = row.breadth > 0.6 && I.close[i] > e && calm;
      if (!pos && ok) return buy(`All clear: breadth ${pct(row.breadth, 0)}, above its EMA 20, ${what}. Buying.`);
      if (pos && !(row.breadth >= 0.5 && I.close[i] > e && calm)) return sell(`Not all clear anymore (breadth ${pct(row.breadth, 0)}, ${what}). Selling.`);
      return wait(`Breadth ${pct(row.breadth, 0)}, ${I.close[i] > e ? "above" : "below"} EMA 20, ${what}.`);
    } },

  // ----- outside data (speed test only) -----
  { id: "vixfade", name: "VIX Spike Fade", type: "Outside data", color: "#e63946",
    desc: "VIX is the stock market's 'fear gauge'. When it jumps 7% or more within 6 candles while this stock falls, buys, betting the fear fades. Sells when VIX eases back under its 20-candle average, at a stop 1.5 ATRs lower, or after 12 candles. Stocks; speed test only.",
    overlays() { return riskLines(this); },
    decide(I, i, pos) {
      const vix = outside("vix");
      if (!vix) return needOutside("VIX prices");
      const V = seriesInfo(vix), k = V.byTime.get(I.time[i]);
      if (pos && k != null && V.ema20[k] != null && V.close[k] < V.ema20[k]) return sell(`VIX eased back under its 20-candle average (${V.close[k].toFixed(2)}). Selling.`);
      if (pos) return checkExits(this, I, i) || wait(holdingMsg(this));
      const a = I.atr14[i];
      if (k == null || k < 6 || i < 6 || a == null) return wait("No VIX reading for this candle yet.");
      const jump = V.close[k] / V.close[k - 6] - 1, drop = I.close[i] / I.close[i - 6] - 1;
      if (jump >= 0.07 && drop < 0) return enter(this, i, `VIX jumped ${pct(jump)} in 6 candles while this fell ${pct(drop)}. Betting the fear fades.`, { stop: I.close[i] - 1.5 * a, maxBars: 12 });
      return wait(`VIX ${pct(jump)} over 6 candles. Needs a 7% jump while this falls.`);
    } },
  { id: "vixcalm", name: "Calm Market Trend", type: "Outside data", color: "#457b9d",
    desc: "Owns this stock while VIX is below its 50-candle average (a calm market) and the stock is above its own 50-candle EMA. Sells when VIX rises above its average or the stock drops under its EMA. Stocks; speed test only.",
    overlays: I => [["EMA 50", I.ema50, "#457b9d"]],
    decide(I, i, pos) {
      const vix = outside("vix");
      if (!vix) return needOutside("VIX prices");
      const V = seriesInfo(vix), k = V.byTime.get(I.time[i]), e = I.ema50[i];
      if (k == null || V.ema50[k] == null || e == null) return warm(50, i);
      const calm = V.close[k] < V.ema50[k], up = I.close[i] > e;
      if (!pos && calm && up) return buy(`VIX (${V.close[k].toFixed(2)}) is under its average and the stock is above its EMA 50. Buying.`);
      if (pos && (!calm || !up)) return sell(!calm ? `VIX rose above its average (${V.ema50[k].toFixed(2)}). Selling.` : "Dropped under its EMA 50. Selling.");
      return wait(`VIX ${calm ? "calm" : "elevated"}, stock ${up ? "above" : "below"} its EMA 50.`);
    } },
  { id: "vixturn", name: "VIX Turn", type: "Outside data", color: "#1d3557",
    desc: "When VIX has just hit its highest close of the last 60 candles and then closes lower twice in a row, fear may have peaked. Buys, with a stop 1.5 ATRs lower, and sells after 24 candles. Stocks; speed test only.",
    overlays() { return riskLines(this); },
    decide(I, i, pos) {
      const vix = outside("vix");
      if (!vix) return needOutside("VIX prices");
      if (pos) return checkExits(this, I, i) || wait(`${holdingMsg(this)} ${24 - (i - this.st.entryIdx)} candles left.`);
      const V = seriesInfo(vix), k = V.byTime.get(I.time[i]), a = I.atr14[i];
      if (k == null || k < 63 || a == null) return wait("Needs 60 candles of VIX readings.");
      let peak = k - 60;
      for (let m = k - 60; m <= k; m++) if (V.close[m] >= V.close[peak]) peak = m;
      const turned = peak >= k - 3 && peak <= k - 2 && V.close[k] < V.close[k - 1] && V.close[k - 1] < V.close[k - 2];
      if (turned) return enter(this, i, `VIX peaked at ${V.close[peak].toFixed(2)}, its highest in 60 candles, and has closed lower twice since. Buying.`, { stop: I.close[i] - 1.5 * a, maxBars: 24 });
      return wait(`VIX ${V.close[k].toFixed(2)}. Waiting for a 60-candle high followed by two lower closes.`);
    } },
  { id: "fearbuyer", name: "Extreme Fear Buyer", type: "Outside data", color: "#9d0208",
    desc: "The Crypto Fear & Greed Index runs from 0 (extreme fear) to 100 (extreme greed). Buys when yesterday's reading was 25 or lower and sells once it's back to 50. It uses yesterday's reading so it never peeks. Crypto; speed test only.",
    overlays: () => [],
    decide(I, i, pos) {
      const fng = outside("fear_greed");
      if (!fng) return needOutside("the Fear & Greed Index");
      const k = lastAtOrBefore(fng, I.time[i] - 86400);
      if (k < 0) return wait("No Fear & Greed reading yet.");
      const v = fng[k].close;
      if (!pos && v <= 25) return buy(`Yesterday's Fear & Greed reading was ${v}: extreme fear. Buying.`);
      if (pos && v >= 50) return sell(`Fear & Greed is back to ${v}. Selling.`);
      return wait(`Fear & Greed ${v}. ${pos ? "Holding until 50." : "Buys at 25 or lower."}`);
    } },
  { id: "greedguard", name: "Greed Guard", type: "Outside data", color: "#6a040f",
    desc: "Owns this coin while the Fear & Greed Index is in the middle (30 to 75) and the coin is above its 50-candle EMA. Sells when greed gets extreme (over 80) or the coin drops under its EMA. Crypto; speed test only.",
    overlays: I => [["EMA 50", I.ema50, "#c1121f"]],
    decide(I, i, pos) {
      const fng = outside("fear_greed");
      if (!fng) return needOutside("the Fear & Greed Index");
      const k = lastAtOrBefore(fng, I.time[i] - 86400), e = I.ema50[i];
      if (k < 0 || e == null) return warm(50, i);
      const v = fng[k].close, up = I.close[i] > e;
      if (!pos && v >= 30 && v <= 75 && up) return buy(`Fear & Greed ${v} (neither panic nor euphoria) and above its EMA 50. Buying.`);
      if (pos && (v > 80 || !up)) return sell(v > 80 ? `Fear & Greed hit ${v}: extreme greed. Selling.` : "Dropped under its EMA 50. Selling.");
      return wait(`Fear & Greed ${v}, ${up ? "above" : "below"} its EMA 50.`);
    } },
  { id: "sentimentturn", name: "Sentiment Turn", type: "Outside data", color: "#bc6c25",
    desc: "Buys when the Fear & Greed Index has risen 10 points or more over 3 days (mood improving fast) and sells when it has fallen 10 points or more over 3 days. Crypto; speed test only.",
    overlays: () => [],
    decide(I, i, pos) {
      const fng = outside("fear_greed");
      if (!fng) return needOutside("the Fear & Greed Index");
      const now = lastAtOrBefore(fng, I.time[i] - 86400), before = lastAtOrBefore(fng, I.time[i] - 4 * 86400);
      if (now < 0 || before < 0) return wait("Needs 4 days of Fear & Greed readings.");
      const change = fng[now].close - fng[before].close;
      if (!pos && change >= 10) return buy(`Fear & Greed rose ${change} points in 3 days (to ${fng[now].close}). Buying.`);
      if (pos && change <= -10) return sell(`Fear & Greed fell ${-change} points in 3 days. Selling.`);
      return wait(`Fear & Greed changed ${change >= 0 ? "+" : ""}${change} over 3 days.`);
    } },
  { id: "volcrush", name: "Implied Vol Crush", type: "Outside data", color: "#3a0ca3",
    desc: "DVOL is bitcoin's implied volatility: how big a move options traders are pricing in. Owns this coin while DVOL is under its 24-hour average and still falling, and the coin is above its 50-candle EMA. Sells when DVOL climbs back above its average. Crypto; speed test only.",
    overlays: I => [["EMA 50", I.ema50, "#4361ee"]],
    decide(I, i, pos) {
      const dvol = outside("dvol_btc");
      if (!dvol) return needOutside("bitcoin's implied volatility");
      const D = seriesInfo(dvol), k = lastAtOrBefore(dvol, I.time[i] + tfMins() * 60 - 3600), e = I.ema50[i];
      if (k < 3 || D.ema24[k] == null || e == null) return warm(50, i);
      const v = D.close[k], avg = D.ema24[k];
      if (!pos && v < avg && v < D.close[k - 3] && I.close[i] > e) return buy(`Implied volatility ${v.toFixed(1)} is under its 24-hour average (${avg.toFixed(1)}) and falling. Calm is spreading: buying.`);
      if (pos && v > avg) return sell(`Implied volatility rose above its 24-hour average (${avg.toFixed(1)}). Selling.`);
      return wait(`DVOL ${v.toFixed(1)} vs its 24-hour average ${avg.toFixed(1)}.`);
    } },
  { id: "volspike", name: "Implied Vol Spike Buyer", type: "Outside data", color: "#7209b7",
    desc: "When bitcoin's implied volatility jumps 12% or more in 24 hours while this coin has fallen more than 3% over the same day, options traders are panicking. Buys, with a stop 2 ATRs lower, and sells after a day's worth of candles. Crypto; speed test only.",
    overlays() { return riskLines(this); },
    decide(I, i, pos) {
      const dvol = outside("dvol_btc"), tf = tfMins(), day = Math.round(1440 / tf);
      if (!dvol) return needOutside("bitcoin's implied volatility");
      if (pos) return checkExits(this, I, i) || wait(`${holdingMsg(this)} ${day - (i - this.st.entryIdx)} candles left.`);
      const end = I.time[i] + tf * 60, k = lastAtOrBefore(dvol, end - 3600), k24 = lastAtOrBefore(dvol, end - 3600 - 86400), a = I.atr14[i];
      if (k < 0 || k24 < 0 || i < day || a == null) return warm(day + 1, i);
      const jump = dvol[k].close / dvol[k24].close - 1, move = I.close[i] / I.close[i - day] - 1;
      if (jump >= 0.12 && move < -0.03) return enter(this, i, `Implied volatility jumped ${pct(jump)} in a day while this coin fell ${pct(move)}. Buying the panic.`, { stop: I.close[i] - 2 * a, maxBars: day });
      return wait(`DVOL ${pct(jump)} over 24 hours, this coin ${pct(move)}.`);
    } },
  { id: "fundingsqueeze", name: "Negative Funding Squeeze", type: "Outside data", color: "#2d6a4f",
    desc: "On bitcoin's perpetual swaps, a negative funding rate means traders betting on a fall are paying to hold those bets: shorts are crowded. Buys when the latest funding rate is negative and this coin is above its EMA 20, betting on a squeeze. Sells when funding turns clearly positive or the coin drops under its EMA. Crypto; speed test only.",
    overlays: I => [["EMA 20", I.ema20, "#52b788"]],
    decide(I, i, pos) {
      const funding = outside("funding_btc");
      if (!funding) return needOutside("bitcoin's funding rate");
      const k = lastAtOrBefore(funding, I.time[i] + tfMins() * 60), e = I.ema20[i];
      if (k < 0 || e == null) return warm(21, i);
      const f = funding[k].close, up = I.close[i] > e;
      if (!pos && f < 0 && up) return buy(`Funding is negative (${pct(f, 4)} per 8 hours): shorts are crowded, and this coin is above its EMA 20. Buying.`);
      if (pos && (f > 0.0001 || !up)) return sell(f > 0.0001 ? `Funding turned positive (${pct(f, 4)}). Selling.` : "Dropped under its EMA 20. Selling.");
      return wait(`Funding ${pct(f, 4)} per 8 hours, ${up ? "above" : "below"} EMA 20.`);
    } },
  { id: "fundingguard", name: "Funding Guard", type: "Outside data", color: "#40916c",
    desc: "Owns this coin while bitcoin's funding rate is normal (between −0.005% and +0.02% per 8 hours) and the coin is above its 50-candle EMA. Sells when funding runs hot (over 0.03%, too many leveraged buyers) or the coin drops under its EMA. Crypto; speed test only.",
    overlays: I => [["EMA 50", I.ema50, "#40916c"]],
    decide(I, i, pos) {
      const funding = outside("funding_btc");
      if (!funding) return needOutside("bitcoin's funding rate");
      const k = lastAtOrBefore(funding, I.time[i] + tfMins() * 60), e = I.ema50[i];
      if (k < 0 || e == null) return warm(50, i);
      const f = funding[k].close, up = I.close[i] > e;
      if (!pos && f >= -0.00005 && f <= 0.0002 && up) return buy(`Funding is normal (${pct(f, 4)}) and the coin is above its EMA 50. Buying.`);
      if (pos && (f > 0.0003 || !up)) return sell(f > 0.0003 ? `Funding ran hot (${pct(f, 4)}). Selling.` : "Dropped under its EMA 50. Selling.");
      return wait(`Funding ${pct(f, 4)}, ${up ? "above" : "below"} EMA 50.`);
    } },

  // ----- published intraday effects -----
  { id: "intramom", name: "Intraday Momentum", type: "Research", color: "#ffd166",
    desc: "From Gao, Han, Li and Zhou (Journal of Financial Economics, 2018): for the S&P 500 ETF, the market's move from the previous close to 10 am tends to predict the last half hour. If the stock rose from yesterday's close to 10 am, buys at 3:30 pm New York time and sells at the close. Stocks; needs candles of 30 minutes or shorter.",
    overlays: () => [],
    decide(I, i, pos) {
      const tf = tfMins();
      if (tf > 30) return needFast(30);
      const D = stockDays(I, tf);
      if (pos && (D.last[i] || !D.stock[i])) return sell("The closing bell. Selling.");
      if (pos) return wait("Holding into the close.");
      if (!D.stock[i]) return wait("Stocks only.");
      if (D.endMins[i] !== 930) return wait(`Trades at 3:30 pm New York time. It's ${hhmm(D.endMins[i])}.`);
      if (D.prevClose[i] == null || D.at1000[i] == null) return wait("Needs yesterday's close and today's 10 am price.");
      const first = D.at1000[i] / D.prevClose[i] - 1;
      if (first > 0) return buy(`From yesterday's close to 10 am it rose ${pct(first, 2)}. The study says the last half hour tends to follow: buying for the close.`);
      return wait(`The first half hour was ${pct(first, 2)}, not up. No trade today.`);
    } },
  { id: "intramom2", name: "Intraday Momentum, Two Signals", type: "Research", color: "#ef476f",
    desc: "The same study found the prediction gets stronger when the half hour from 3 to 3:30 pm agrees with the first half hour. Buys at 3:30 pm only if both were up, and sells at the close. Stocks; needs candles of 30 minutes or shorter.",
    overlays: () => [],
    decide(I, i, pos) {
      const tf = tfMins();
      if (tf > 30) return needFast(30);
      const D = stockDays(I, tf);
      if (pos && (D.last[i] || !D.stock[i])) return sell("The closing bell. Selling.");
      if (pos) return wait("Holding into the close.");
      if (!D.stock[i]) return wait("Stocks only.");
      if (D.endMins[i] !== 930) return wait(`Trades at 3:30 pm New York time. It's ${hhmm(D.endMins[i])}.`);
      if (D.prevClose[i] == null || D.at1000[i] == null || D.at1500[i] == null || D.at1530[i] == null) return wait("Needs yesterday's close and today's 10 am, 3 pm and 3:30 pm prices.");
      const first = D.at1000[i] / D.prevClose[i] - 1, late = D.at1530[i] / D.at1500[i] - 1;
      if (first > 0 && late > 0) return buy(`The first half hour (${pct(first, 2)}) and 3 to 3:30 pm (${pct(late, 2)}) were both up. Buying for the close.`);
      return wait(`First half hour ${pct(first, 2)}, 3 to 3:30 pm ${pct(late, 2)}. Needs both up.`);
    } },
  { id: "cryptomom", name: "Crypto Intraday Momentum", type: "Research", color: "#f77f00",
    desc: "Shen, Urquhart and Wang (Financial Review, 2022) found bitcoin's first half hour predicts its last half hour, using trading volume to define the day. This simpler version uses the UTC day: if the coin rose from midnight to 00:30 UTC, buys at 23:30 UTC and sells at midnight. Crypto; needs candles of 30 minutes or shorter.",
    overlays: () => [],
    decide(I, i, pos) {
      const tf = tfMins();
      if (tf > 30) return needFast(30);
      const C = cryptoDays(I, tf);
      if (pos && C.endMins[i] >= 1440) return sell("Midnight UTC. Selling.");
      if (pos) return wait("Holding until midnight UTC.");
      if (C.open[i] == null) return wait("Needs the UTC day's opening price (crypto only).");
      if (C.endMins[i] !== 1410) return wait(`Trades at 23:30 UTC. It's ${hhmm(C.endMins[i])} UTC.`);
      if (C.at0030[i] == null) return wait("Needs today's 00:30 UTC price.");
      const first = C.at0030[i] / C.open[i] - 1;
      if (first > 0) return buy(`The day's first half hour was up ${pct(first, 2)}. Buying the last half hour.`);
      return wait(`The first half hour was ${pct(first, 2)}. No trade today.`);
    } },
  { id: "btcnight", name: "Bitcoin Night Hours", type: "Research", color: "#fcbf49",
    desc: "A seasonality study (reported by QuantPedia) found bitcoin's strongest hours were 22:00 and 23:00 UTC, when the major stock markets are closed. Owns crypto from 21:00 to 23:00 UTC every day. Crypto; needs candles of 1 hour or shorter.",
    overlays: () => [],
    decide(I, i, pos) {
      const tf = tfMins();
      if (tf > 60) return needFast(60);
      const C = cryptoDays(I, tf), end = C.endMins[i];
      if (pos && (end >= 1380 || end < 1260)) return sell(`${hhmm(end)} UTC. Selling.`);
      if (pos) return wait(`${hhmm(end)} UTC. Holding until 23:00.`);
      if (C.open[i] == null) return wait("Crypto only (needs a 24-hour market).");
      if (end >= 1260 && end < 1260 + tf) return buy("21:00 UTC. Buying for the two night hours.");
      return wait(`${hhmm(end)} UTC. Buys at 21:00.`);
    } },
  { id: "gapreversal", name: "Gap Reversal to Close", type: "Research", color: "#90be6d",
    desc: "A study of liquid US stocks found big price drops tend to partly reverse. When a stock opens at least 0.7% below yesterday's close, buys at the close of the first candle and holds to the day's close. Stocks; needs candles of 30 minutes or shorter.",
    overlays: () => [],
    decide(I, i, pos) {
      const tf = tfMins();
      if (tf > 30) return needFast(30);
      const D = stockDays(I, tf);
      if (pos && (D.last[i] || !D.stock[i])) return sell("The closing bell. Selling.");
      if (pos) return wait("Holding to the close.");
      if (!D.stock[i]) return wait("Stocks only.");
      if (i !== D.first[i]) return wait("Only trades the first candle of the day.");
      if (D.prevClose[i] == null) return wait("Needs yesterday's close.");
      const gap = I.open[i] / D.prevClose[i] - 1;
      if (gap <= -0.007) return buy(`Opened ${pct(-gap, 2)} below yesterday's close. Buying for a reversal by the close.`);
      return wait(`Opened ${pct(gap, 2)} from yesterday's close. Needs a gap down of 0.7% or more.`);
    } },
  { id: "extremereversal", name: "Extreme Drop Reversal", type: "Research", color: "#43aa8b",
    desc: "The same idea inside the day: when a stock has fallen at least 3% (and 2.5 ATRs) from the day's opening price, buys, and sells when it recovers to within 1% of the open or at the day's close. One trade a day. Stocks; needs candles of 30 minutes or shorter.",
    overlays: () => [],
    decide(I, i, pos) {
      const tf = tfMins();
      if (tf > 30) return needFast(30);
      const D = stockDays(I, tf), c = I.close[i];
      if (pos && (D.last[i] || !D.stock[i])) return sell("The closing bell. Selling.");
      if (pos && c >= D.dayOpen[i] * 0.99) return sell("Recovered to within 1% of the day's open. Selling.");
      if (pos) return wait("Holding for a recovery toward the open.");
      if (!D.stock[i]) return wait("Stocks only.");
      const a = I.atr14[i], drop = 1 - c / D.dayOpen[i];
      if (a == null) return warm(15, i);
      if (this.st.day === D.first[i]) return wait("Already traded today.");
      if (drop >= 0.03 && D.dayOpen[i] - c >= 2.5 * a && !D.last[i]) {
        this.st.day = D.first[i];
        return buy(`Down ${pct(drop)} from the day's open. Buying the extreme drop.`);
      }
      return wait(`${pct(drop)} below the day's open. Needs 3%.`);
    } },
  { id: "openvolume", name: "Opening Volume Momentum", type: "Time", color: "#577590",
    desc: "A common day-trading idea: when the first half hour's volume is at least 1.5 times its average over recent days and the stock is above its opening price at 10 am, big buyers may be at work. Buys at 10 am New York time and sells at the close. Stocks; needs candles of 30 minutes or shorter.",
    overlays: () => [],
    decide(I, i, pos) {
      const tf = tfMins();
      if (tf > 30) return needFast(30);
      const D = stockDays(I, tf);
      if (pos && (D.last[i] || !D.stock[i])) return sell("The closing bell. Selling.");
      if (pos) return wait("Holding to the close.");
      if (!D.stock[i]) return wait("Stocks only.");
      if (D.endMins[i] !== 600) return wait(`Trades at 10 am New York time. It's ${hhmm(D.endMins[i])}.`);
      if (D.vol30[i] == null || D.avgVol30[i] == null || !(D.avgVol30[i] > 0)) return wait("Needs 3 days of opening volume history.");
      const ratio = D.vol30[i] / D.avgVol30[i], up = I.close[i] > D.dayOpen[i];
      if (ratio >= 1.5 && up) return buy(`The first half hour traded ${ratio.toFixed(1)} times its usual volume and the stock is above its open. Buying.`);
      return wait(`Opening volume ${ratio.toFixed(1)}x usual, ${up ? "above" : "below"} the open. Needs 1.5x and above.`);
    } },

  // ----- combined -----
  { id: "fastcommittee", name: "Fast Committee", type: "Trend", color: "#48bfe3",
    desc: "Four fast trend signals vote: EMA 3 above EMA 8, a fast MACD above its signal, a fast Supertrend pointing up, and at least 6 of the last 10 candles closing higher. Buys when at least 3 agree and sells when 1 or none do.",
    overlays: () => [],
    decide(I, i, pos) {
      const F = fastSignals(I);
      if (i < 10 || F.sig[i] == null || F.st.dir[i] == null) return warm(17, i);
      let ups = 0;
      for (let j = i - 9; j <= i; j++) if (I.close[j] > I.close[j - 1]) ups++;
      const votes = [F.e3[i] > F.e8[i], F.macd[i] > F.sig[i], F.st.dir[i] === 1, ups >= 6].filter(Boolean).length;
      if (!pos && votes >= 3) return buy(`${votes} of 4 fast signals say up. Buying.`);
      if (pos && votes <= 1) return sell(`Only ${votes} of 4 fast signals still say up. Selling.`);
      return wait(`${votes} of 4 fast signals say up. ${pos ? "Holding until 1 or none." : "Buys at 3 or more."}`);
    } },
);
})();

// A sixth batch of Live Arena bots (added 2026-09-13), built from what the speed test's practice weeks showed.
// - On 5- and 15-minute crypto candles, the dip-buying bots picked their moments better than chance but paid 0.25% a
//   trade and lost it all to fees. Only a big drop bounces by more than a buy and a sale cost, so the bounce bots here
//   wait for large drops and hold for hours.
// - Also: bitcoin's taker buying and the VIX curve (outside data), a published stock momentum rule, a learner that only
//   trades when its forecast beats the fees, and random-entry controls with matching holding times.
// The thresholds were chosen after looking at the practice weeks (2026-07-13 to 2026-09-12), so those weeks prove
// nothing for these bots: only forward weeks count. None of these bots are in the year-long paper tests.
(() => {
"use strict";

// ---------- helpers ----------
const memo = new WeakMap();
function get(owner, key, make) {   // computed the first time a bot asks, once per set of candles (or per data series)
  let m = memo.get(owner);
  if (!m) memo.set(owner, m = {});
  if (!(key in m)) m[key] = make();
  return m[key];
}
const tfMins = () => +$("tf").value;
const bars = mins => Math.max(1, Math.round(mins / tfMins()));   // how many candles make up this many minutes
const pct = (x, dp = 1) => `${(x * 100).toFixed(dp)}%`;
const span = mins => mins % 60 ? `${mins} minutes` : mins === 60 ? "1 hour" : `${mins / 60} hours`;
const hhmm = mins => `${String(Math.floor(mins / 60) % 24).padStart(2, "0")}:${String(mins % 60).padStart(2, "0")}`;
const warm = (n, i) => wait(`Warming up. Needs ${n} candles (has ${i + 1}).`);
const needFast = tf => wait(`Needs candles of ${tf} minutes or shorter.`);
const EXT = () => window.SPEED_EXT || null;
const outside = name => { const ext = EXT(); return ext && ext.outside ? ext.outside[name] : null; };
const needOutside = what => wait(`Needs ${what}, which only the weekly speed test collects.`);
const needGroup = () => wait("Needs the other markets in its group, which only the weekly speed test provides.");
const roundTrip = () => 2 * feeRate() + 2 * SLIP;   // a buy and its sale together, as a share of the price
const change = (I, i, mins) => { const k = bars(mins); return i >= k ? I.close[i] / I.close[i - k] - 1 : null; };
const dayAvg = I => { const n = bars(1440); return get(I, `sma${n}`, () => sma(I.close, n)); };
const byTime = rows => get(rows, "byTime", () => new Map(rows.map((r, j) => [r.time, j])));
const NY_DATE = new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York" });

function lastAtOrBefore(rows, t) {   // index of the last row stamped at or before t, or -1
  let lo = 0, hi = rows.length - 1, found = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (rows[mid].time <= t) { found = mid; lo = mid + 1; } else hi = mid - 1;
  }
  return found;
}
// A repeatable random number in [0, 1) for this candle: the same on every rerun, but a different calendar in every
// market (unlike Coin Flip, whose one seed gives every market the same random days).
function chance(I, i, salt) {
  let h = Math.imul(((I.time[i] + OFF) | 0) ^ salt, 0x9e3779b1) ^ Math.imul(Math.round(I.open[0] * 1e4) | 0, 0x85ebca77);
  h ^= h >>> 15; h = Math.imul(h, 0x2c1b3c6d); h ^= h >>> 12; h = Math.imul(h, 0x297a2d39); h ^= h >>> 15;
  return (h >>> 0) / 4294967296;
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
function prefix(values) {   // running totals, so any stretch's sum is one subtraction
  const out = new Float64Array(values.length + 1);
  for (let j = 0; j < values.length; j++) out[j + 1] = out[j] + values[j];
  return out;
}
function solve(A, b) {   // a small linear system, by Gaussian elimination with pivoting (A and b are left untouched)
  const n = b.length, M = A.map((row, r) => [...row, b[r]]);
  for (let c = 0; c < n; c++) {
    let p = c;
    for (let r = c + 1; r < n; r++) if (Math.abs(M[r][c]) > Math.abs(M[p][c])) p = r;
    [M[c], M[p]] = [M[p], M[c]];
    if (Math.abs(M[c][c]) < 1e-12) return null;
    for (let r = c + 1; r < n; r++) {
      const f = M[r][c] / M[c][c];
      for (let k = c; k <= n; k++) M[r][k] -= f * M[c][k];
    }
  }
  const x = Array(n).fill(0);
  for (let r = n - 1; r >= 0; r--) {
    let s = M[r][n];
    for (let k = r + 1; k < n; k++) s -= M[r][k] * x[k];
    x[r] = s / M[r][r];
  }
  return x;
}

// The Cost-Aware Learner's forecasts of the next 8 hours' return (in %), from a ridge regression that only ever trains
// on examples whose 8 hours have already passed.
function costForecasts(I, tf) {
  return get(I, `cost${tf}`, () => {
    const n = I.close.length, C = I.close, H = Math.max(1, Math.round(480 / tf)), h1 = Math.max(1, Math.round(60 / tf));
    const h3 = Math.max(1, Math.round(180 / tf)), avg = sma(C, Math.max(2, Math.round(1440 / tf)));
    const pred = Array(n).fill(null), seen = Array(n).fill(0), K = 7, A = [...Array(K)].map((_, r) => [...Array(K)].map((_, c) => r === c ? 5 : 0)), b = Array(K).fill(0);
    const features = j => {
      if (j < h3 || avg[j] == null || I.atr14[j] == null) return null;
      const angle = 2 * Math.PI * (((I.time[j] + OFF) % 86400) / 86400);
      return [1, 100 * (C[j] / C[j - h1] - 1), 100 * (C[j] / C[j - h3] - 1), 100 * (C[j] / avg[j] - 1), 100 * I.atr14[j] / C[j], Math.sin(angle), Math.cos(angle)];
    };
    let count = 0;
    for (let i = 0; i < n; i++) {
      const j = i - H;   // this candle's close finishes the 8 hours after candle j
      const x = j >= 0 ? features(j) : null;
      if (x) {
        const y = Math.max(-10, Math.min(10, 100 * (C[i] / C[j] - 1)));
        for (let r = 0; r < K; r++) { b[r] += x[r] * y; for (let c = 0; c < K; c++) A[r][c] += x[r] * x[c]; }
        count++;
      }
      seen[i] = count;
      const now = features(i);
      if (now && count >= 120) {
        const w = solve(A, b);
        if (w) pred[i] = w.reduce((s, v, r) => s + v * now[r], 0);
      }
    }
    return { pred, seen, H };
  });
}

// Stock days (New York): the opening price, yesterday's close, the day's VWAP so far, and the "noise area" width:
// how far the price has usually strayed from the open by this time of day over the last 14 days (at least 4).
function stockSessions(I, tf) {
  return get(I, `sessions${tf}`, () => {
    const n = I.close.length, blank = () => Array(n).fill(null);
    const S = { stock: Array(n).fill(false), endMins: Array(n).fill(0), open: blank(), prevClose: blank(), vwap: blank(), sigma: blank() };
    const days = [];
    let cur = null, pv = 0, vv = 0;
    for (let i = 0; i < n; i++) {
      const t = I.time[i] + OFF, date = NY_DATE.format(new Date(t * 1000)), start = nyClock(t).mins, end = start + tf;
      if (!cur || cur.date !== date) {
        cur = { date, open: I.open[i], stock: start >= 540, moves: new Map(), prevClose: cur ? cur.lastClose : null, lastClose: null };
        days.push(cur);
        pv = vv = 0;
      }
      cur.lastClose = I.close[i];
      pv += (I.high[i] + I.low[i] + I.close[i]) / 3 * I.vol[i];
      vv += I.vol[i];
      cur.moves.set(end, Math.abs(I.close[i] / cur.open - 1));
      let sum = 0, count = 0;
      for (let d = days.length - 2; d >= Math.max(0, days.length - 15); d--) {
        const m = days[d].stock ? days[d].moves.get(end) : null;
        if (m != null) { sum += m; count++; }
      }
      S.stock[i] = cur.stock; S.endMins[i] = end; S.open[i] = cur.open; S.prevClose[i] = cur.prevClose;
      S.vwap[i] = vv > 0 ? pv / vv : I.close[i];
      S.sigma[i] = count >= 4 ? sum / count : null;
    }
    return S;
  });
}

// ---------- bounce bots: buy a big drop, hold for hours ----------
function dropBot({ id, name, color, drop, over, hold, desc }) {
  return { id, name, type: "Bounce", color, desc,
    overlays: () => [],
    decide(I, i, pos) {
      if (tfMins() > 60) return needFast(60);
      if (pos) return checkExits(this, I, i) || wait(`Holding. ${this.st.maxBars - (i - this.st.entryIdx)} candles left.`);
      const ch = change(I, i, over);
      if (ch == null) return warm(bars(over) + 1, i);
      if (ch <= -drop) return enter(this, i, `Down ${pct(-ch)} over the last ${span(over)}. Buying the drop and holding for ${span(hold)}.`, { maxBars: bars(hold) });
      return wait(`${ch >= 0 ? "Up" : "Down"} ${pct(Math.abs(ch))} over the last ${span(over)}. Buys a drop of ${pct(drop, 0)} or more.`);
    } };
}
BOTS.push(
  dropBot({ id: "drop3h8", name: "3-Hour Drop, 8-Hour Hold", color: "#bc4749", drop: 0.03, over: 180, hold: 480,
    desc: "Buys after a fall of 3% or more over the last 3 hours and sells 8 hours later, with no stop. In the practice weeks, crypto coins tended to bounce after drops that size by more than a buy and a sale cost in fees (0.54%), while short bounces were too small to pay for them. Needs candles of 1 hour or shorter." }),
  dropBot({ id: "drop3h4", name: "3-Hour Drop, 4-Hour Hold", color: "#a7c957", drop: 0.03, over: 180, hold: 240,
    desc: "The same 3% drop over 3 hours, but sells after 4 hours instead of 8. Needs candles of 1 hour or shorter." }),
  dropBot({ id: "dip2h8", name: "2% Dip, 8-Hour Hold", color: "#6a994e", drop: 0.02, over: 180, hold: 480,
    desc: "A shallower version: buys after a fall of 2% or more over 3 hours and sells 8 hours later. It trades more often, but smaller drops bounced less. Needs candles of 1 hour or shorter." }),
  dropBot({ id: "plunge1h", name: "1-Hour Plunge, 8-Hour Hold", color: "#386641", drop: 0.03, over: 60, hold: 480,
    desc: "Buys after a fall of 3% or more within a single hour and sells 8 hours later. Needs candles of 1 hour or shorter." }),
  dropBot({ id: "slide6h", name: "6-Hour Slide, 12-Hour Hold", color: "#f2e8cf", drop: 0.05, over: 360, hold: 720,
    desc: "Waits for a rarer, bigger fall: 5% or more over 6 hours. Buys and sells 12 hours later. Needs candles of 1 hour or shorter." }),
  { id: "unusualdrop", name: "Unusual Drop Bounce", type: "Bounce", color: "#e76f51",
    desc: "Measures how unusual the last 3 hours' move is for this market: how many standard deviations it sits from its 3-hour moves over the past week (or as far back as it has, at least 150 candles). Buys a move 2.5 or more below normal and sells 8 hours later, so it adapts to each market's own swings. Needs candles of 1 hour or shorter.",
    overlays: () => [],
    decide(I, i, pos) {
      if (tfMins() > 60) return needFast(60);
      if (pos) return checkExits(this, I, i) || wait(`Holding. ${this.st.maxBars - (i - this.st.entryIdx)} candles left.`);
      const k = bars(180), first = Math.max(k, i - bars(7 * 1440)), n = i - first;
      if (n < 150) return warm(k + 151, i);
      const P = get(I, `drops${k}`, () => {
        const moves = I.close.map((c, j) => j >= k ? c / I.close[j - k] - 1 : 0);
        return { s: prefix(moves), q: prefix(moves.map(x => x * x)) };
      });
      const mean = (P.s[i] - P.s[first]) / n, sd = Math.sqrt(Math.max((P.q[i] - P.q[first]) / n - mean * mean, 0));
      const now = I.close[i] / I.close[i - k] - 1, z = sd > 0 ? (now - mean) / sd : 0;
      if (z <= -2.5) return enter(this, i, `The last 3 hours (${pct(now)}) were ${(-z).toFixed(1)} standard deviations below this market's usual 3-hour move. Buying for 8 hours.`, { maxBars: bars(480) });
      return wait(`The last 3 hours: ${pct(now)}, ${z.toFixed(1)} standard deviations from usual. Needs −2.5.`);
    } },
  { id: "dropexits", name: "Drop Bounce with Exits", type: "Bounce", color: "#f4a259",
    desc: "After a fall of 3% or more over 3 hours, buys with a take-profit 2.5% higher and a stop 5% lower, and sells after 12 hours if neither is hit. Needs candles of 1 hour or shorter.",
    overlays() { return riskLines(this); },
    decide(I, i, pos) {
      if (tfMins() > 60) return needFast(60);
      if (pos) return checkExits(this, I, i) || wait(`${holdingMsg(this)} ${this.st.maxBars - (i - this.st.entryIdx)} candles left.`);
      const ch = change(I, i, 180), c = I.close[i];
      if (ch == null) return warm(bars(180) + 1, i);
      if (ch <= -0.03) return enter(this, i, `Down ${pct(-ch)} over 3 hours. Buying, take-profit ${fmtP(c * 1.025)}, stop ${fmtP(c * 0.95)}.`, { target: c * 1.025, stop: c * 0.95, maxBars: bars(720) });
      return wait(`${pct(ch)} over the last 3 hours. Buys a 3% drop.`);
    } },
  { id: "capitulation", name: "Capitulation Volume", type: "Bounce", color: "#5b8e7d",
    desc: "Looks for panic selling: a fall of 2.5% or more over 3 hours, with the last hour's trading volume at least 2.5 times its usual hourly volume over the previous 2 days. Buys and sells 8 hours later. Needs candles of 1 hour or shorter.",
    overlays: () => [],
    decide(I, i, pos) {
      if (tfMins() > 60) return needFast(60);
      if (pos) return checkExits(this, I, i) || wait(`Holding. ${this.st.maxBars - (i - this.st.entryIdx)} candles left.`);
      const h = bars(60), W = bars(2 * 1440), ch = change(I, i, 180);
      if (i + 1 < W + h || ch == null) return warm(W + h, i);
      const V = get(I, "volsum", () => prefix(I.vol));
      const lastHour = V[i + 1] - V[i + 1 - h], usual = (V[i + 1 - h] - V[i + 1 - h - W]) / W * h;
      const ratio = usual > 0 ? lastHour / usual : 0;
      if (ch <= -0.025 && ratio >= 2.5) return enter(this, i, `Down ${pct(-ch)} over 3 hours on ${ratio.toFixed(1)} times the usual hourly volume. Buying the panic for 8 hours.`, { maxBars: bars(480) });
      return wait(`${pct(ch)} over 3 hours, last hour's volume ${ratio.toFixed(1)}x usual. Needs a 2.5% drop on 2.5x volume.`);
    } },
  { id: "dipuptrend", name: "Dip in an Uptrend", type: "Bounce", color: "#9bc53d",
    desc: "Only buys drops in markets that were healthy before they fell: a fall of 2% or more over 3 hours, where the price 3 hours ago was above its 1-day average. Sells 8 hours later. Needs candles of 1 hour or shorter.",
    overlays: I => [["1-day average", dayAvg(I), "#9bc53d"]],
    decide(I, i, pos) {
      if (tfMins() > 60) return needFast(60);
      if (pos) return checkExits(this, I, i) || wait(`Holding. ${this.st.maxBars - (i - this.st.entryIdx)} candles left.`);
      const k = bars(180), avg = dayAvg(I), ch = change(I, i, 180);
      if (ch == null || avg[i - k] == null) return warm(bars(1440) + k, i);
      const healthy = I.close[i - k] > avg[i - k];
      if (ch <= -0.02 && healthy) return enter(this, i, `Down ${pct(-ch)} over 3 hours, after trading above its 1-day average. Buying the dip for 8 hours.`, { maxBars: bars(480) });
      return wait(`${pct(ch)} over 3 hours; 3 hours ago it was ${healthy ? "above" : "below"} its 1-day average.`);
    } },
  { id: "dropladder", name: "Drop Ladder", type: "Bounce", color: "#9c6644",
    desc: "Buys in three equal parts as a drop deepens: the first after a 2% fall over 3 hours, the second 1.5% below that first buy, the third 3% below it. Sells everything 8 hours after its last buy. Bigger drops bounced more in the practice weeks, so it puts in more as they grow. Needs candles of 1 hour or shorter.",
    overlays: () => [],
    decide(I, i, pos) {
      if (tfMins() > 60) return needFast(60);
      const s = this.st, c = I.close[i], hold = bars(480);
      if (pos) {
        if (i - s.last >= hold) return sell(`${span(480)} since the last buy. Selling everything.`);
        if (s.n < 3 && c <= s.ref * (1 - 0.015 * s.n)) return { act: "buy", frac: 1 / (3 - s.n), why: `Down to ${fmtP(c)}, ${pct(1 - c / s.ref)} below the first buy. Buying part ${s.n + 1} of 3.` };
        return wait(`Holding ${s.n} of 3 parts. Sells in ${hold - (i - s.last)} candles.`);
      }
      const ch = change(I, i, 180);
      if (ch == null) return warm(bars(180) + 1, i);
      if (ch <= -0.02) return { act: "buy", frac: 1 / 3, why: `Down ${pct(-ch)} over the last 3 hours. Buying part 1 of 3.` };
      return wait(`${pct(ch)} over the last 3 hours. Starts buying at a 2% drop.`);
    },
    filled(d, r, i) {
      const s = this.st;
      if (d.act === "buy") { s.n = (s.n || 0) + 1; s.last = i; if (s.n === 1) s.ref = r.fill; }
      else { s.n = 0; s.ref = null; }
    } },
  { id: "btcdrop", name: "Bitcoin Drop, Coin Bounce", type: "vs Bitcoin", color: "#e09f3e",
    desc: "When bitcoin has fallen 2.5% or more over the last 3 hours, buys this coin and sells it 8 hours later: most coins fall with bitcoin, so bitcoin's drop stands in for the whole market's. Needs bitcoin's candles for the same times and candles of 1 hour or shorter.",
    overlays: () => [],
    decide(I, i, pos) {
      if (!I.btc) return wait("Needs bitcoin's candles for the same times.");
      if (tfMins() > 60) return needFast(60);
      if (pos) return checkExits(this, I, i) || wait(`Holding. ${this.st.maxBars - (i - this.st.entryIdx)} candles left.`);
      const k = bars(180);
      if (i < k) return warm(k + 1, i);
      const b = I.btc[i] / I.btc[i - k] - 1;
      if (b <= -0.025) return enter(this, i, `Bitcoin fell ${pct(-b)} over the last 3 hours. Buying this coin for 8 hours.`, { maxBars: bars(480) });
      return wait(`Bitcoin ${pct(b)} over the last 3 hours. Buys after a 2.5% drop.`);
    } },

  // ----- the group (speed test only) -----
  { id: "flushlaggard", name: "Flush Laggard, 8 Hours", type: "Breadth", color: "#40798c",
    desc: "When the whole group has fallen 1.5% or more on average over the last 90 minutes and this market fell at least half a point more than that, buys it and sells 8 hours later. In the practice weeks, the coins hit hardest in a group-wide drop tended to bounce back the most. Speed test only; needs candles of 1 hour or shorter.",
    overlays: () => [],
    decide(I, i, pos) {
      const ext = EXT();
      if (!ext) return needGroup();
      if (tfMins() > 60) return needFast(60);
      if (pos) return checkExits(this, I, i) || wait(`Holding. ${this.st.maxBars - (i - this.st.entryIdx)} candles left.`);
      const e = groupMoves(ext, bars(90)).get(I.time[i]), me = e && e[ext.current];
      if (me == null) return warm(bars(90) + 1, i);
      const all = Object.values(e);
      if (all.length < 3) return wait("Too few markets in the group have prices for this candle.");
      const avg = all.reduce((a, x) => a + x, 0) / all.length;
      if (avg <= -0.015 && me <= avg - 0.005) return enter(this, i, `The group fell ${pct(-avg)} on average over 90 minutes and this market fell ${pct(-me)}. Buying the laggard for 8 hours.`, { maxBars: bars(480) });
      return wait(`Group ${pct(avg)} over 90 minutes, this market ${pct(me)}.`);
    } },
  { id: "groupcrash", name: "Group Crash, 8 Hours", type: "Breadth", color: "#0b3954",
    desc: "When the group's markets have fallen 2% or more on average over the last 90 minutes, buys and sells 8 hours later. Speed test only; needs candles of 1 hour or shorter.",
    overlays: () => [],
    decide(I, i, pos) {
      const ext = EXT();
      if (!ext) return needGroup();
      if (tfMins() > 60) return needFast(60);
      if (pos) return checkExits(this, I, i) || wait(`Holding. ${this.st.maxBars - (i - this.st.entryIdx)} candles left.`);
      const e = groupMoves(ext, bars(90)).get(I.time[i]);
      if (!e || e[ext.current] == null) return warm(bars(90) + 1, i);
      const all = Object.values(e);
      if (all.length < 3) return wait("Too few markets in the group have prices for this candle.");
      const avg = all.reduce((a, x) => a + x, 0) / all.length;
      if (avg <= -0.02) return enter(this, i, `The whole group fell ${pct(-avg)} on average over 90 minutes. Buying for 8 hours.`, { maxBars: bars(480) });
      return wait(`The group moved ${pct(avg)} on average over 90 minutes. Needs a 2% fall.`);
    } },

  // ----- time of day -----
  { id: "nyselloff", name: "NY Selloff, Hold to 4 pm", type: "Time", color: "#2ec4b6",
    desc: "NY Open Reversal had the best-timed crypto trades in the practice weeks, but sold at noon. This version buys the same early selloff (a fall of more than 1 ATR from the 9:30 open to 10 am New York time, on a weekday) and holds until just before 4 pm. Needs candles of 30 minutes or shorter.",
    overlays: () => [],
    decide(I, i, pos) {
      const tf = tfMins();
      if (tf > 30) return needFast(30);
      const t = nyClock(I.time[i] + OFF + tf * 60), a = I.atr14[i];   // New York time at the candle's close
      if (pos && (t.mins + tf >= 960 || t.mins < 600)) return sell(`${hhmm(t.mins)} in New York. Selling before 4 pm.`);
      if (pos) return wait("Holding until just before 4 pm in New York.");
      if (a == null) return warm(15, i);
      if (t.mins !== 600 || t.day === "Sat" || t.day === "Sun") return wait(`${t.day} ${hhmm(t.mins)} in New York. Waiting for 10 am on a weekday.`);
      let j = -1;
      for (let k = i; k >= Math.max(0, i - 7) && j < 0; k--) if (nyClock(I.time[k] + OFF).mins === 570) j = k;
      if (j < 0) return wait("No 9:30 candle today.");
      const drop = I.open[j] - I.close[i];
      if (drop > a) return buy(`Fell ${fmtP(drop)} since the 9:30 open, more than 1 ATR. Buying the early selloff and holding to the close.`);
      return wait(`10 am in New York. Moved ${fmtP(-drop)} since 9:30; needs a drop of more than ${fmtP(a)}.`);
    } },

  // ----- fee-aware versions of the bots that timed well -----
  { id: "widegrid", name: "Wide Grid", type: "Grid", color: "#b8c0ff",
    desc: "Grid Trader timed its dips better than chance on crypto but paid fees on hundreds of small trades a week. This version spaces its 5 slices so that each sale earns at least three times what a buy and a sale cost (or 2 ATRs, if that's wider). Buys a slice each step down and sells each slice one step above its own buy price.",
    reset() { this.st.lots = []; this.lv.nb = []; this.lv.ns = []; },
    overlays() { return [["Next buy", this.lv.nb, "#26a69a"], ["Next sell", this.lv.ns, "#ef5350"]]; },
    decide(I, i) {
      const a = I.atr14[i], c = I.close[i], s = this.st, lots = s.lots;
      if (a == null) return warm(15, i);
      const step = Math.max(2 * a, 3 * roundTrip() * c);
      if (!lots.length && s.ref != null && c > s.ref + 2 * step) s.ref = null;   // price ran away: start a new grid
      const nextBuy = lots.length ? Math.min(...lots.map(l => l.entry)) - step : s.ref != null ? s.ref - step : c;
      const nextSell = lots.length ? Math.min(...lots.map(l => l.target)) : null;
      if (lots.length < 5) this.lv.nb[i] = nextBuy;
      if (nextSell != null) this.lv.ns[i] = nextSell;
      const ready = lots.filter(l => c >= l.target).sort((x, y) => x.entry - y.entry)[0];
      if (ready) return { act: "sell", lot: ready, costBasis: ready.cost, frac: lots.length === 1 ? 1 : ready.qty / acct[this.id].qty,
        why: `The slice bought at ${fmtP(ready.entry)} reached its sell level (${fmtP(ready.target)}).` };
      if (lots.length < 5 && c <= nextBuy) return { act: "buy", step, frac: 1 / (5 - lots.length),
        why: lots.length ? `Down a full step to ${fmtP(c)}. Buying slice ${lots.length + 1} of 5.` : `Starting a wide grid at ${fmtP(c)}, step ${fmtP(step)}. Buying slice 1 of 5.` };
      return wait(`${lots.length} of 5 slices held.${lots.length < 5 ? ` Next buy at ${fmtP(nextBuy)}.` : ""}${nextSell != null ? ` Next sell at ${fmtP(nextSell)}.` : ""}`);
    },
    filled(d, r) {
      const s = this.st;
      if (d.act === "buy") s.lots.push({ entry: r.fill, qty: r.qty, cost: r.spend, target: r.fill + d.step });
      else { s.lots = s.lots.filter(l => l !== d.lot); if (!s.lots.length) s.ref = r.fill; }
    } },
  { id: "costlearner", name: "Cost-Aware Learner", type: "Stats", color: "#7678ed",
    desc: "A small regression model that trains itself as it goes, only on examples whose outcome is already known. From the last hour's and 3 hours' moves, the distance from the 1-day average, volatility and the time of day, it forecasts the next 8 hours. Buys only when the forecast is bigger than what a buy and a sale cost: a 2026 study of machine-learning bitcoin trading found that filter cut trading sharply and brought some of its models back to a profit after costs. Holds 8 hours, and longer while the forecast still clears the fees. Needs candles of 1 hour or shorter.",
    overlays: () => [],
    decide(I, i, pos) {
      const tf = tfMins();
      if (tf > 60) return needFast(60);
      const F = costForecasts(I, tf), p = F.pred[i], bar = 100 * roundTrip();
      if (pos && i - this.st.entryIdx >= F.H) {
        if (p != null && p >= bar) { this.st.entryIdx = i; return wait(`The forecast for the next 8 hours (${p.toFixed(2)}%) still beats the fees (${bar.toFixed(2)}%). Holding another 8 hours.`); }
        return sell(`8 hours are up and the forecast (${p == null ? "none" : `${p.toFixed(2)}%`}) no longer beats the fees. Selling.`);
      }
      if (pos) return wait(`Holding. ${F.H - (i - this.st.entryIdx)} candles until it checks the forecast again.`);
      if (p == null) return wait(`Learning. Has ${F.seen[i]} finished examples; needs 120.`);
      if (p >= bar) { this.st.entryIdx = i; return buy(`Forecast for the next 8 hours: ${p.toFixed(2)}%, more than a buy and a sale cost (${bar.toFixed(2)}%). Buying.`); }
      return wait(`Forecast for the next 8 hours: ${p.toFixed(2)}%. Needs more than the fees (${bar.toFixed(2)}%).`);
    } },

  // ----- outside data (speed test only) -----
  { id: "takerpressure", name: "Taker Buy Pressure", type: "Outside data", color: "#ff9f1c",
    desc: "Bitcoin's perpetual swaps report how much trading came from aggressive buyers (who pay the asking price) and how much from aggressive sellers. A 2026 study of crypto futures (Kim and Hansen) found that this order imbalance, measured at the start of each quarter hour, predicts returns over the next 4 to 12 hours. This simpler hourly version buys when aggressive buying beat selling by 15% or more over the last 4 finished hours and the coin is above its 1-day average, and sells 8 hours later. Crypto; speed test only.",
    overlays: I => [["1-day average", dayAvg(I), "#ff9f1c"]],
    decide(I, i, pos) {
      const tk = outside("taker_btc");
      if (!tk) return needOutside("the taker buy and sell volume on bitcoin's perpetual swaps");
      const tf = tfMins();
      if (tf > 60) return needFast(60);
      if (pos) return checkExits(this, I, i) || wait(`Holding. ${this.st.maxBars - (i - this.st.entryIdx)} candles left.`);
      const k = lastAtOrBefore(tk, I.time[i] + tf * 60 - 3600), avg = dayAvg(I)[i];   // the last hour that had finished by this candle's close
      if (k < 3 || avg == null) return warm(bars(1440), i);
      if (tk[k].time - tk[k - 3].time !== 3 * 3600) return wait("A gap in the hourly taker volume readings.");
      let bought = 0, sold = 0;
      for (let m = k - 3; m <= k; m++) { bought += tk[m].close; sold += tk[m].open; }   // stored as open = seller-initiated, close = buyer-initiated
      const ratio = sold > 0 ? bought / sold : 0, up = I.close[i] > avg;
      if (ratio >= 1.15 && up) return enter(this, i, `Aggressive buying was ${ratio.toFixed(2)} times aggressive selling over the last 4 hours, and the coin is above its 1-day average. Buying for 8 hours.`, { maxBars: bars(480) });
      return wait(`Taker buy/sell over 4 hours: ${ratio.toFixed(2)}. Coin ${up ? "above" : "below"} its 1-day average. Needs 1.15 and above.`);
    } },
  { id: "vixcurve", name: "Calm VIX Curve", type: "Outside data", color: "#3d5a80",
    desc: "VIX9D measures the fear priced in for the next 9 days, and VIX for the next 30. When the near-term reading is well below the 30-day one (85% of it or less), options traders expect calm soon. Owns the stock then, while it's above its 50-candle EMA, and sells when that ratio climbs over 95% or the stock drops under its EMA. Stocks; speed test only.",
    overlays: I => [["EMA 50", I.ema50, "#3d5a80"]],
    decide(I, i, pos) {
      const v9 = outside("vix9d"), vx = outside("vix");
      if (!v9 || !vx) return needOutside("the 9-day and 30-day VIX");
      const k9 = byTime(v9).get(I.time[i]), kx = byTime(vx).get(I.time[i]), e = I.ema50[i];
      if (e == null) return warm(50, i);
      if (k9 == null || kx == null || !(vx[kx].close > 0)) return wait(`No VIX readings for this candle. ${pos ? "Holding." : "Waiting."}`);
      const ratio = v9[k9].close / vx[kx].close, up = I.close[i] > e;
      if (!pos && ratio <= 0.85 && up) return buy(`VIX9D is ${pct(ratio, 0)} of VIX: calm expected soon, and the stock is above its EMA 50. Buying.`);
      if (pos && (ratio > 0.95 || !up)) return sell(ratio > 0.95 ? `VIX9D rose to ${pct(ratio, 0)} of VIX. Selling.` : "Dropped under its EMA 50. Selling.");
      return wait(`VIX9D is ${pct(ratio, 0)} of VIX; the stock is ${up ? "above" : "below"} its EMA 50.`);
    } },

  // ----- published intraday rule -----
  { id: "noisearea", name: "Noise Area Breakout", type: "Research", color: "#ee964b",
    desc: "From Zarattini, Aziz and Barbon (2024), who tested it on SPY. Each day, the 'noise area' above the opening price is how far the price has usually strayed from the open by that time of day over the last 14 days (at least 4 here, since the speed test warms up for a week); after a gap down it starts from yesterday's close instead. Every half hour, buys when the price breaks above that edge, sells when it falls back under the edge or the day's VWAP, and always ends the day in cash. The study also bet on falls; this version only buys. Stocks; needs candles of 30 minutes or shorter.",
    overlays: () => [],
    decide(I, i, pos) {
      const tf = tfMins();
      if (tf > 30) return needFast(30);
      const S = stockSessions(I, tf), end = S.endMins[i], c = I.close[i];
      const upper = S.sigma[i] != null && S.prevClose[i] != null ? Math.max(S.open[i], S.prevClose[i]) * (1 + S.sigma[i]) : null;
      if (pos) {
        if (!S.stock[i] || end + tf >= 960) return sell("The day's last candles. Selling so it ends the day in cash.");
        const line = upper != null ? Math.max(upper, S.vwap[i]) : S.vwap[i];
        if (end % 30 === 0 && c < line) return sell(`Back under ${upper != null && upper >= S.vwap[i] ? "the noise area's edge" : "the day's VWAP"} (${fmtP(line)}). Selling.`);
        return wait(`Holding. Checks every half hour against ${fmtP(line)}.`);
      }
      if (!S.stock[i]) return wait("Stocks only.");
      if (upper == null) return wait("Needs yesterday's close and at least 4 earlier days at this time of day.");
      if (end % 30 !== 0 || end + tf >= 960) return wait(`Checks on the hour and half hour before the last candles. It's ${hhmm(end)}.`);
      if (c > upper) return buy(`At ${hhmm(end)} the price (${fmtP(c)}) broke above the noise area's edge (${fmtP(upper)}), a bigger move than this time of day usually brings. Buying.`);
      return wait(`The noise area's upper edge is ${fmtP(upper)}; the price is ${fmtP(c)}.`);
    } },

  // ----- controls: random timing with the same holding times -----
  { id: "rand8h", name: "Random Entry, 8-Hour Hold", type: "Control", color: "#a5a58d",
    desc: "A control for the bounce bots. Buys at random moments (about twice a day's worth of candles) and sells 8 hours later, with a different random calendar in every market. If a bounce bot can't beat this, its drops weren't doing the work.",
    overlays: () => [],
    decide(I, i, pos) {
      if (tfMins() > 60) return needFast(60);
      if (pos) return checkExits(this, I, i) || wait(`Holding. ${this.st.maxBars - (i - this.st.entryIdx)} candles left.`);
      if (chance(I, i, 0x51ed27) < tfMins() / 720) return enter(this, i, "Random entry. Selling in 8 hours.", { maxBars: bars(480) });
      return wait("The dice said not yet.");
    } },
  { id: "rand1h", name: "Random Entry, 1-Hour Hold", type: "Control", color: "#b7b7a4",
    desc: "A control for short holds. Buys at random moments (about once every 4 hours' worth of candles) and sells 1 hour later, with a different random calendar in every market.",
    overlays: () => [],
    decide(I, i, pos) {
      if (tfMins() > 60) return needFast(60);
      if (pos) return checkExits(this, I, i) || wait(`Holding. ${this.st.maxBars - (i - this.st.entryIdx)} candles left.`);
      if (chance(I, i, 0x2f6b1d) < tfMins() / 240) return enter(this, i, "Random entry. Selling in 1 hour.", { maxBars: bars(60) });
      return wait("The dice said not yet.");
    } },
  { id: "coinfair", name: "Independent Coin Flip", type: "Control", color: "#cb997e",
    desc: "Like Coin Flip (a 1-in-10 chance each candle to buy if out or sell if in), but with a different random calendar in every market, so its results across markets are independent. The fairest measure of how often luck alone passes the speed test.",
    overlays: () => [],
    decide(I, i, pos) {
      if (chance(I, i, 0x6d2b79) < 0.1) return pos ? sell("Flipped a coin. Sell.") : buy("Flipped a coin. Buy.");
      return wait("Coin says do nothing.");
    } },
);
})();

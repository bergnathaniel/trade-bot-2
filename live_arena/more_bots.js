// More Live Arena bots (added 2026-09-12), appended to the BOTS list in index.html.
// They live in their own file so index.html's bot section, which the paper tests fingerprint, stays unchanged.
// None of them are in the paper tests. Same ground rules as every other bot: decide only on closed candles, paper money only.
(() => {
"use strict";

// ---------- extra indicators: each is computed the first time a bot asks for it, once per set of candles ----------
const memo = new WeakMap();
function get(I, key, make) {
  let m = memo.get(I);
  if (!m) memo.set(I, m = {});
  if (!(key in m)) m[key] = make();
  return m[key];
}
function avgN(v, n) {   // simple average that stays blank until the last n values all exist
  const o = Array(v.length).fill(null);
  for (let i = n - 1; i < v.length; i++) {
    let s = 0, ok = true;
    for (let j = i - n + 1; j <= i && ok; j++) if (v[j] == null) ok = false; else s += v[j];
    if (ok) o[i] = s / n;
  }
  return o;
}
function wma(v, n) {   // weighted average: the newest value counts n times, the oldest once
  const o = Array(v.length).fill(null), den = n * (n + 1) / 2;
  for (let i = n - 1; i < v.length; i++) {
    let s = 0, ok = true;
    for (let j = 0; j < n && ok; j++) if (v[i - j] == null) ok = false; else s += v[i - j] * (n - j);
    if (ok) o[i] = s / den;
  }
  return o;
}
function hull(v, n) {   // Hull moving average: smooth, but quick to turn
  const half = wma(v, Math.round(n / 2)), full = wma(v, n);
  return wma(half.map((h, i) => h == null || full[i] == null ? null : 2 * h - full[i]), Math.round(Math.sqrt(n)));
}
function kama(v, n = 10, fast = 2, slow = 30) {   // Kaufman's adaptive average: fast in clean trends, nearly still in chop
  const o = Array(v.length).fill(null), f = 2 / (fast + 1), s = 2 / (slow + 1);
  for (let i = n; i < v.length; i++) {
    let noise = 0;
    for (let j = i - n + 1; j <= i; j++) noise += Math.abs(v[j] - v[j - 1]);
    const er = noise ? Math.abs(v[i] - v[i - n]) / noise : 0, sc = (er * (f - s) + s) ** 2, prev = o[i - 1] ?? v[i - 1];
    o[i] = prev + sc * (v[i] - prev);
  }
  return o;
}
function aroon(high, low, n) {   // how recently the highest high and lowest low of the last n candles happened, 100 = this candle
  const up = Array(high.length).fill(null), dn = up.slice();
  for (let i = n; i < high.length; i++) {
    let hi = i - n, lo = i - n;
    for (let j = i - n; j <= i; j++) { if (high[j] >= high[hi]) hi = j; if (low[j] <= low[lo]) lo = j; }
    up[i] = 100 * (n - (i - hi)) / n; dn[i] = 100 * (n - (i - lo)) / n;
  }
  return { up, dn };
}
function vortex(high, low, close, n) {
  const plus = Array(close.length).fill(null), minus = plus.slice();
  for (let i = n; i < close.length; i++) {
    let vp = 0, vm = 0, tr = 0;
    for (let j = i - n + 1; j <= i; j++) {
      vp += Math.abs(high[j] - low[j - 1]); vm += Math.abs(low[j] - high[j - 1]);
      tr += Math.max(high[j] - low[j], Math.abs(high[j] - close[j - 1]), Math.abs(low[j] - close[j - 1]));
    }
    plus[i] = tr > 0 ? vp / tr : 1; minus[i] = tr > 0 ? vm / tr : 1;
  }
  return { plus, minus };
}
function regression(v, n) {   // slope of the best straight line through the last n values, and how well it fits (R², 0 to 1)
  const slope = Array(v.length).fill(null), r2 = slope.slice(), mx = (n - 1) / 2, sxx = n * (n * n - 1) / 12;
  for (let i = n - 1; i < v.length; i++) {
    let sy = 0, sxy = 0, syy = 0;
    for (let k = 0; k < n; k++) { sy += v[i - n + 1 + k]; sxy += (k - mx) * v[i - n + 1 + k]; }
    for (let k = 0; k < n; k++) syy += (v[i - n + 1 + k] - sy / n) ** 2;
    slope[i] = sxy / sxx;
    r2[i] = syy > 0 ? sxy * sxy / (sxx * syy) : 0;
  }
  return { slope, r2 };
}
const typical = I => I.close.map((c, j) => (I.high[j] + I.low[j] + c) / 3);
function cci(tp, n) {   // Commodity Channel Index: distance from the average in units of typical deviation
  const o = Array(tp.length).fill(null);
  for (let i = n - 1; i < tp.length; i++) {
    let s = 0, dev = 0;
    for (let j = i - n + 1; j <= i; j++) s += tp[j];
    const m = s / n;
    for (let j = i - n + 1; j <= i; j++) dev += Math.abs(tp[j] - m);
    o[i] = dev > 0 ? (tp[i] - m) / (0.015 * dev / n) : 0;
  }
  return o;
}
function mfi(tp, vol, n) {   // Money Flow Index: an RSI weighted by volume
  const o = Array(tp.length).fill(null);
  for (let i = n; i < tp.length; i++) {
    let up = 0, down = 0;
    for (let j = i - n + 1; j <= i; j++) {
      if (tp[j] > tp[j - 1]) up += tp[j] * vol[j];
      else if (tp[j] < tp[j - 1]) down += tp[j] * vol[j];
    }
    o[i] = down === 0 ? (up === 0 ? 50 : 100) : 100 - 100 / (1 + up / down);
  }
  return o;
}
function connors(close) {   // ConnorsRSI: the average of RSI-3, the RSI of the up/down streak, and this move ranked against the last 100
  let run = 0;
  const streak = close.map((c, i) => (run = !i || c === close[i - 1] ? 0 : c > close[i - 1] ? Math.max(run, 0) + 1 : Math.min(run, 0) - 1));
  const r3 = rsi(close, 3), rs = rsi(streak, 2), move = close.map((c, i) => i ? c / close[i - 1] - 1 : 0);
  return close.map((_, i) => {
    if (i < 101 || r3[i] == null || rs[i] == null) return null;
    let below = 0;
    for (let j = i - 100; j < i; j++) if (move[j] < move[i]) below++;
    return (r3[i] + rs[i] + below) / 3;
  });
}
function stochRsi(r, n) {   // where RSI sits inside its own range of the last n candles, smoothed twice
  const raw = r.map((x, i) => {
    if (i < n - 1) return null;
    const w = r.slice(i - n + 1, i + 1);
    if (w.some(v => v == null)) return null;
    const hi = Math.max(...w), lo = Math.min(...w);
    return hi === lo ? 50 : (x - lo) / (hi - lo) * 100;
  });
  const k = avgN(raw, 3);
  return { k, d: avgN(k, 3) };
}
function chaikin(I, n) {   // Chaikin Money Flow: did candles close near their highs or lows, weighted by volume
  const flow = I.close.map((c, j) => { const r = I.high[j] - I.low[j]; return r > 0 ? ((c - I.low[j]) - (I.high[j] - c)) / r * I.vol[j] : 0; });
  return I.close.map((_, i) => {
    if (i < n - 1) return null;
    let f = 0, v = 0;
    for (let j = i - n + 1; j <= i; j++) { f += flow[j]; v += I.vol[j]; }
    return v > 0 ? f / v : 0;
  });
}
const NY_DATE = new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York" });
const nyDate = t => NY_DATE.format(new Date((t + OFF) * 1000));
// For each candle: the previous full New York day's high, low and close (on daily candles, the previous candle's),
// the index of the first candle of its day, and whether it's the last candle of its day
// (stock days end at 4 pm New York time, crypto days at midnight).
function sessions(I, tf) {
  const n = I.close.length, H = Array(n).fill(null), L = H.slice(), C = H.slice(), first = Array(n).fill(0), last = Array(n).fill(false);
  if (tf >= 1440) {
    for (let i = 0; i < n; i++) { first[i] = i; last[i] = true; if (i) { H[i] = I.high[i - 1]; L[i] = I.low[i - 1]; C[i] = I.close[i - 1]; } }
    return { H, L, C, first, last };
  }
  let day = null, days = 0, start = 0, stock = false, h = 0, l = 0, c = 0, ph = null, pl = null, pc = null;
  for (let i = 0; i < n; i++) {
    const d = nyDate(I.time[i]);
    if (d !== day) {
      if (days >= 2) { ph = h; pl = l; pc = c; }   // the first day in the data is usually partial, so it's skipped
      day = d; days++; start = i; h = -Infinity; l = Infinity;
      stock = nyClock(I.time[i] + OFF).mins >= 540;   // a day that starts after 9 am is a stock session
    }
    h = Math.max(h, I.high[i]); l = Math.min(l, I.low[i]); c = I.close[i];
    H[i] = ph; L[i] = pl; C[i] = pc; first[i] = start;
    const end = I.time[i] + tf * 60;
    last[i] = stock ? nyClock(end + OFF).mins >= 960 : nyDate(end) !== d;
  }
  return { H, L, C, first, last };
}

const HULL = I => get(I, "hull20", () => hull(I.close, 20));
const KAMA = I => get(I, "kama", () => kama(I.close));
const AROON = I => get(I, "aroon", () => aroon(I.high, I.low, 25));
const VORTEX = I => get(I, "vortex", () => vortex(I.high, I.low, I.close, 14));
const TRIX = I => get(I, "trix", () => {
  const t = ema(ema(ema(I.close, 15), 15), 15), x = t.map((v, j) => v == null || t[j - 1] == null ? null : (v / t[j - 1] - 1) * 1e4);
  return { x, sig: ema(x, 9) };
});
const REG20 = I => get(I, "reg20", () => regression(I.close, 20));
const E13 = I => get(I, "ema13", () => ema(I.close, 13));
const HIST = I => get(I, "hist", () => I.macd.map((m, j) => m == null || I.signal[j] == null ? null : m - I.signal[j]));
const GUPPY = I => get(I, "guppy", () => ({ fast: [3, 5, 8, 10, 12, 15].map(n => ema(I.close, n)), slow: [30, 35, 40, 45, 50, 60].map(n => ema(I.close, n)) }));
const AO = I => get(I, "ao", () => {
  const mid = I.high.map((h, j) => (h + I.low[j]) / 2), f = sma(mid, 5), s = sma(mid, 34);
  return mid.map((_, j) => s[j] == null ? null : f[j] - s[j]);
});
const CALM = I => get(I, "calm", () => {   // the median candle size (ATR as a share of price) over the last 100 candles
  const p = I.atr14.map((a, j) => a == null ? null : a / I.close[j]);
  return p.map((_, j) => { if (j < 113) return null; const w = p.slice(j - 99, j + 1).sort((a, b) => a - b); return (w[49] + w[50]) / 2; });
});
const TURTLE = I => get(I, "turtle", () => ({ hi: channel(I.high, 55, Math.max), lo: channel(I.low, 20, Math.min) }));
const KELT = I => get(I, "kelt", () => {
  const band = m => I.ema20.map((e, j) => e == null || I.atr14[j] == null ? null : e + m * I.atr14[j]);
  return { up: band(2), lo: band(-2) };
});
const CCI20 = I => get(I, "cci", () => cci(typical(I), 20));
const CRSI = I => get(I, "crsi", () => connors(I.close));
const SRSI = I => get(I, "srsi", () => stochRsi(I.rsi14, 14));
const CMF = I => get(I, "cmf", () => chaikin(I, 20));
const FORCE = I => get(I, "force", () => ({ efi2: ema(I.close.map((c, j) => j ? (c - I.close[j - 1]) * I.vol[j] : null), 2), ema22: ema(I.close, 22) }));
const MFI = I => get(I, "mfi", () => mfi(typical(I), I.vol, 14));
const SESS = (I, tf) => get(I, `sessions${tf}`, () => sessions(I, tf));

// ---------- helpers ----------
const pct = (x, dp = 1) => `${(x * 100).toFixed(dp)}%`;
const tfMins = () => +$("tf").value;
const warm = (n, i) => wait(`Warming up. Needs ${n} candles (has ${i + 1}).`);
const needBtc = () => wait("Needs bitcoin's prices for the same days. Only saved crypto baskets have them.");
const DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
// daily candles start at midnight UTC (crypto) or 9:30 am New York time (stocks), so their UTC date is the trading day
const utcDate = t => new Date((t + OFF) * 1000);
const hhmm = mins => `${String(Math.floor(mins / 60)).padStart(2, "0")}:${String(mins % 60).padStart(2, "0")}`;
function twoToOne(b, I, i, why, stop) {   // buy with a stop, and a take-profit twice as far above the close as the stop is below it
  const c = I.close[i], target = c + 2 * (c - stop);
  return enter(b, i, `${why} Stop ${fmtP(stop)}, target ${fmtP(target)}.`, { stop, target });
}

// ---------- the bots ----------
BOTS.push(
  // ----- trend followers -----
  { id: "above200", name: "Above the 200", type: "Trend", color: "#5aa9e6",
    desc: "The simplest trend rule, and one many long-term investors use. Owns it while price closes above its 200-candle average and sits in cash while it's below.",
    overlays: I => [["SMA 200", I.sma200, "#5aa9e6"]],
    decide(I, i, pos) {
      const s = I.sma200[i], c = I.close[i];
      if (s == null) return warm(200, i);
      if (!pos && c > s) return buy(`Closed at ${fmtP(c)}, above the 200-candle average (${fmtP(s)}). Uptrend: buying.`);
      if (pos && c < s) return sell(`Closed under the 200-candle average (${fmtP(s)}). Downtrend: selling.`);
      return wait(`${c > s ? "Above" : "Below"} the 200-candle average (${fmtP(s)}). ${pos ? "Holding." : "Waiting in cash."}`);
    } },
  { id: "hull", name: "Hull Turner", type: "Trend", color: "#7fc8f8",
    desc: "The Hull moving average is built to be smooth but quick to turn. Buys when the 20-candle Hull average turns up and sells when it turns down.",
    overlays: I => [["Hull 20", HULL(I), "#7fc8f8"]],
    decide(I, i, pos) {
      const h = HULL(I);
      if (h[i - 2] == null) return warm(25, i);
      const up = h[i] > h[i - 1], wasUp = h[i - 1] > h[i - 2];
      if (!pos && up && !wasUp) return buy(`The Hull average turned up (${fmtP(h[i - 1])} → ${fmtP(h[i])}). Buying.`);
      if (pos && !up) return sell("The Hull average turned down. Selling.");
      return wait(`Hull average heading ${up ? "up" : "down"}. ${pos ? "Holding." : up ? "Missed the turn. Waiting for the next one." : "Waiting for it to turn up."}`);
    } },
  { id: "kama", name: "Adaptive Average", type: "Trend", color: "#ffe45e",
    desc: "Kaufman's adaptive average (KAMA) moves fast when price trends cleanly and nearly stands still when the market is choppy, so it gets faked out less often. Buys a close above it and sells a close below it.",
    overlays: I => [["KAMA", KAMA(I), "#ffe45e"]],
    decide(I, i, pos) {
      const k = KAMA(I)[i], c = I.close[i];
      if (k == null) return warm(11, i);
      if (!pos && c > k) return buy(`Closed at ${fmtP(c)}, above the adaptive average (${fmtP(k)}). Buying.`);
      if (pos && c < k) return sell(`Closed under the adaptive average (${fmtP(k)}). Selling.`);
      return wait(`${c > k ? "Above" : "Below"} the adaptive average (${fmtP(k)}). ${pos ? "Holding." : "Waiting for a close above it."}`);
    } },
  { id: "aroon", name: "Aroon Trend", type: "Trend", color: "#ff6392",
    desc: "Aroon asks how recently price made its highest high and its lowest low of the last 25 candles. Buys when the high was very recent (Aroon Up 70 or more) and the low was long ago (Aroon Down 30 or less). Sells when Aroon Down moves above Aroon Up.",
    overlays: () => [],
    decide(I, i, pos) {
      const A = AROON(I), u = A.up[i], d = A.dn[i];
      if (u == null) return warm(26, i);
      if (!pos && u >= 70 && d <= 30) return buy(`Aroon Up ${u.toFixed(0)}, Aroon Down ${d.toFixed(0)}: fresh highs and old lows. Uptrend: buying.`);
      if (pos && d > u) return sell(`Aroon Down (${d.toFixed(0)}) moved above Aroon Up (${u.toFixed(0)}). The lows are now more recent than the highs.`);
      return wait(`Aroon Up ${u.toFixed(0)}, Aroon Down ${d.toFixed(0)}. ${pos ? "Holding." : "Waiting for Up 70+ with Down 30 or less."}`);
    } },
  { id: "vortex", name: "Vortex Crosser", type: "Trend", color: "#9b5de5",
    desc: "The Vortex indicator compares upward swings with downward swings over 14 candles. Buys when the upward line (VI+) crosses above the downward line (VI−) and sells when it falls back below.",
    overlays: () => [],
    decide(I, i, pos) {
      const V = VORTEX(I), p = V.plus, m = V.minus;
      if (p[i - 1] == null) return warm(16, i);
      const up = p[i] > m[i], wasUp = p[i - 1] > m[i - 1];
      if (!pos && up && !wasUp) return buy(`VI+ (${p[i].toFixed(2)}) crossed above VI− (${m[i].toFixed(2)}). Upward swings are winning: buying.`);
      if (pos && !up) return sell(`VI− (${m[i].toFixed(2)}) is back above VI+ (${p[i].toFixed(2)}). Selling.`);
      return wait(`VI+ ${p[i].toFixed(2)}, VI− ${m[i].toFixed(2)}. ${pos ? "Holding." : up ? "Missed the cross. Waiting for a fresh one." : "Waiting for VI+ to cross above."}`);
    } },
  { id: "trix", name: "TRIX Crosser", type: "Trend", color: "#f15bb5",
    desc: "TRIX is how fast a triple-smoothed average (EMA 15, three times over) is changing, which filters out most small wiggles. Buys when TRIX crosses above its 9-candle signal line and sells when it drops below.",
    overlays: () => [],
    decide(I, i, pos) {
      const T = TRIX(I), x = T.x, s = T.sig;
      if (s[i - 1] == null) return warm(53, i);
      const up = x[i] > s[i], wasUp = x[i - 1] > s[i - 1];
      if (!pos && up && !wasUp) return buy("TRIX crossed above its signal line. Smoothed momentum is turning up: buying.");
      if (pos && !up) return sell("TRIX dropped under its signal line. Momentum fading: selling.");
      return wait(`TRIX is ${up ? "above" : "below"} its signal. ${pos ? "Holding." : "No fresh cross up."}`);
    } },
  { id: "regress", name: "Regression Slope", type: "Trend", color: "#e4c1f9",
    desc: "Fits a straight line through the last 20 closes. Buys when the line slopes up and the closes hug it (R² of 0.6 or more: a steady climb, not a jumpy one). Sells when the line slopes down.",
    overlays: () => [],
    decide(I, i, pos) {
      const R = REG20(I), slope = R.slope[i], fit = R.r2[i];
      if (slope == null) return warm(20, i);
      const per = slope / I.close[i];
      if (!pos && per > 0 && fit >= 0.6) return buy(`Steady climb: the 20-candle line rises ${pct(per, 2)} per candle and fits the closes well (R² ${fit.toFixed(2)}). Buying.`);
      if (pos && per < 0) return sell(`The 20-candle line now slopes down (${pct(per, 2)} per candle). Selling.`);
      return wait(`Line ${per > 0 ? "rising" : "falling"} ${pct(Math.abs(per), 2)} per candle, R² ${fit.toFixed(2)}. ${pos ? "Holding." : "Buys a rise with R² 0.6+."}`);
    } },
  { id: "elder", name: "Elder Impulse", type: "Trend", color: "#00bbf9",
    desc: "Alexander Elder's impulse system colors each candle: green when both the 13-candle EMA and the MACD histogram are rising, red when both are falling, blue when they disagree. Buys on green and sells on red.",
    overlays: I => [["EMA 13", E13(I), "#00bbf9"]],
    decide(I, i, pos) {
      const e = E13(I), h = HIST(I);
      if (h[i - 1] == null || e[i - 1] == null) return warm(35, i);
      const green = e[i] > e[i - 1] && h[i] > h[i - 1], red = e[i] < e[i - 1] && h[i] < h[i - 1];
      if (!pos && green) return buy("Green impulse: the EMA 13 and the MACD histogram are both rising. Buying.");
      if (pos && red) return sell("Red impulse: the EMA 13 and the MACD histogram are both falling. Selling.");
      return wait(`${green ? "Green" : red ? "Red" : "Blue"} impulse. ${pos ? "Holding until a red one." : "Waiting for a green one."}`);
    } },
  { id: "guppy", name: "Guppy Ribbon", type: "Trend", color: "#3bceac",
    desc: "Daryl Guppy's ribbon: six fast averages (EMA 3 to 15) for short-term traders and six slow ones (EMA 30 to 60) for investors. Buys when every fast average is above every slow one and sells when the fast group, on average, drops under the slow group.",
    overlays: I => { const G = GUPPY(I); return [["EMA 3", G.fast[0], "#8ff7e5"], ["EMA 15", G.fast[5], "#3bceac"], ["EMA 30", G.slow[0], "#f28482"], ["EMA 60", G.slow[5], "#b23a48"]]; },
    decide(I, i, pos) {
      const G = GUPPY(I);
      if (G.slow[5][i] == null) return warm(60, i);
      const f = G.fast.map(x => x[i]), s = G.slow.map(x => x[i]), mean = v => v.reduce((a, x) => a + x, 0) / v.length;
      if (!pos && Math.min(...f) > Math.max(...s)) return buy("All six fast averages are above all six slow ones. Traders and investors agree: uptrend. Buying.");
      if (pos && mean(f) < mean(s)) return sell("The fast averages sank below the slow ones. Selling.");
      return wait(`Fast group ${mean(f) > mean(s) ? "above" : "below"} the slow group. ${pos ? "Holding." : "Waiting for every fast average to clear every slow one."}`);
    } },
  { id: "awesome", name: "Awesome Oscillator", type: "Trend", color: "#8ac926",
    desc: "Bill Williams' Awesome Oscillator: the 5-candle average of each candle's midpoint minus the 34-candle average. Buys when it crosses above zero (short-term momentum beating the longer-term) and sells when it drops below zero.",
    overlays: () => [],
    decide(I, i, pos) {
      const ao = AO(I);
      if (ao[i - 1] == null) return warm(35, i);
      if (!pos && ao[i] > 0 && ao[i - 1] <= 0) return buy("The Awesome Oscillator crossed above zero. Momentum turning up: buying.");
      if (pos && ao[i] < 0) return sell("The Awesome Oscillator dropped below zero. Selling.");
      return wait(`Oscillator ${ao[i] > 0 ? "above" : "below"} zero. ${pos ? "Holding." : ao[i] > 0 ? "Missed the cross. Waiting for a fresh one." : "Waiting for a cross above zero."}`);
    } },
  { id: "calm", name: "Calm Trend", type: "Trend", color: "#1982c4",
    desc: "Trends in quiet markets tend to be steadier. Buys when price is above its 50-candle average and candles are smaller than usual (ATR as a share of price, below its 100-candle median). Sells when price drops under the average or candles get 50% bigger than usual.",
    overlays: I => [["SMA 50", I.sma50, "#1982c4"]],
    decide(I, i, pos) {
      const med = CALM(I)[i], s = I.sma50[i], c = I.close[i];
      if (med == null || s == null) return warm(114, i);
      const rel = I.atr14[i] / c / med;
      if (!pos && c > s && rel < 1) return buy(`Above the 50-candle average, and candles are ${pct(1 - rel, 0)} smaller than usual. A calm uptrend: buying.`);
      if (pos && c < s) return sell(`Dropped under the 50-candle average (${fmtP(s)}). Selling.`);
      if (pos && rel > 1.5) return sell(`Candles are ${pct(rel - 1, 0)} bigger than usual. It's not calm anymore: selling.`);
      return wait(`Candles are ${pct(rel, 0)} of their usual size, price ${c > s ? "above" : "below"} the 50-candle average. ${pos ? "Holding." : "Needs calm and above the average."}`);
    } },
  { id: "committee", name: "Trend Committee", type: "Trend", color: "#a28bd4",
    desc: "Asks five trend signals at once: EMA 9 above EMA 21, MACD above its signal, price above the 50-candle average, Supertrend pointing up, and +DI above −DI. Buys when at least 4 agree and sells when 2 or fewer do.",
    overlays: I => [["SMA 50", I.sma50, "#a28bd4"]],
    decide(I, i, pos) {
      if (I.sma50[i] == null || I.signal[i] == null || I.st.dir[i] == null || I.dmi.pdi[i] == null) return warm(50, i);
      const votes = [["EMA 9 over 21", I.ema9[i] > I.ema21[i]], ["MACD over signal", I.macd[i] > I.signal[i]], ["above SMA 50", I.close[i] > I.sma50[i]],
                     ["Supertrend up", I.st.dir[i] === 1], ["+DI over −DI", I.dmi.pdi[i] > I.dmi.mdi[i]]];
      const yes = votes.filter(v => v[1]), n = yes.length, names = yes.map(v => v[0]).join(", ") || "none";
      if (!pos && n >= 4) return buy(`${n} of 5 say uptrend (${names}). Buying.`);
      if (pos && n <= 2) return sell(`Only ${n} of 5 still say uptrend (${names}). Selling.`);
      return wait(`${n} of 5 say uptrend (${names}). ${pos ? "Holding until 2 or fewer." : "Buys at 4 or more."}`);
    } },

  // ----- breakouts -----
  { id: "turtle", name: "Turtle 55", type: "Breakout", color: "#ff595e",
    desc: "The slower of the two systems taught to the famous 1980s 'Turtle' traders. Buys a close above the highest high of the last 55 candles and sells a close below the lowest low of the last 20.",
    overlays: I => { const T = TURTLE(I); return [["55-candle high", T.hi, "#ff595e"], ["20-candle low", T.lo, "#a33a3d"]]; },
    decide(I, i, pos) {
      const T = TURTLE(I), c = I.close[i], hi = T.hi[i], lo = T.lo[i];
      if (hi == null) return warm(56, i);
      if (!pos && c > hi) return buy(`Closed at ${fmtP(c)}, above the 55-candle high (${fmtP(hi)}). Breakout: buying.`);
      if (pos && c < lo) return sell(`Closed under the 20-candle low (${fmtP(lo)}). Selling.`);
      return wait(pos ? `Holding. Exits under ${fmtP(lo)}.` : `Needs a close above ${fmtP(hi)}.`);
    } },
  { id: "keltner", name: "Keltner Breakout", type: "Breakout", color: "#ffca3a",
    desc: "Keltner Channels sit 2 ATRs above and below the 20-candle EMA. A close above the top channel is an unusually strong push. Buys that and sells when price closes back under the EMA.",
    overlays: I => { const K = KELT(I); return [["Upper channel", K.up, "#ffca3a"], ["EMA 20", I.ema20, "#b38b1d"], ["Lower channel", K.lo, "#ffca3a"]]; },
    decide(I, i, pos) {
      const K = KELT(I), c = I.close[i], up = K.up[i], mid = I.ema20[i];
      if (up == null) return warm(20, i);
      if (!pos && c > up) return buy(`Closed at ${fmtP(c)}, above the upper Keltner channel (${fmtP(up)}). A strong push: buying.`);
      if (pos && c < mid) return sell(`Closed back under the EMA 20 (${fmtP(mid)}). Selling.`);
      return wait(pos ? `Holding while above ${fmtP(mid)}.` : `Needs a close above ${fmtP(up)}.`);
    } },
  { id: "darvas", name: "Darvas Box", type: "Breakout", color: "#e07a5f",
    desc: "Nicolas Darvas, a dancer who made a fortune in 1950s stocks, bought breakouts from 'boxes'. A box forms when a high holds for at least 3 candles while price moves sideways in a tight range (under 4 ATRs tall). Buys a close above the box, with a stop at its bottom. Also sells a close below the 10-candle low.",
    reset() { this.lv.top = []; this.lv.bottom = []; },
    overlays() { return [["Box top", this.lv.top, "#e07a5f"], ["Box bottom", this.lv.bottom, "#8f4a37"], ...riskLines(this)]; },
    decide(I, i, pos) {
      const a = I.atr14[i], c = I.close[i];
      if (pos) {
        const exit = checkExits(this, I, i);
        if (exit) return exit;
        const lo = Math.min(...I.low.slice(i - 10, i));
        if (c < lo) return sell(`Closed under the 10-candle low (${fmtP(lo)}). The move is over.`);
        return wait(`${holdingMsg(this)} Also exits under ${fmtP(lo)}.`);
      }
      if (i < 25 || a == null) return warm(25, i);
      let top = i - 20;
      for (let j = i - 20; j < i; j++) if (I.high[j] >= I.high[top]) top = j;
      if (i - top < 4) return wait("Price is still making new highs. No box yet.");
      const bottom = Math.min(...I.low.slice(top, i)), height = I.high[top] - bottom;
      if (height > 4 * a) return wait("Price is swinging too widely to form a box.");
      this.lv.top[i] = I.high[top]; this.lv.bottom[i] = bottom;
      if (c > I.high[top]) return enter(this, i, `Broke out of a box: closed above its top (${fmtP(I.high[top])}) after ${i - top} candles inside. Stop at the box bottom, ${fmtP(bottom)}.`, { stop: bottom });
      return wait(`Box from ${fmtP(bottom)} to ${fmtP(I.high[top])}. Waiting for a close above the top.`);
    } },
  { id: "wbreak", name: "Volatility Breakout", type: "Breakout", color: "#f4a261",
    desc: "Larry Williams' volatility breakout. When a candle rises from its open by more than 60% of the previous candle's whole range, buyers are unusually eager. Buys at that close and sells one candle later.",
    overlays() { return riskLines(this); },
    decide(I, i, pos) {
      if (pos) return checkExits(this, I, i) || wait("Holding for one candle.");
      if (i < 2) return warm(3, i);
      const prevRange = I.high[i - 1] - I.low[i - 1], push = I.close[i] - I.open[i];
      if (prevRange > 0 && push >= 0.6 * prevRange) return enter(this, i, `Rose ${fmtP(push)} from its open, more than 60% of the last candle's range (${fmtP(prevRange)}). Riding the burst for one candle.`, { maxBars: 1 });
      return wait(`Needs a rise of ${fmtP(0.6 * prevRange)} from the open. This candle: ${fmtP(push)}.`);
    } },
  { id: "bigcandle", name: "Big Candle", type: "Breakout", color: "#ff8c61",
    desc: "Buys a wide green candle: more than twice the normal size (2 ATRs) and closing in its top quarter, a sign of strong demand. Stop at the middle of that candle, and sells after 5 candles if the stop isn't hit.",
    overlays() { return riskLines(this); },
    decide(I, i, pos) {
      if (pos) return checkExits(this, I, i) || wait(`${holdingMsg(this)} ${5 - (i - this.st.entryIdx)} candles left.`);
      const a = I.atr14[i - 1];
      if (a == null) return warm(16, i);
      const h = I.high[i], l = I.low[i], range = h - l, c = I.close[i];
      if (range > 2 * a && isGreen(I, i) && c >= l + 0.75 * range) return enter(this, i, `A big green candle: ${(range / a).toFixed(1)} times the normal size, closing near its high. Stop at its middle, ${fmtP((h + l) / 2)}.`, { stop: (h + l) / 2, maxBars: 5 });
      return wait(`This candle is ${a > 0 ? (range / a).toFixed(1) : "–"} times the normal size. Needs a green one over 2, closing near its high.`);
    } },

  // ----- bounce (mean reversion) -----
  { id: "willr", name: "Williams %R", type: "Bounce", color: "#81b29a",
    desc: "Williams %R shows where price closed in its 14-candle range, from 0 (the top) to −100 (the bottom). Buys when it climbs back above −80 after being oversold and sells once it's above −20.",
    overlays: () => [],
    decide(I, i, pos) {
      const k = I.stoch.k;
      if (k[i - 1] == null) return warm(15, i);
      const w = k[i] - 100, before = k[i - 1] - 100;
      if (!pos && w > -80 && before <= -80) return buy(`Williams %R climbed out of oversold (${before.toFixed(0)} → ${w.toFixed(0)}). Buying.`);
      if (pos && w > -20) return sell(`Williams %R reached ${w.toFixed(0)}, near the top of the range. Selling.`);
      return wait(`Williams %R ${w.toFixed(0)}. ${pos ? "Holding until it's above −20." : "Waiting for a climb back above −80."}`);
    } },
  { id: "cci", name: "CCI Reversal", type: "Bounce", color: "#f2cc8f",
    desc: "The Commodity Channel Index measures how far price is from its 20-candle average. Under −100 is unusually low. Buys when CCI climbs back above −100 and sells when it's over +100, or after 20 candles.",
    overlays: () => [],
    decide(I, i, pos) {
      const x = CCI20(I);
      if (x[i - 1] == null) return warm(21, i);
      if (pos && x[i] > 100) return sell(`CCI reached ${x[i].toFixed(0)}. Selling the bounce.`);
      if (pos) return checkExits(this, I, i) || wait(`Holding until CCI is over 100 (now ${x[i].toFixed(0)}). ${20 - (i - this.st.entryIdx)} candles left.`);
      if (x[i] > -100 && x[i - 1] <= -100) return enter(this, i, `CCI climbed back above −100 (${x[i - 1].toFixed(0)} → ${x[i].toFixed(0)}). Buying the turn.`, { maxBars: 20 });
      return wait(`CCI ${x[i].toFixed(0)}. Waiting for it to climb back above −100.`);
    } },
  { id: "connors", name: "ConnorsRSI", type: "Bounce", color: "#98c1d9",
    desc: "Larry Connors' blend of three things: a very fast RSI (3 candles), how long the current up or down streak is, and how big the latest move is compared with the last 100. Buys when it's under 10 (a sharp, stretched drop) and sells when it's over 70.",
    overlays: () => [],
    decide(I, i, pos) {
      const x = CRSI(I)[i];
      if (x == null) return warm(102, i);
      if (!pos && x < 10) return buy(`ConnorsRSI is ${x.toFixed(0)}, deeply oversold. Buying.`);
      if (pos && x > 70) return sell(`ConnorsRSI is back up to ${x.toFixed(0)}. Selling.`);
      return wait(`ConnorsRSI ${x.toFixed(0)}. ${pos ? "Holding until it's over 70." : "Waiting for it to go under 10."}`);
    } },
  { id: "stochrsi", name: "Stochastic RSI", type: "Bounce", color: "#ee6c4d",
    desc: "Runs the Stochastic formula on RSI instead of price: where RSI sits inside its own 14-candle range. Buys when it turns up from under 20 and sells once it's above 80.",
    overlays: () => [],
    decide(I, i, pos) {
      const S = SRSI(I), k = S.k, d = S.d;
      if (d[i - 1] == null) return warm(33, i);
      if (!pos && k[i] > d[i] && k[i - 1] <= d[i - 1] && k[i] < 20) return buy(`Stochastic RSI turned up at ${k[i].toFixed(0)}, near the bottom of its range. Buying.`);
      if (pos && k[i] > 80) return sell(`Stochastic RSI hit ${k[i].toFixed(0)}. Selling.`);
      return wait(`Stochastic RSI ${k[i].toFixed(0)}. ${pos ? "Holding until it's above 80." : "Waiting for a turn up under 20."}`);
    } },
  { id: "sevens", name: "Double Sevens", type: "Bounce", color: "#b8f2e6",
    desc: "A simple rule from Larry Connors' book on short-term trading. In an uptrend (above the 200-candle average), buys the lowest close of the last 7 candles and sells the highest close of the last 7.",
    overlays: I => [["SMA 200", I.sma200, "#6fb7a6"]],
    decide(I, i, pos) {
      if (i < 7) return warm(8, i);
      const c = I.close[i], s = I.sma200[i], lo7 = Math.min(...I.close.slice(i - 6, i)), hi7 = Math.max(...I.close.slice(i - 6, i));
      if (pos && c >= hi7) return sell(`Highest close of the last 7 (${fmtP(c)}). Selling.`);
      if (pos) return wait(`Holding until a close above ${fmtP(hi7)}.`);
      if (s == null) return warm(200, i);
      if (c > s && c <= lo7) return buy("Uptrend, and this is the lowest close of the last 7 candles. Buying the dip.");
      return wait(c <= s ? "Below the 200-candle average. Not buying dips." : `Uptrend. Waiting for a close under ${fmtP(lo7)}.`);
    } },
  { id: "threered", name: "Three Lower Closes", type: "Bounce", color: "#ffa69e",
    desc: "Buys after three lower closes in a row and sells on the first close that's higher than the one before.",
    overlays: () => [],
    decide(I, i, pos) {
      if (i < 3) return warm(4, i);
      const c = I.close;
      if (pos && c[i] > c[i - 1]) return sell(`First higher close (${fmtP(c[i])}). Selling the bounce.`);
      if (pos) return wait("Holding until a close higher than the last one.");
      if (c[i] < c[i - 1] && c[i - 1] < c[i - 2] && c[i - 2] < c[i - 3]) return buy(`Three lower closes in a row (${fmtP(c[i - 3])} → ${fmtP(c[i])}). Betting on a bounce.`);
      return wait("Waiting for three lower closes in a row.");
    } },
  { id: "gap", name: "Gap Filler", type: "Bounce", color: "#aed9e0",
    desc: "When a candle opens well below the last close (a 'gap down'), price often drifts back up to 'fill the gap'. If a candle opens at least half an ATR under the previous close and is still below it at the close, buys with the previous close as the target, a stop 1 ATR under the candle's low, and a 5-candle limit. Gaps happen in stocks; crypto trades around the clock and rarely gaps.",
    overlays() { return riskLines(this); },
    decide(I, i, pos) {
      if (pos) return checkExits(this, I, i) || wait(`${holdingMsg(this)} ${5 - (i - this.st.entryIdx)} candles left.`);
      const a = I.atr14[i - 1], prev = I.close[i - 1], c = I.close[i];
      if (a == null) return warm(16, i);
      const gap = prev - I.open[i];
      if (gap >= 0.5 * a && c < prev) return enter(this, i, `Opened ${fmtP(gap)} under the last close and hasn't filled the gap. Target ${fmtP(prev)}.`, { target: prev, stop: I.low[i] - a, maxBars: 5 });
      return wait(gap > 0 ? `Small gap down (${fmtP(gap)}). Needs at least ${fmtP(0.5 * a)}.` : "No gap down.");
    } },
  { id: "panic", name: "Panic Candle Buyer", type: "Bounce", color: "#ff4f79",
    desc: "Buys right after a panic candle: a close more than 2.5 ATRs below the previous close. Aims to win back half the drop, with a stop 1.5 ATRs lower and a 10-candle limit.",
    overlays() { return riskLines(this); },
    decide(I, i, pos) {
      if (pos) return checkExits(this, I, i) || wait(`${holdingMsg(this)} ${10 - (i - this.st.entryIdx)} candles left.`);
      const a = I.atr14[i - 1], c = I.close[i];
      if (a == null) return warm(16, i);
      const drop = I.close[i - 1] - c, size = a > 0 ? drop / a : 0;
      if (size > 2.5) return enter(this, i, `Panic candle: fell ${fmtP(drop)} (${size.toFixed(1)} ATRs). Aiming to win back half.`, { target: c + drop / 2, stop: c - 1.5 * a, maxBars: 10 });
      return wait(`Last move: ${size >= 0 ? "down" : "up"} ${Math.abs(size).toFixed(1)} ATRs. Needs a drop of more than 2.5.`);
    } },

  // ----- candlestick and chart patterns -----
  { id: "soldiers", name: "Three White Soldiers", type: "Pattern", color: "#faf3dd",
    desc: "Candlestick pattern. After a drop, three strong green candles in a row, each opening inside the last one's body and closing higher, near its high. Buys with a stop under the first soldier and a target twice the risk.",
    overlays() { return riskLines(this); },
    decide(I, i, pos) {
      if (pos) return checkExits(this, I, i) || wait(holdingMsg(this));
      const a = I.atr14[i];
      if (a == null || i < 10) return warm(15, i);
      const strong = j => isGreen(I, j) && I.close[j] - I.open[j] > 0.4 * a && I.high[j] - I.close[j] <= 0.3 * (I.high[j] - I.low[j]);
      const stacked = j => I.close[j] > I.close[j - 1] && I.open[j] >= I.open[j - 1] && I.open[j] <= I.close[j - 1];
      const soldiers = [i - 2, i - 1, i].every(strong) && stacked(i) && stacked(i - 1);
      if (soldiers && I.close[i - 3] < I.close[i - 8]) return twoToOne(this, I, i, "Three white soldiers after a drop.", I.low[i - 2]);
      return wait(soldiers ? "Three strong green candles, but price wasn't falling before them. Skipping." : "No three white soldiers.");
    } },
  { id: "doji", name: "Doji at the Low", type: "Pattern", color: "#c9ada7",
    desc: "Candlestick pattern. A doji (open and close almost equal: buyers and sellers tied) at the lowest point of the last 10 candles, then a green candle closing above the doji's high. Buys with a stop under the low and a target twice the risk.",
    overlays() { return riskLines(this); },
    decide(I, i, pos) {
      if (pos) return checkExits(this, I, i) || wait(holdingMsg(this));
      const a = I.atr14[i];
      if (a == null || i < 12) return warm(15, i);
      const j = i - 1, range = I.high[j] - I.low[j];
      const doji = range >= 0.5 * a && Math.abs(I.close[j] - I.open[j]) <= 0.1 * range;
      const atLow = I.low[j] <= Math.min(...I.low.slice(i - 11, j));
      if (doji && atLow && isGreen(I, i) && I.close[i] > I.high[j]) return twoToOne(this, I, i, "A doji at a 10-candle low, confirmed by a green close above it.", Math.min(I.low[j], I.low[i]));
      return wait(doji && atLow ? `Doji at a 10-candle low. Needs a green close above ${fmtP(I.high[j])}.` : "No doji at a low.");
    } },
  { id: "harami", name: "Bullish Harami", type: "Pattern", color: "#cdb4ff",
    desc: "Candlestick pattern. After a drop, a big red candle followed by a small green one that fits inside the red candle's body: the selling ran out of steam. Buys with a stop under the pattern's low and a target twice the risk.",
    overlays() { return riskLines(this); },
    decide(I, i, pos) {
      if (pos) return checkExits(this, I, i) || wait(holdingMsg(this));
      const a = I.atr14[i];
      if (a == null || i < 7) return warm(15, i);
      const j = i - 1, redBody = I.open[j] - I.close[j], greenBody = I.close[i] - I.open[i];
      const harami = isRed(I, j) && redBody > a && isGreen(I, i) && I.open[i] >= I.close[j] && I.close[i] <= I.open[j] && greenBody < 0.5 * redBody;
      if (harami && I.close[j] < I.close[j - 5]) return twoToOne(this, I, i, "Bullish harami after a drop: a small green candle inside a big red one.", Math.min(I.low[j], I.low[i]));
      return wait(harami ? "Harami shape, but price wasn't falling before it. Skipping." : "No bullish harami.");
    } },
  { id: "keyrev", name: "Key Reversal", type: "Pattern", color: "#e9c46a",
    desc: "Chart pattern. After a drop, a candle dips below the previous candle's low but then closes above the previous candle's high: sellers pushed, buyers took over. Buys with a stop under that candle's low and a target twice the risk.",
    overlays() { return riskLines(this); },
    decide(I, i, pos) {
      if (pos) return checkExits(this, I, i) || wait(holdingMsg(this));
      if (i < 7) return warm(8, i);
      const rev = I.low[i] < I.low[i - 1] && I.close[i] > I.high[i - 1];
      if (rev && I.close[i - 1] < I.close[i - 6]) return twoToOne(this, I, i, `Key reversal: dipped under ${fmtP(I.low[i - 1])} and closed above ${fmtP(I.high[i - 1])}.`, I.low[i]);
      return wait(rev ? "Reversal candle, but price wasn't falling before it. Skipping." : "No key reversal.");
    } },
  { id: "nr7", name: "NR7 Breakout", type: "Pattern", color: "#84dcc6",
    desc: "Toby Crabel's NR7: the narrowest candle of the last 7 means the market is coiled. Buys when the next candle closes above that narrow candle's high, with a stop under it and a target twice the risk.",
    overlays() { return riskLines(this); },
    decide(I, i, pos) {
      if (pos) return checkExits(this, I, i) || wait(holdingMsg(this));
      if (i < 8) return warm(9, i);
      const rng = k => I.high[k] - I.low[k], j = i - 1;
      let narrowest = true;
      for (let k = j - 6; k < j; k++) if (rng(k) <= rng(j)) narrowest = false;
      if (narrowest && I.close[i] > I.high[j]) return twoToOne(this, I, i, `Broke out of an NR7 candle, closing above its high (${fmtP(I.high[j])}).`, Math.min(I.low[j], I.low[i]));
      return wait(narrowest ? `The last candle was the narrowest of 7. Needs a close above ${fmtP(I.high[j])}.` : "No NR7 candle.");
    } },
  { id: "dbottom", name: "Double Bottom", type: "Pattern", color: "#a5ffd6",
    desc: "The 'W' chart pattern. Two lows at about the same price (within half an ATR) with a real bounce between them, then a close above the top of that bounce (the 'neckline'). Buys with a stop under the lows and a target as far above the neckline as the lows are below it.",
    reset() { this.lv.neck = []; },
    overlays() { return [["Neckline", this.lv.neck, "#a5ffd6"], ...riskLines(this)]; },
    decide(I, i, pos) {
      if (pos) return checkExits(this, I, i) || wait(holdingMsg(this));
      const a = I.atr14[i];
      if (i < 60 || a == null) return warm(61, i);
      let first = i - 60;
      for (let j = i - 60; j <= i - 15; j++) if (I.low[j] <= I.low[first]) first = j;
      let second = first + 5;
      for (let j = first + 5; j < i; j++) if (I.low[j] <= I.low[second]) second = j;
      const neck = Math.max(...I.high.slice(first + 1, second)), bottom = Math.min(I.low[first], I.low[second]);
      const similar = Math.abs(I.low[second] - I.low[first]) <= 0.5 * a, bounced = neck - Math.max(I.low[first], I.low[second]) >= 2 * a;
      const fresh = i - second <= 20 && Math.max(...I.close.slice(second, i)) <= neck;
      if (!(similar && bounced && fresh)) return wait("No double bottom forming.");
      this.lv.neck[i] = neck;
      if (I.close[i] > neck) {
        const target = neck + (neck - bottom);
        return enter(this, i, `Double bottom: two lows near ${fmtP(bottom)}, then a close above the neckline (${fmtP(neck)}). Stop ${fmtP(bottom)}, target ${fmtP(target)}.`, { stop: bottom, target });
      }
      return wait(`Possible double bottom near ${fmtP(bottom)}. Needs a close above the neckline at ${fmtP(neck)}.`);
    } },

  // ----- levels -----
  { id: "pivot", name: "Pivot Bounce", type: "Levels", color: "#f9c74f",
    desc: "Floor traders' pivot points, worked out from the previous day's high, low and close (on daily candles, the previous candle's). Buys when price dips to the first support level (S1) and closes back above it. Target: the pivot. Stop: the second support level (S2).",
    reset() { this.lv.p = []; this.lv.s1 = []; },
    overlays() { return [["Pivot", this.lv.p, "#f9c74f"], ["S1", this.lv.s1, "#a8862f"], ...riskLines(this)]; },
    decide(I, i, pos) {
      if (pos) return checkExits(this, I, i) || wait(holdingMsg(this));
      const S = SESS(I, tfMins());
      if (S.H[i] == null) return wait("Waiting for a full previous day of candles.");
      const P = (S.H[i] + S.L[i] + S.C[i]) / 3, S1 = 2 * P - S.H[i], S2 = P - (S.H[i] - S.L[i]), c = I.close[i];
      this.lv.p[i] = P; this.lv.s1[i] = S1;
      if (I.low[i] <= S1 && c > S1 && c < P) return enter(this, i, `Dipped to support S1 (${fmtP(S1)}) and closed back above it. Target the pivot (${fmtP(P)}), stop at S2 (${fmtP(S2)}).`, { stop: S2, target: P });
      return wait(c > S1 ? `Pivot ${fmtP(P)}, support S1 ${fmtP(S1)}. Waiting for a dip to S1.` : `Under S1 (${fmtP(S1)}). Waiting for a candle that closes back above it.`);
    } },
  { id: "retest", name: "Breakout Retest", type: "Levels", color: "#90be6d",
    desc: "Doesn't chase breakouts. After price closes above the 20-candle high, it waits up to 10 candles for a pullback to that old high, then buys if price holds above it ('old ceiling, new floor'). Stop 1 ATR under the level, target twice the risk.",
    reset() { this.lv.level = []; },
    overlays() { return [["Breakout level", this.lv.level, "#90be6d"], ...riskLines(this)]; },
    decide(I, i, pos) {
      if (pos) return checkExits(this, I, i) || wait(holdingMsg(this));
      const a = I.atr14[i], hi = I.hi20[i], c = I.close[i];
      if (a == null || hi == null) return warm(21, i);
      let w = this.st.watch;
      if (w && (i - w.idx > 10 || c < w.level - a)) this.st.watch = w = null;   // no pullback in time, or the breakout failed
      if (w) {
        this.lv.level[i] = w.level;
        if (i > w.idx && I.low[i] <= w.level + 0.25 * a && c > w.level)
          return twoToOne(this, I, i, `Pulled back to the old high (${fmtP(w.level)}) it broke ${i - w.idx} candles ago and held above it.`, w.level - a);
        return wait(`Broke above ${fmtP(w.level)} ${i - w.idx} candles ago. Waiting for a pullback to it.`);
      }
      if (c > hi) {
        this.st.watch = { level: hi, idx: i };
        this.lv.level[i] = hi;
        return wait(`Broke above the 20-candle high (${fmtP(hi)}). Not chasing it: waiting for a pullback to that level.`);
      }
      return wait(`Waiting for a breakout above ${fmtP(hi)}.`);
    } },
  { id: "priorhigh", name: "Prior Day Breakout", type: "Levels", color: "#43aa8b",
    desc: "Buys the first close above yesterday's high (on daily candles, the high of the last 5 candles). Sells if price falls back under the middle of that range.",
    overlays: () => [],
    decide(I, i, pos) {
      const tf = tfMins(), c = I.close[i];
      let hi, lo, prevHi, label;
      if (tf >= 1440) {
        if (i < 6) return warm(7, i);
        hi = Math.max(...I.high.slice(i - 5, i)); lo = Math.min(...I.low.slice(i - 5, i)); prevHi = Math.max(...I.high.slice(i - 6, i - 1)); label = "the 5-candle";
      } else {
        const S = SESS(I, tf);
        if (S.H[i] == null || S.H[i - 1] == null) return wait("Waiting for a full previous day of candles.");
        hi = S.H[i]; lo = S.L[i]; prevHi = S.H[i - 1]; label = "yesterday's";
      }
      const mid = (hi + lo) / 2;
      if (!pos && c > hi && I.close[i - 1] <= prevHi) return buy(`Closed at ${fmtP(c)}, above ${label} high (${fmtP(hi)}). Buying.`);
      if (pos && c < mid) return sell(`Fell back under the middle of ${label} range (${fmtP(mid)}). Selling.`);
      return wait(pos ? `Holding. Exits under ${fmtP(mid)}.` : `Waiting for a close above ${label} high (${fmtP(hi)}).`);
    } },

  // ----- volume -----
  { id: "cmf", name: "Chaikin Money Flow", type: "Volume", color: "#4d908e",
    desc: "Chaikin Money Flow checks whether candles have been closing near their highs (buying) or lows (selling), weighted by volume, over 20 candles. Buys when it rises above +0.05 while price is above its 50-candle average, and sells when it drops under −0.05.",
    overlays: I => [["EMA 50", I.ema50, "#4d908e"]],
    decide(I, i, pos) {
      const f = CMF(I), e = I.ema50[i], c = I.close[i];
      if (f[i - 1] == null || e == null) return warm(50, i);
      if (!pos && f[i] > 0.05 && f[i - 1] <= 0.05 && c > e) return buy(`Money flow rose to ${f[i].toFixed(2)}: candles are closing near their highs on real volume. Buying.`);
      if (pos && f[i] < -0.05) return sell(`Money flow turned negative (${f[i].toFixed(2)}). Selling.`);
      return wait(`Money flow ${f[i].toFixed(2)}. ${pos ? "Holding until it's under −0.05." : "Buys a rise above 0.05 while above the 50-candle average."}`);
    } },
  { id: "force", name: "Force Index Dip", type: "Volume", color: "#6c8ebf",
    desc: "Alexander Elder's Force Index multiplies each price change by its volume. In an uptrend (22-candle EMA rising), buys when the 2-candle Force Index dips below zero (a short selloff) and sells when it turns positive again.",
    overlays: I => [["EMA 22", FORCE(I).ema22, "#6c8ebf"]],
    decide(I, i, pos) {
      const F = FORCE(I), f = F.efi2[i], e = F.ema22;
      if (e[i - 1] == null || f == null) return warm(23, i);
      const rising = e[i] > e[i - 1];
      if (!pos && rising && f < 0) return buy("Uptrend (EMA 22 rising), and the Force Index dipped below zero: a short selloff. Buying it.");
      if (pos && f > 0) return sell("The Force Index is back above zero. Selling the bounce.");
      return wait(`Force Index ${f < 0 ? "below" : "above"} zero, EMA 22 ${rising ? "rising" : "falling"}. ${pos ? "Holding." : "Buys a dip below zero in an uptrend."}`);
    } },
  { id: "mfi", name: "Money Flow Dip", type: "Volume", color: "#f94144",
    desc: "The Money Flow Index is like RSI but weighted by volume. Buys when it's under 20 (heavy selling) and sells when it recovers above 60.",
    overlays: () => [],
    decide(I, i, pos) {
      const m = MFI(I)[i];
      if (m == null) return warm(15, i);
      if (!pos && m < 20) return buy(`Money Flow Index is ${m.toFixed(0)}: heavy selling. Betting it's overdone.`);
      if (pos && m > 60) return sell(`Money Flow Index recovered to ${m.toFixed(0)}. Selling.`);
      return wait(`Money Flow Index ${m.toFixed(0)}. ${pos ? "Holding until it's over 60." : "Waiting for it to go under 20."}`);
    } },
  { id: "quiet", name: "Quiet Pullback", type: "Volume", color: "#f3722c",
    desc: "In an uptrend (EMA 20 above EMA 50), waits for three falling candles on light volume (under 80% of normal): sellers who aren't serious. Buys when a green candle then closes above the last high, with a stop under the pullback and a target twice the risk.",
    overlays() { return riskLines(this); },
    decide(I, i, pos) {
      if (pos) return checkExits(this, I, i) || wait(holdingMsg(this));
      const avg = I.volAvg20[i - 4], e20 = I.ema20[i], e50 = I.ema50[i];
      if (avg == null || e50 == null) return warm(50, i);
      const c = I.close, up = e20 > e50 && c[i] > e50;
      const pulled = [i - 3, i - 2, i - 1].every(j => c[j] < c[j - 1] && I.vol[j] < 0.8 * avg);
      if (up && pulled && isGreen(I, i) && c[i] > I.high[i - 1]) return twoToOne(this, I, i, "Uptrend, a 3-candle pullback on light volume, and now a green close above the last high.", Math.min(...I.low.slice(i - 3, i + 1)));
      return wait(!up ? "No uptrend (EMA 20 must be above EMA 50)." : pulled ? `Quiet pullback. Needs a green close above ${fmtP(I.high[i - 1])}.` : "Uptrend. Waiting for a pullback on light volume.");
    } },
  { id: "vwaprider", name: "VWAP Rider", type: "Volume", color: "#f8961e",
    desc: "The trend-following use of VWAP (the volume-weighted average price). Buys when price crosses above a rising 50-candle VWAP, meaning buyers are paying up, and sells a close back under it.",
    overlays: I => [["VWAP 50", I.vwap50, "#f8961e"]],
    decide(I, i, pos) {
      const v = I.vwap50, c = I.close[i];
      if (v[i - 5] == null) return warm(55, i);
      const rising = v[i] > v[i - 5];
      if (!pos && c > v[i] && I.close[i - 1] <= v[i - 1] && rising) return buy(`Crossed above a rising VWAP (${fmtP(v[i])}). Buying.`);
      if (pos && c < v[i]) return sell(`Closed under the VWAP (${fmtP(v[i])}). Selling.`);
      return wait(`${c > v[i] ? "Above" : "Below"} a ${rising ? "rising" : "falling"} VWAP (${fmtP(v[i])}). ${pos ? "Holding." : "Buys a cross above a rising VWAP."}`);
    } },

  // ----- position sizing -----
  { id: "streak", name: "Winning Streak Doubler", type: "Sizing", color: "#ff99ac",
    desc: "The opposite of Martingale: bets more after wins and less after losses. Trades the same EMA 9/21 crosses as Trend Rider, starting with 25% of its cash. After a winning trade the next bet doubles (25% → 50% → 100%); after a losing one it goes back to 25%.",
    reset() { this.st = { size: 0.25 }; },
    overlays: I => [["EMA 9", I.ema9, "#ffc2cf"], ["EMA 21", I.ema21, "#c9667a"]],
    decide(I, i, pos) {
      const a = I.ema9, b = I.ema21, size = this.st.size;
      if (b[i - 1] == null) return warm(22, i);
      const up = a[i] > b[i], wasUp = a[i - 1] > b[i - 1];
      if (!pos && up && !wasUp) return { act: "buy", frac: size, why: `EMA 9 crossed above EMA 21. Betting ${pct(size, 0)} of the cash.` };
      if (pos && !up && wasUp) return sell("EMA 9 crossed back below EMA 21. Trend over.");
      return wait(`Next bet: ${pct(size, 0)} of the cash. ${pos ? "Holding." : "Waiting for a cross up."}`);
    },
    filled(d, r) { if (d.act === "sell") this.st.size = r.pnl > 0 ? Math.min(1, this.st.size * 2) : 0.25; } },
  { id: "scaleout", name: "Scale-Out Trader", type: "Sizing", color: "#b9fbc0",
    desc: "Takes some profit early and lets the rest ride. Buys a close above the 20-candle high with a stop 2 ATRs down. When price is 2 ATRs up, sells half and moves the stop to break-even. Sells the rest on a close below the 10-candle low or at the stop.",
    reset() { this.st = {}; },
    overlays(I) { return [["20-candle high", I.hi20, "#b8862b"], ["Sell half at", this.lv.tp, "#26a69a"], ["Stop", this.lv.sl, "#ef5350"]]; },
    decide(I, i, pos) {
      const a = I.atr14[i], c = I.close[i], s = this.st, hi = I.hi20[i], lo = I.lo10[i];
      if (a == null || hi == null) return warm(21, i);
      if (!pos) return c > hi ? { act: "buy", atr: a, why: `Closed above the 20-candle high (${fmtP(hi)}). Buying, with a stop 2 ATRs down.` } : wait(`Needs a close above ${fmtP(hi)}.`);
      this.lv.sl[i] = s.stop;
      if (!s.half) this.lv.tp[i] = s.target;
      if (c <= s.stop) return sell(s.half ? `Back to the break-even stop (${fmtP(s.stop)}). Selling the rest.` : `Closed under the stop (${fmtP(s.stop)}). Cutting the loss.`);
      if (!s.half && c >= s.target) return { act: "sell", frac: 0.5, why: `Up 2 ATRs to ${fmtP(c)}. Selling half and moving the stop to break-even (${fmtP(s.entry)}).` };
      if (s.half && c < lo) return sell(`Closed under the 10-candle low (${fmtP(lo)}). Selling the rest.`);
      return wait(s.half ? `Half sold. Letting the rest ride; exits under ${fmtP(Math.max(s.stop, lo))}.` : `Holding. Sells half at ${fmtP(s.target)}, stop ${fmtP(s.stop)}.`);
    },
    filled(d, r) {
      if (d.act === "buy") this.st = { entry: r.fill, stop: r.fill - 2 * d.atr, target: r.fill + 2 * d.atr, half: false };
      else if (d.frac === 0.5) { this.st.half = true; this.st.stop = this.st.entry; }
      else this.st = {};
    } },
  { id: "ladder", name: "Ladder Buyer", type: "Sizing", color: "#fbc4ab",
    desc: "The 'DCA bot' that crypto exchanges sell. Splits the money into 5 equal parts: buys one right away, and another each time price drops 2 ATRs below the last buy. Sells everything once price is 1.5 ATRs above the average cost (never less than the fees). No stop-loss, so a long slide leaves it stuck holding.",
    reset() { this.st = { n: 0 }; },
    overlays() { return [["Sell target", this.lv.tp, "#26a69a"], ["Next buy", this.lv.sl, "#ef5350"]]; },
    decide(I, i, pos) {
      const a = I.atr14[i], c = I.close[i], ac = acct[this.id], s = this.st;
      if (a == null) return warm(15, i);
      if (!pos) return { act: "buy", frac: 0.2, step: 2 * a, why: "New ladder. Buying part 1 of 5; another part each time price drops 2 ATRs." };
      const avg = ac.cost / ac.qty, target = avg + Math.max(1.5 * a, avg * (2 * feeRate() + 0.002));
      this.lv.tp[i] = target;
      if (s.n < 5) this.lv.sl[i] = s.next;
      if (c >= target) return sell(`Reached ${fmtP(target)}, above the average cost of ${fmtP(avg)}. Selling all ${s.n} parts.`);
      if (s.n < 5 && c <= s.next) return { act: "buy", frac: 1 / (5 - s.n), step: 2 * a, why: `Dropped to ${fmtP(c)}. Buying part ${s.n + 1} of 5.` };
      return wait(s.n < 5 ? `${s.n} of 5 parts bought, average cost ${fmtP(avg)}. Sells at ${fmtP(target)}, next buy at ${fmtP(s.next)}.`
                          : `All 5 parts bought. Stuck holding until ${fmtP(target)}.`);
    },
    filled(d, r) {
      const s = this.st;
      if (d.act === "buy") { s.n++; s.next = r.fill - d.step; }
      else { s.n = 0; s.next = null; }
    } },
  { id: "risk1", name: "Risk 1% Per Trade", type: "Sizing", color: "#a0c4ff",
    desc: "The rule most trading books teach: size each trade so hitting the stop loses about 1% of the account. Buys a close above the 20-candle high with a stop 2 ATRs down, so a wild market means a small position. Sells at the stop or on a close below the 10-candle low.",
    overlays(I) { return [["20-candle high", I.hi20, "#b8862b"], ...riskLines(this)]; },
    decide(I, i, pos) {
      const a = I.atr14[i], c = I.close[i], hi = I.hi20[i], lo = I.lo10[i];
      if (pos) {
        const exit = checkExits(this, I, i);
        if (exit) return exit;
        if (c < lo) return sell(`Closed under the 10-candle low (${fmtP(lo)}). Selling.`);
        return wait(`${holdingMsg(this)} Also exits under ${fmtP(lo)}.`);
      }
      if (a == null || hi == null) return warm(21, i);
      if (c <= hi) return wait(`Needs a close above ${fmtP(hi)}.`);
      const stop = c - 2 * a, frac = Math.min(1, 0.01 * c / (c - stop));
      const d = enter(this, i, `Closed above the 20-candle high (${fmtP(hi)}). The stop is 2 ATRs down at ${fmtP(stop)}, so it buys with ${pct(frac, 0)} of the cash: if the stop hits, it loses about ${pct(frac * (c - stop) / c, 1)}.`, { stop });
      return { ...d, frac };
    } },

  // ----- time -----
  { id: "tuesday", name: "Turnaround Tuesday", type: "Time", color: "#caffbf",
    desc: "An old stock-market saying: after a down Monday, Tuesday tends to bounce. Buys at Monday's close if Monday closed lower than Friday (crypto: Sunday) and sells at Tuesday's close. Needs daily candles.",
    overlays: () => [],
    decide(I, i, pos) {
      if (tfMins() !== 1440) return wait("Needs daily candles.");
      if (i < 1) return warm(2, i);
      const day = utcDate(I.time[i]).getUTCDay(), change = I.close[i] / I.close[i - 1] - 1;
      if (pos && day !== 1) return sell(`${DAYS[day]}'s close. Trade done: selling.`);
      if (pos) return wait("Holding into Tuesday.");
      if (day === 1 && change < 0) return buy(`Monday closed down ${pct(-change)}. Betting on a Tuesday bounce.`);
      return wait(day === 1 ? "Monday closed up. No trade this week." : `${DAYS[day]}. Waiting for a down Monday.`);
    } },
  { id: "tom", name: "Turn of the Month", type: "Time", color: "#ffc8dd",
    desc: "Stocks have historically done better around the turn of each month, when paychecks and retirement money get invested. Owns it from the last 4 days of each month through the 3rd day of the next, and sits in cash the rest of the time. Needs daily candles.",
    overlays: () => [],
    decide(I, i, pos) {
      if (tfMins() !== 1440) return wait("Needs daily candles.");
      const d = utcDate(I.time[i]), day = d.getUTCDate(), dim = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0)).getUTCDate();
      const inTurn = day >= dim - 3 || day <= 2;
      if (!pos && inTurn) return buy(day > 2 ? `Day ${day} of ${dim}: the turn of the month is here. Buying.` : `Day ${day} of the new month, still inside the turn. Buying.`);
      if (pos && !inTurn) return sell(`Day ${day} of the month. The turn is over: selling.`);
      return wait(pos ? `Day ${day}. Holding through the turn of the month.` : `Day ${day} of ${dim}. Buys on day ${dim - 3}.`);
    } },
  { id: "overnight", name: "Overnight Holder", type: "Time", color: "#8093f1",
    desc: "Research on US stocks has found that much of their long-run gain came overnight, between the close and the next morning's open. Buys at the last candle before 4 pm New York time and sells once the market is open again. On crypto that means owning it every evening, night and weekend. Needs candles of 1 hour or shorter.",
    overlays: () => [],
    decide(I, i, pos) {
      const tf = tfMins();
      if (tf > 60) return wait("Needs candles of 1 hour or shorter to see the time of day.");
      const t = nyClock(I.time[i] + OFF + tf * 60), open = t.day !== "Sat" && t.day !== "Sun" && t.mins >= 570 && t.mins < 960;
      const when = `${t.day} ${hhmm(t.mins)} in New York.`;
      if (!pos && !open) return buy(`${when} The US market is closed: holding overnight.`);
      if (pos && open) return sell(`${when} The market is open again: selling.`);
      return wait(`${when} ${open ? "Market hours. Waiting in cash for the close." : "Market closed. Holding until the next open."}`);
    } },
  { id: "orb", name: "Opening Range Breakout", type: "Time", color: "#72ddf7",
    desc: "A classic day-trading setup. Marks the high and low of each day's first 30 minutes (from 9:30 am New York time for stocks, midnight New York time for crypto). Buys the first close above that range, with a stop at the range's low, and sells at the day's last candle. One trade a day. Needs candles of 15 minutes or shorter.",
    reset() { this.lv.rh = []; },
    overlays() { return [["Opening range high", this.lv.rh, "#72ddf7"], ...riskLines(this)]; },
    decide(I, i, pos) {
      const tf = tfMins();
      if (tf > 15) return wait("Needs candles of 15 minutes or shorter.");
      const S = SESS(I, tf), f = S.first[i], k = Math.round(30 / tf);
      if (pos) {
        if (S.last[i]) return sell("Last candle of the day. Day trades don't stay open overnight: selling.");
        return checkExits(this, I, i) || wait(`${holdingMsg(this)} Sells at the day's last candle.`);
      }
      if (i - f + 1 < k) return wait(`The opening range is forming: ${i - f + 1} of ${k} candles.`);
      let hi = -Infinity, lo = Infinity;
      for (let j = f; j < f + k; j++) { hi = Math.max(hi, I.high[j]); lo = Math.min(lo, I.low[j]); }
      this.lv.rh[i] = hi;
      if (this.st.day === f) return wait("Already traded today's range. Waiting for tomorrow.");
      if (S.last[i]) return wait("Last candle of the day. Too late to start a trade.");
      if (I.close[i] > hi && i >= f + k) {
        const d = enter(this, i, `Closed at ${fmtP(I.close[i])}, above the first 30 minutes' high (${fmtP(hi)}). Stop at the range low, ${fmtP(lo)}.`, { stop: lo });
        this.st.day = f;
        return d;
      }
      return wait(`Opening range ${fmtP(lo)} to ${fmtP(hi)}. Waiting for a close above ${fmtP(hi)}.`);
    } },

  // ----- compared with bitcoin (saved crypto baskets only) -----
  { id: "btcfollow", name: "Bitcoin Follower", type: "vs Bitcoin", color: "#f7b267",
    desc: "Smaller coins often follow bitcoin with a delay. Buys a coin that moved less than 1% on a day bitcoin jumped 3% or more, and sells 3 days later. Needs a saved crypto basket.",
    overlays() { return riskLines(this); },
    decide(I, i, pos) {
      if (!I.btc) return needBtc();
      if (pos) return checkExits(this, I, i) || wait(`Holding. ${3 - (i - this.st.entryIdx)} days left.`);
      if (i < 1) return warm(2, i);
      const b = I.btc[i] / I.btc[i - 1] - 1, own = I.close[i] / I.close[i - 1] - 1;
      if (b >= 0.03 && own < 0.01) return enter(this, i, `Bitcoin jumped ${pct(b)} today, but this coin only moved ${pct(own)}. Betting it catches up within 3 days.`, { maxBars: 3 });
      return wait(`Bitcoin ${pct(b)} today, this coin ${pct(own)}. Waiting for bitcoin to jump 3%+ while this coin lags.`);
    } },
  { id: "ratiobreak", name: "Ratio Breakout", type: "vs Bitcoin", color: "#f4845f",
    desc: "Watches the coin's price measured in bitcoin. Buys when that ratio closes at its highest of the last 30 days (the coin is suddenly outrunning bitcoin) and sells when it closes at its lowest of the last 10. Needs a saved crypto basket.",
    overlays: () => [],
    decide(I, i, pos) {
      if (!I.btc) return needBtc();
      if (i < 31) return warm(32, i);
      const r = I.ratio, hi = Math.max(...r.slice(i - 30, i)), lo = Math.min(...r.slice(i - 10, i));
      if (!pos && r[i] > hi) return buy("Measured in bitcoin, this coin just closed at a 30-day high. It's outrunning bitcoin: buying.");
      if (pos && r[i] < lo) return sell("Measured in bitcoin, it closed at a 10-day low. Selling.");
      return wait(`Measured in bitcoin, it's ${pct(r[i] / hi - 1)} from its 30-day high. ${pos ? "Holding." : "Waiting for a new high."}`);
    } },
  { id: "ratiosnap", name: "Ratio Snapback", type: "vs Bitcoin", color: "#f25c54",
    desc: "Bets that a coin which suddenly falls far behind bitcoin catches back up. Buys when the coin's price in bitcoin is 2 standard deviations below its 30-day average, and sells when it's back to the average. Needs a saved crypto basket.",
    overlays: () => [],
    decide(I, i, pos) {
      if (!I.btc) return needBtc();
      if (i < 30) return warm(31, i);
      const w = I.ratio.slice(i - 29, i + 1), m = w.reduce((a, x) => a + x, 0) / 30;
      const sd = Math.sqrt(w.reduce((a, x) => a + (x - m) ** 2, 0) / 30), r = I.ratio[i], z = sd > 0 ? (r - m) / sd : 0;
      if (!pos && z < -2) return buy(`Measured in bitcoin, it's ${Math.abs(z).toFixed(1)} standard deviations below its 30-day average. Betting it catches up.`);
      if (pos && r >= m) return sell("Back to its 30-day average against bitcoin. Selling.");
      return wait(`${z.toFixed(1)} standard deviations from its 30-day average against bitcoin. ${pos ? "Holding until it's back to average." : "Buys under −2."}`);
    } },

  // ----- controls: no edge on purpose, to measure the other bots against -----
  { id: "randomexit", name: "Random Entry, 2:1 Exits", type: "Control", color: "#b0a8b9",
    desc: "A check on the pattern bots. Enters at random (a 1-in-10 chance each candle while out) but exits the way they do: a stop 1.5 ATRs down and a take-profit 3 ATRs up. If a pattern can't beat this, the exits were doing the work, not the pattern.",
    reset() { this.rng = mulberry32(7); },
    overlays() { return riskLines(this); },
    decide(I, i, pos) {
      if (pos) return checkExits(this, I, i) || wait(holdingMsg(this));
      const a = I.atr14[i], c = I.close[i];
      if (a == null) return warm(15, i);
      if (this.rng() < 0.1) return enter(this, i, `Random entry. Stop 1.5 ATRs down (${fmtP(c - 1.5 * a)}), target 3 ATRs up (${fmtP(c + 3 * a)}).`, { stop: c - 1.5 * a, target: c + 3 * a });
      return wait("The dice said not yet.");
    } },
  { id: "opposite", name: "Opposite Day", type: "Control", color: "#d4a5a5",
    desc: "Trend Rider backwards: buys when EMA 9 crosses below EMA 21 and sells when it crosses back above. If Trend Rider and this both lose, the crosses don't mean much either way.",
    overlays: I => [["EMA 9", I.ema9, "#f0c9c9"], ["EMA 21", I.ema21, "#9c6b6b"]],
    decide(I, i, pos) {
      const a = I.ema9, b = I.ema21;
      if (b[i - 1] == null) return warm(22, i);
      const up = a[i] > b[i], wasUp = a[i - 1] > b[i - 1];
      if (!pos && !up && wasUp) return buy("EMA 9 crossed below EMA 21. Doing the opposite of Trend Rider: buying.");
      if (pos && up && !wasUp) return sell("EMA 9 crossed back above EMA 21. Doing the opposite: selling.");
      return wait(pos ? "Holding until EMA 9 crosses back above EMA 21." : "Waiting for EMA 9 to cross below EMA 21.");
    } },
);
})();

// A third batch of Live Arena bots (added 2026-09-12), appended to the BOTS list after more_bots.js.
// index.html's bot section and more_bots.js are frozen because paper tests use their bots, so new bots go here.
// None of these bots are in a paper test. Same ground rules: decide only on closed candles, paper money only.
(() => {
"use strict";

// ---------- indicators: each is computed the first time a bot asks for it, once per set of candles ----------
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
function rma(v, n) {   // Wilder's smoothed average (SMMA)
  const o = Array(v.length).fill(null);
  let s = 0;
  for (let i = 0; i < v.length; i++) {
    if (i < n - 1) s += v[i];
    else if (i === n - 1) o[i] = (s + v[i]) / n;
    else o[i] = (o[i - 1] * (n - 1) + v[i]) / n;
  }
  return o;
}
const roc = (v, n) => v.map((x, i) => i >= n ? (x / v[i - n] - 1) * 100 : null);
const shift = (v, n) => v.map((_, i) => i >= n ? v[i - n] : null);   // a line drawn n candles ahead: its value at i was known n candles earlier
function mcginley(close, n) {   // McGinley Dynamic: an average that speeds up when price runs away from it
  const o = Array(close.length).fill(null);
  for (let i = n; i < close.length; i++) {
    if (o[i - 1] == null) { o[i] = close.slice(i - n + 1, i + 1).reduce((a, x) => a + x, 0) / n; continue; }
    const md = o[i - 1];
    o[i] = md + (close[i] - md) / Math.max(1, n * (close[i] / md) ** 4);   // never steps past the price
  }
  return o;
}
function kst(close) {   // Martin Pring's Know Sure Thing: four smoothed rates of change, the slower ones weighted more
  const r = [[10, 10], [15, 10], [20, 10], [30, 15]].map(([a, b]) => avgN(roc(close, a), b));
  const k = close.map((_, i) => r.some(x => x[i] == null) ? null : r[0][i] + 2 * r[1][i] + 3 * r[2][i] + 4 * r[3][i]);
  return { k, sig: avgN(k, 9) };
}
function schaff(close) {   // Schaff Trend Cycle: MACD run through the Stochastic formula twice, 0 to 100
  const e1 = ema(close, 23), e2 = ema(close, 50), o = Array(close.length).fill(null), pfs = [];
  const m = close.map((_, i) => e1[i] == null || e2[i] == null ? null : e1[i] - e2[i]);
  let f1 = 0, f2 = 0, pf = null, st = null;
  for (let i = 0; i < close.length; i++) {
    if (i < 58 || m[i - 9] == null) { pfs.push(null); continue; }
    const w = m.slice(i - 9, i + 1), lo = Math.min(...w), hi = Math.max(...w);
    if (hi > lo) f1 = (m[i] - lo) / (hi - lo) * 100;
    pf = pf == null ? f1 : pf + 0.5 * (f1 - pf);
    pfs.push(pf);
    const w2 = pfs.slice(-10);
    if (w2.some(x => x == null)) continue;
    const lo2 = Math.min(...w2), hi2 = Math.max(...w2);
    if (hi2 > lo2) f2 = (pf - lo2) / (hi2 - lo2) * 100;
    o[i] = st = st == null ? f2 : st + 0.5 * (f2 - st);
  }
  return o;
}
function renko(I) {   // bricks 1 ATR tall: +n after n up bricks in a row, -n after n down bricks in a row
  const n = I.close.length, run = Array(n).fill(null);
  let base = null, r = 0;
  for (let i = 0; i < n; i++) {
    const a = I.atr14[i], c = I.close[i];
    if (a == null || !(a > 0)) continue;
    if (base == null) base = c;
    else if (c >= base + a) { const k = Math.floor((c - base) / a); base += k * a; r = r > 0 ? r + k : k; }
    else if (c <= base - a) { const k = Math.floor((base - c) / a); base -= k * a; r = r < 0 ? r - k : -k; }
    run[i] = r;
  }
  return run;
}
function ultimate(I) {   // Larry Williams' Ultimate Oscillator: buying pressure over 7, 14 and 28 candles
  const n = I.close.length, bp = Array(n).fill(0), tr = Array(n).fill(0), o = Array(n).fill(null);
  for (let i = 1; i < n; i++) {
    const lo = Math.min(I.low[i], I.close[i - 1]), hi = Math.max(I.high[i], I.close[i - 1]);
    bp[i] = I.close[i] - lo; tr[i] = hi - lo;
  }
  const avg = (i, len) => { let b = 0, t = 0; for (let j = i - len + 1; j <= i; j++) { b += bp[j]; t += tr[j]; } return t > 0 ? b / t : 0.5; };
  for (let i = 28; i < n; i++) o[i] = 100 * (4 * avg(i, 7) + 2 * avg(i, 14) + avg(i, 28)) / 7;
  return o;
}
function fisher(I, len) {   // John Ehlers' Fisher Transform: stretches price's place in its range so turns stand out
  const n = I.close.length, f = Array(n).fill(null);
  let v = 0, prev = 0;
  for (let i = len - 1; i < n; i++) {
    let hi = -Infinity, lo = Infinity;
    for (let j = i - len + 1; j <= i; j++) { const mid = (I.high[j] + I.low[j]) / 2; hi = Math.max(hi, mid); lo = Math.min(lo, mid); }
    const mid = (I.high[i] + I.low[i]) / 2;
    v = Math.max(-0.999, Math.min(0.999, 0.66 * (hi > lo ? (mid - lo) / (hi - lo) - 0.5 : 0) + 0.67 * v));
    prev = f[i] = 0.5 * Math.log((1 + v) / (1 - v)) + 0.5 * prev;
  }
  return f;
}
function cmo(close, n) {   // Chande Momentum Oscillator: up moves minus down moves, as a share of all moves, -100 to 100
  const o = Array(close.length).fill(null);
  for (let i = n; i < close.length; i++) {
    let up = 0, down = 0;
    for (let j = i - n + 1; j <= i; j++) { const d = close[j] - close[j - 1]; if (d > 0) up += d; else down -= d; }
    o[i] = up + down > 0 ? 100 * (up - down) / (up + down) : 0;
  }
  return o;
}
function fractals(I) {   // Bill Williams' fractals: a high (or low) beyond the 2 candles on each side, confirmed 2 candles later
  const n = I.close.length, up = Array(n).fill(null), dn = Array(n).fill(null), h = I.high, l = I.low;
  let lastUp = null, lastDown = null;
  for (let i = 4; i < n; i++) {
    const k = i - 2;
    if (h[k] > h[k - 1] && h[k] > h[k - 2] && h[k] > h[k + 1] && h[k] > h[k + 2]) lastUp = h[k];
    if (l[k] < l[k - 1] && l[k] < l[k - 2] && l[k] < l[k + 1] && l[k] < l[k + 2]) lastDown = l[k];
    up[i] = lastUp; dn[i] = lastDown;
  }
  return { up, dn };
}
const NY_DATE = new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York" });
const nyDate = t => NY_DATE.format(new Date((t + OFF) * 1000));
// The day's VWAP, restarting each New York day, plus each candle's first candle of the day and whether it's the day's last
// candle (stock days end at 4 pm New York time, crypto days at midnight). Same day rules as more_bots.js.
function sessionVwap(I, tf) {
  const n = I.close.length, vw = Array(n).fill(null), first = Array(n).fill(0), last = Array(n).fill(false);
  let day = null, pv = 0, v = 0, start = 0, stock = false;
  for (let i = 0; i < n; i++) {
    const d = nyDate(I.time[i]);
    if (d !== day) { day = d; pv = 0; v = 0; start = i; stock = nyClock(I.time[i] + OFF).mins >= 540; }
    pv += (I.high[i] + I.low[i] + I.close[i]) / 3 * I.vol[i]; v += I.vol[i];
    vw[i] = v > 0 ? pv / v : null; first[i] = start;
    const end = I.time[i] + tf * 60;
    last[i] = stock ? nyClock(end + OFF).mins >= 960 : nyDate(end) !== d;
  }
  return { vw, first, last };
}
// For each candle: how often, so far, the next candle closed higher after the same up/down pattern of 3 candles
function markov(close) {
  const n = close.length, ups = Array(8).fill(0), seen = Array(8).fill(0), prob = Array(n).fill(null), count = Array(n).fill(0), state = Array(n).fill(null);
  const code = j => (close[j] > close[j - 1] ? 4 : 0) + (close[j - 1] > close[j - 2] ? 2 : 0) + (close[j - 2] > close[j - 3] ? 1 : 0);
  for (let i = 4; i < n; i++) {
    const before = code(i - 1);   // the pattern that candle i just answered
    seen[before]++;
    if (close[i] > close[i - 1]) ups[before]++;
    const s = state[i] = code(i);
    count[i] = seen[s];
    prob[i] = seen[s] ? ups[s] / seen[s] : null;
  }
  return { prob, count, state };
}
function shapes(I, len) {   // each candle's last `len` moves, measured in ATRs so any price level compares
  return I.close.map((_, j) => {
    const a = I.atr14[j];
    if (a == null || !(a > 0) || j < len + 1) return null;
    const out = new Float64Array(len);
    for (let t = 0; t < len; t++) out[t] = (I.close[j - len + 1 + t] - I.close[j - len + t]) / a;
    return out;
  });
}

const MCG = I => get(I, "mcginley", () => mcginley(I.close, 14));
const KST = I => get(I, "kst", () => kst(I.close));
const STC = I => get(I, "stc", () => schaff(I.close));
const ALLIGATOR = I => get(I, "alligator", () => {
  const mid = I.high.map((h, j) => (h + I.low[j]) / 2);
  return { jaw: shift(rma(mid, 13), 8), teeth: shift(rma(mid, 8), 5), lips: shift(rma(mid, 5), 3) };
});
const E13 = I => get(I, "ema13", () => ema(I.close, 13));
const RENKO = I => get(I, "renko", () => renko(I));
const COPPOCK = I => get(I, "coppock", () => {
  const a = roc(I.close, 14), b = roc(I.close, 11);
  return wma(a.map((x, j) => x == null || b[j] == null ? null : x + b[j]), 10);
});
const UO = I => get(I, "uo", () => ultimate(I));
const FISHER = I => get(I, "fisher", () => fisher(I, 10));
const CMO = I => get(I, "cmo", () => cmo(I.close, 20));
const FRACTALS = I => get(I, "fractals", () => fractals(I));
const CHOSC = I => get(I, "chosc", () => {   // Chaikin Oscillator: EMA 3 minus EMA 10 of the accumulation/distribution line
  let adl = 0;
  const line = I.close.map((c, j) => { const r = I.high[j] - I.low[j]; return (adl += r > 0 ? ((c - I.low[j]) - (I.high[j] - c)) / r * I.vol[j] : 0); });
  const fast = ema(line, 3), slow = ema(line, 10);
  return line.map((_, j) => slow[j] == null ? null : fast[j] - slow[j]);
});
const SMA10 = I => get(I, "sma10", () => sma(I.close, 10));
const NVI = I => get(I, "nvi", () => {   // Negative Volume Index: only moves on days with less volume than the day before
  let x = 1000;
  const line = I.close.map((c, j) => (x = j && I.vol[j] < I.vol[j - 1] ? x * c / I.close[j - 1] : x));
  return { line, avg: ema(line, 200) };
});
const SVWAP = (I, tf) => get(I, `svwap${tf}`, () => sessionVwap(I, tf));
const MARKOV = I => get(I, "markov", () => markov(I.close));
const SHAPES = I => get(I, "shapes", () => shapes(I, 5));

// ---------- helpers ----------
const pct = (x, dp = 1) => `${(x * 100).toFixed(dp)}%`;
const tfMins = () => +$("tf").value;
const warm = (n, i) => wait(`Warming up. Needs ${n} candles (has ${i + 1}).`);
const utcDate = t => new Date((t + OFF) * 1000);   // a daily candle's UTC date is its trading day
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const hhmm = mins => `${String(Math.floor(mins / 60)).padStart(2, "0")}:${String(mins % 60).padStart(2, "0")}`;
function twoToOne(b, I, i, why, stop) {   // buy with a stop, and a take-profit twice as far above the close as the stop is below it
  const c = I.close[i], target = c + 2 * (c - stop);
  return enter(b, i, `${why} Stop ${fmtP(stop)}, target ${fmtP(target)}.`, { stop, target });
}
function knnVote(I, i, k = 15) {   // of the 15 past 5-candle shapes most like the latest one, the share followed by a higher close
  const S = SHAPES(I), now = S[i], c = I.close, best = [];
  if (!now) return null;
  for (let j = 0; j < i; j++) {   // j + 1 <= i, so every outcome counted is already known
    const past = S[j];
    if (!past) continue;
    let d = 0;
    for (let t = 0; t < now.length; t++) d += (now[t] - past[t]) ** 2;
    if (best.length === k && d >= best[k - 1][0]) continue;
    best.push([d, c[j + 1] > c[j]]);
    best.sort((x, y) => x[0] - y[0]);
    if (best.length > k) best.pop();
  }
  return best.length < k ? null : best.filter(x => x[1]).length / k;
}
function kellyBet(results) {   // half the Kelly bet from the last 20 trades' returns, between 10% and 100% of the cash
  if (results.length < 5) return { frac: 0.25, why: `Only ${results.length} past trades, so it bets a starter 25%.` };
  const wins = results.filter(x => x > 0), losses = results.filter(x => x <= 0), w = wins.length / results.length;
  const avgWin = wins.length ? wins.reduce((a, x) => a + x, 0) / wins.length : 0;
  const avgLoss = losses.length ? -losses.reduce((a, x) => a + x, 0) / losses.length : 0;
  const kelly = avgWin > 0 && avgLoss > 0 ? w - (1 - w) / (avgWin / avgLoss) : wins.length ? 1 : 0;
  const frac = Math.min(1, Math.max(0.1, kelly / 2));
  return { frac, why: `It won ${Math.round(w * 100)}% of its last ${results.length} trades (average win ${pct(avgWin)}, average loss ${pct(avgLoss)}), so half-Kelly bets ${pct(frac, 0)} of the cash.` };
}

// ---------- the bots ----------
BOTS.push(
  // ----- trend followers -----
  { id: "mcginley", name: "McGinley Dynamic", type: "Trend", color: "#6fd3ff",
    desc: "The McGinley Dynamic is a moving average that speeds up when price runs away from it, so it lags less than a normal average. Buys when price closes above it after being below, and sells a close back under it.",
    overlays: I => [["McGinley Dynamic", MCG(I), "#6fd3ff"]],
    decide(I, i, pos) {
      const md = MCG(I), c = I.close;
      if (md[i - 1] == null) return warm(16, i);
      if (!pos && c[i] > md[i] && c[i - 1] <= md[i - 1]) return buy(`Closed above the McGinley Dynamic (${fmtP(md[i])}). Buying.`);
      if (pos && c[i] < md[i]) return sell(`Closed under the McGinley Dynamic (${fmtP(md[i])}). Selling.`);
      return wait(`${c[i] > md[i] ? "Above" : "Below"} the McGinley Dynamic (${fmtP(md[i])}). ${pos ? "Holding." : "Waiting for a fresh close above it."}`);
    } },
  { id: "kst", name: "Know Sure Thing", type: "Trend", color: "#ffb86b",
    desc: "Martin Pring's Know Sure Thing (KST) adds up four smoothed rates of change, from fast to slow, with the slow ones counting more. Buys when KST crosses above its 9-candle signal line and sells when it crosses back below.",
    overlays: () => [],
    decide(I, i, pos) {
      const K = KST(I), k = K.k, s = K.sig;
      if (s[i - 1] == null) return warm(54, i);
      const up = k[i] > s[i], wasUp = k[i - 1] > s[i - 1];
      if (!pos && up && !wasUp) return buy("KST crossed above its signal line. Momentum at every speed is turning up: buying.");
      if (pos && !up) return sell("KST dropped under its signal line. Selling.");
      return wait(`KST is ${up ? "above" : "below"} its signal. ${pos ? "Holding." : "No fresh cross up."}`);
    } },
  { id: "stc", name: "Schaff Trend Cycle", type: "Trend", color: "#c3f73a",
    desc: "The Schaff Trend Cycle runs MACD through the Stochastic formula twice to get a smooth line from 0 to 100 that turns early. Buys when it climbs above 25 and sells when it turns down through 75 (or falls back under 25).",
    overlays: () => [],
    decide(I, i, pos) {
      const s = STC(I);
      if (s[i - 1] == null) return warm(68, i);
      if (!pos && s[i] > 25 && s[i - 1] <= 25) return buy(`The Schaff Trend Cycle climbed above 25 (${s[i].toFixed(0)}). A new up-cycle is starting: buying.`);
      if (pos && s[i] < 25) return sell(`The cycle fell back under 25 (${s[i].toFixed(0)}). Selling.`);
      if (pos && s[i] < 75 && s[i - 1] >= 75) return sell(`The cycle turned down through 75 (${s[i].toFixed(0)}). Selling.`);
      return wait(`Schaff Trend Cycle ${s[i].toFixed(0)}. ${pos ? "Holding." : "Waiting for a climb above 25."}`);
    } },
  { id: "alligator", name: "Williams Alligator", type: "Trend", color: "#57cc99",
    desc: "Bill Williams' Alligator draws three smoothed averages pushed forward in time: the jaw (13 candles), teeth (8) and lips (5). When they're tangled the alligator is 'sleeping'. Buys when lips are above teeth above jaw with price above all three, and sells when the lips drop under the teeth.",
    overlays: I => { const A = ALLIGATOR(I); return [["Jaw", A.jaw, "#3a86ff"], ["Teeth", A.teeth, "#ff006e"], ["Lips", A.lips, "#57cc99"]]; },
    decide(I, i, pos) {
      const A = ALLIGATOR(I), jaw = A.jaw[i], teeth = A.teeth[i], lips = A.lips[i], c = I.close[i];
      if (jaw == null) return warm(21, i);
      const stacked = lips > teeth && teeth > jaw;
      if (!pos && stacked && c > lips) return buy("The Alligator is awake and eating: lips above teeth above jaw, with price above all three. Buying.");
      if (pos && lips < teeth) return sell("The Alligator's lips crossed under its teeth. It's going back to sleep: selling.");
      return wait(stacked ? (pos ? "Lines stacked upward. Holding." : "Lines stacked upward. Waiting for price above the lips.") : "The Alligator is sleeping (its lines are tangled or pointing down).");
    } },
  { id: "elderray", name: "Elder Ray", type: "Trend", color: "#ff9f1c",
    desc: "Alexander Elder's Elder Ray measures Bear Power: how far each candle's low reached below the 13-candle EMA. Buys when the EMA is rising and Bear Power is below zero but shrinking (sellers pushed, but less hard), and sells when the EMA turns down.",
    overlays: I => [["EMA 13", E13(I), "#ff9f1c"]],
    decide(I, i, pos) {
      const e = E13(I);
      if (e[i - 1] == null) return warm(14, i);
      const rising = e[i] > e[i - 1], bear = I.low[i] - e[i], bearBefore = I.low[i - 1] - e[i - 1];
      if (!pos && rising && bear < 0 && bear > bearBefore) return buy(`EMA 13 rising, and Bear Power (${fmtP(bear)}) is below zero but weaker than last candle. Buying the dip in the uptrend.`);
      if (pos && !rising) return sell("The EMA 13 turned down. Selling.");
      return wait(`EMA 13 ${rising ? "rising" : "falling"}, Bear Power ${fmtP(bear)}. ${pos ? "Holding." : "Waiting for a shrinking dip below the EMA in an uptrend."}`);
    } },
  { id: "rsitrend", name: "RSI Trend", type: "Trend", color: "#90f1ef",
    desc: "Uses RSI the other way round: instead of buying when it's low, it treats RSI above 55 as an uptrend. Buys when RSI (14) is over 55 and sells when it drops under 45.",
    overlays: () => [],
    decide(I, i, pos) {
      const r = I.rsi14[i];
      if (r == null) return warm(15, i);
      if (!pos && r > 55) return buy(`RSI is ${r.toFixed(0)}, over 55. Buyers are in charge: buying.`);
      if (pos && r < 45) return sell(`RSI dropped to ${r.toFixed(0)}, under 45. Selling.`);
      return wait(`RSI ${r.toFixed(0)}. ${pos ? "Holding until it's under 45." : "Waiting for it to go over 55."}`);
    } },
  { id: "yearmom", name: "One-Year Momentum", type: "Trend", color: "#ffd6a5",
    desc: "The long-term momentum rule from academic research: own it while it's higher than it was 250 candles ago (about a year of stock-market days on daily candles), and sit in cash while it's lower.",
    overlays: () => [],
    decide(I, i, pos) {
      if (i < 250) return warm(251, i);
      const change = I.close[i] / I.close[i - 250] - 1;
      if (!pos && change > 0) return buy(`Up ${pct(change)} over the last 250 candles. Buying.`);
      if (pos && change < 0) return sell(`Down ${pct(-change)} over the last 250 candles. Selling.`);
      return wait(`250-candle change ${pct(change)}. ${pos ? "Holding." : "Waiting for it to turn positive."}`);
    } },
  { id: "renko", name: "Renko Bricks", type: "Trend", color: "#e5989b",
    desc: "Renko charts ignore time and draw a new brick only when price moves a full brick size (here 1 ATR). Buys after 2 up bricks in a row and sells after 2 down bricks in a row, which filters out small wiggles.",
    overlays: () => [],
    decide(I, i, pos) {
      const r = RENKO(I)[i];
      if (r == null) return warm(15, i);
      if (!pos && r >= 2) return buy(`${r} up bricks in a row (each brick is 1 ATR). Uptrend: buying.`);
      if (pos && r <= -2) return sell(`${-r} down bricks in a row. Selling.`);
      return wait(`${r === 0 ? "No bricks yet" : `${Math.abs(r)} ${r > 0 ? "up" : "down"} brick${Math.abs(r) === 1 ? "" : "s"} in a row`}. ${pos ? "Holding until 2 down bricks." : "Waiting for 2 up bricks."}`);
    } },
  { id: "coppock", name: "Coppock Turn", type: "Trend", color: "#b8c0ff",
    desc: "The Coppock Curve was designed in the 1960s to spot the bottom of a bear market: a weighted average of two rates of change (14 and 11 candles). Buys when it turns up while still below zero, and sells when it turns back down.",
    overlays: () => [],
    decide(I, i, pos) {
      const c = COPPOCK(I);
      if (c[i - 2] == null) return warm(26, i);
      const turnedUp = c[i] > c[i - 1] && c[i - 1] <= c[i - 2], turnedDown = c[i] < c[i - 1] && c[i - 1] >= c[i - 2];
      if (!pos && turnedUp && c[i - 1] < 0) return buy(`The Coppock Curve turned up from below zero (${c[i - 1].toFixed(1)}). The classic bottom signal: buying.`);
      if (pos && turnedDown) return sell("The Coppock Curve turned down. Selling.");
      return wait(`Coppock Curve ${c[i].toFixed(1)}, heading ${c[i] > c[i - 1] ? "up" : "down"}. ${pos ? "Holding until it turns down." : "Waiting for a turn up below zero."}`);
    } },
  { id: "threeup", name: "Three Higher Closes", type: "Trend", color: "#a0e426",
    desc: "The momentum mirror image of Three Lower Closes: buys after three higher closes in a row and sells on the first close that's lower than the one before.",
    overlays: () => [],
    decide(I, i, pos) {
      if (i < 3) return warm(4, i);
      const c = I.close;
      if (pos && c[i] < c[i - 1]) return sell(`First lower close (${fmtP(c[i])}). Selling.`);
      if (pos) return wait("Holding until a close lower than the last one.");
      if (c[i] > c[i - 1] && c[i - 1] > c[i - 2] && c[i - 2] > c[i - 3]) return buy(`Three higher closes in a row (${fmtP(c[i - 3])} → ${fmtP(c[i])}). Riding the momentum.`);
      return wait("Waiting for three higher closes in a row.");
    } },
  { id: "holygrail", name: "Holy Grail", type: "Trend", color: "#ffe066",
    desc: "Linda Raschke's 'Holy Grail': in a strong uptrend (ADX over 30, +DI above −DI), wait for a pullback that touches the 20-candle EMA, then buy when price closes back above that pullback candle's high. Stop under the pullback low, target twice the risk.",
    overlays(I) { return [["EMA 20", I.ema20, "#ffe066"], ...riskLines(this)]; },
    decide(I, i, pos) {
      if (pos) return checkExits(this, I, i) || wait(holdingMsg(this));
      const D = I.dmi, e = I.ema20;
      if (D.adx[i - 1] == null || e[i - 1] == null) return warm(29, i);
      const strong = D.adx[i - 1] > 30 && D.pdi[i - 1] > D.mdi[i - 1], touched = I.low[i - 1] <= e[i - 1];
      if (strong && touched && I.close[i] > I.high[i - 1]) return twoToOne(this, I, i, `Strong uptrend (ADX ${D.adx[i - 1].toFixed(0)}) pulled back to the EMA 20, and price closed back above the pullback candle's high.`, I.low[i - 1]);
      return wait(strong ? (touched ? `Pullback touched the EMA 20. Needs a close above ${fmtP(I.high[i - 1])}.` : `Strong uptrend. Waiting for a pullback to the EMA 20 (${fmtP(e[i])}).`) : "No strong uptrend (needs ADX over 30 with +DI above −DI).");
    } },

  // ----- bounce (mean reversion) -----
  { id: "ultimate", name: "Ultimate Oscillator", type: "Bounce", color: "#9bf6ff",
    desc: "Larry Williams' Ultimate Oscillator blends buying pressure over 7, 14 and 28 candles so one timeframe can't fool it. Buys when it climbs back above 30 and sells when it's over 65.",
    overlays: () => [],
    decide(I, i, pos) {
      const u = UO(I);
      if (u[i - 1] == null) return warm(30, i);
      if (!pos && u[i] > 30 && u[i - 1] <= 30) return buy(`The Ultimate Oscillator climbed back above 30 (${u[i].toFixed(0)}). Buying the turn.`);
      if (pos && u[i] > 65) return sell(`Ultimate Oscillator at ${u[i].toFixed(0)}. Selling the bounce.`);
      return wait(`Ultimate Oscillator ${u[i].toFixed(0)}. ${pos ? "Holding until it's over 65." : "Waiting for a climb back above 30."}`);
    } },
  { id: "fisher", name: "Fisher Transform", type: "Bounce", color: "#fdffb6",
    desc: "John Ehlers' Fisher Transform stretches where price sits in its 10-candle range so extreme turns stand out. Buys when it turns up from below −1.5 and sells when it turns down from above +1.5, or after 20 candles.",
    overlays: () => [],
    decide(I, i, pos) {
      const f = FISHER(I);
      if (f[i - 2] == null) return warm(12, i);
      if (pos && f[i - 1] > 1.5 && f[i] < f[i - 1]) return sell(`The Fisher Transform turned down from ${f[i - 1].toFixed(1)}. Selling the bounce.`);
      if (pos) return checkExits(this, I, i) || wait(`Holding until it turns down from above 1.5 (now ${f[i].toFixed(1)}). ${20 - (i - this.st.entryIdx)} candles left.`);
      if (f[i - 1] < -1.5 && f[i] > f[i - 1] && f[i - 1] <= f[i - 2]) return enter(this, i, `The Fisher Transform turned up from ${f[i - 1].toFixed(1)}, a stretched low. Buying the turn.`, { maxBars: 20 });
      return wait(`Fisher Transform ${f[i].toFixed(1)}. Waiting for a turn up from under −1.5.`);
    } },
  { id: "cmo", name: "Chande Momentum", type: "Bounce", color: "#caffbf",
    desc: "Tushar Chande's Momentum Oscillator compares the size of up moves with down moves over 20 candles, from −100 to +100. Buys when it climbs back above −50 and sells when it's over +50.",
    overlays: () => [],
    decide(I, i, pos) {
      const m = CMO(I);
      if (m[i - 1] == null) return warm(22, i);
      if (!pos && m[i] > -50 && m[i - 1] <= -50) return buy(`Chande Momentum climbed back above −50 (${m[i].toFixed(0)}). The selling is easing: buying.`);
      if (pos && m[i] > 50) return sell(`Chande Momentum reached ${m[i].toFixed(0)}. Selling the bounce.`);
      return wait(`Chande Momentum ${m[i].toFixed(0)}. ${pos ? "Holding until it's over 50." : "Waiting for a climb back above −50."}`);
    } },
  { id: "soup", name: "Turtle Soup", type: "Bounce", color: "#ffadad",
    desc: "Linda Raschke's 'Turtle Soup' fades the breakouts the Turtle traders bought. When price dips under a 20-candle low that's at least 4 candles old but closes back above it, the breakdown failed. Buys that, with a stop under the new low and a target twice the risk.",
    overlays() { return riskLines(this); },
    decide(I, i, pos) {
      if (pos) return checkExits(this, I, i) || wait(holdingMsg(this));
      if (i < 21) return warm(22, i);
      let k = i - 20;
      for (let j = i - 20; j < i; j++) if (I.low[j] <= I.low[k]) k = j;
      const old = I.low[k];
      if (I.low[i] < old && i - k >= 4 && I.close[i] > old) return twoToOne(this, I, i, `Turtle soup: dipped under the 20-candle low (${fmtP(old)}, set ${i - k} candles ago) and closed back above it. The breakdown failed.`, I.low[i]);
      return wait(I.low[i] < old ? `New 20-candle low, still under ${fmtP(old)}. No reversal.` : `The 20-candle low is ${fmtP(old)}. Waiting for a failed breakdown.`);
    } },
  { id: "divergence", name: "Bullish Divergence", type: "Bounce", color: "#bdb2ff",
    desc: "Price makes a lower low, but RSI makes a higher low: the drop is losing force. When that happens (with the earlier RSI low under 35) and the next candle closes green above the last high, it buys. Stop under the low. Sells when RSI is over 65 or after 30 candles.",
    overlays() { return riskLines(this); },
    decide(I, i, pos) {
      const r = I.rsi14;
      if (pos && r[i] > 65) return sell(`RSI is back up to ${r[i].toFixed(0)}. Selling.`);
      if (pos) return checkExits(this, I, i) || wait(`${holdingMsg(this)} Sells when RSI is over 65 (now ${r[i].toFixed(0)}).`);
      if (i < 44 || r[i - 30] == null) return warm(45, i);
      let a = i - 30, b = i - 5;
      for (let j = i - 30; j <= i - 6; j++) if (I.low[j] <= I.low[a]) a = j;
      for (let j = i - 5; j <= i; j++) if (I.low[j] <= I.low[b]) b = j;
      const div = I.low[b] < I.low[a] && r[b] > r[a] && r[a] < 35 && i - b <= 3;
      if (div && isGreen(I, i) && I.close[i] > I.high[i - 1]) return enter(this, i, `Bullish divergence: price made a lower low (${fmtP(I.low[b])} vs ${fmtP(I.low[a])}) but RSI made a higher low (${r[b].toFixed(0)} vs ${r[a].toFixed(0)}). Stop ${fmtP(I.low[b])}.`, { stop: I.low[b], maxBars: 30 });
      return wait(div ? `Divergence spotted. Needs a green close above ${fmtP(I.high[i - 1])}.` : "No bullish divergence.");
    } },
  { id: "pullback50", name: "50-Candle Pullback", type: "Bounce", color: "#ffc6ff",
    desc: "A favorite of swing traders: in an uptrend (the 50-candle average above the 200 and rising), buy when price dips to the 50-candle average and closes back above it. Target the recent high, stop 1.5 ATRs under the average.",
    overlays(I) { return [["SMA 50", I.sma50, "#ffc6ff"], ["SMA 200", I.sma200, "#9d4edd"], ...riskLines(this)]; },
    decide(I, i, pos) {
      if (pos) return checkExits(this, I, i) || wait(holdingMsg(this));
      const s50 = I.sma50, s200 = I.sma200[i], a = I.atr14[i], c = I.close[i];
      if (s200 == null || s50[i - 10] == null) return warm(200, i);
      const up = s50[i] > s200 && s50[i] > s50[i - 10];
      if (up && I.low[i] <= s50[i] && c > s50[i]) {
        const target = Math.max(...I.high.slice(i - 20, i)), stop = s50[i] - 1.5 * a;
        if (target > c) return enter(this, i, `Uptrend, and price dipped to the 50-candle average (${fmtP(s50[i])}) and closed back above it. Target the recent high ${fmtP(target)}, stop ${fmtP(stop)}.`, { stop, target });
      }
      return wait(up ? `Uptrend. Waiting for a dip to the 50-candle average (${fmtP(s50[i])}).` : "No uptrend (the 50-candle average must be above the 200 and rising).");
    } },

  // ----- breakouts -----
  { id: "volbreak", name: "Breakout on Volume", type: "Breakout", color: "#f9844a",
    desc: "Only trusts a breakout that has real buying behind it: a close above the 20-candle high on at least twice the normal volume. Sells a close below the 10-candle low.",
    overlays: I => [["20-candle high", I.hi20, "#f9844a"], ["10-candle low", I.lo10, "#9c4f2c"]],
    decide(I, i, pos) {
      const c = I.close[i], hi = I.hi20[i], lo = I.lo10[i], avg = I.volAvg20[i - 1];
      if (hi == null || avg == null) return warm(21, i);
      if (pos && c < lo) return sell(`Closed under the 10-candle low (${fmtP(lo)}). Selling.`);
      if (pos) return wait(`Holding. Exits under ${fmtP(lo)}.`);
      const ratio = avg > 0 ? I.vol[i] / avg : 0;
      if (c > hi && ratio >= 2) return buy(`Closed above the 20-candle high (${fmtP(hi)}) on ${ratio.toFixed(1)}x normal volume. A breakout with buyers behind it.`);
      return wait(c > hi ? `Breakout, but volume is only ${ratio.toFixed(1)}x normal. Skipping.` : `Needs a close above ${fmtP(hi)} on twice the normal volume.`);
    } },
  { id: "fractal", name: "Fractal Breakout", type: "Breakout", color: "#43bccd",
    desc: "Bill Williams' fractals mark a candle whose high (or low) beats the 2 candles on each side. Buys when price closes above the latest up fractal and sells when it closes below the latest down fractal.",
    overlays: I => { const F = FRACTALS(I); return [["Up fractal", F.up, "#43bccd"], ["Down fractal", F.dn, "#a4508b"]]; },
    decide(I, i, pos) {
      const F = FRACTALS(I), c = I.close;
      if (i < 5) return warm(6, i);
      const lvl = F.up[i - 1], floor = F.dn[i];
      if (pos && floor != null && c[i] < floor) return sell(`Closed under the latest down fractal (${fmtP(floor)}). Selling.`);
      if (pos) return wait(floor != null ? `Holding. Exits under ${fmtP(floor)}.` : "Holding.");
      if (lvl != null && c[i] > lvl && c[i - 1] <= lvl) return buy(`Closed above the latest up fractal (${fmtP(lvl)}). Breakout: buying.`);
      return wait(lvl != null ? `Latest up fractal ${fmtP(lvl)}. Waiting for a close above it.` : "No up fractal yet.");
    } },
  { id: "flag", name: "Bull Flag", type: "Breakout", color: "#f15152",
    desc: "The classic continuation pattern. A 'pole' (a rise of at least 3 ATRs in 5 candles), then a short 'flag' of 2 to 7 candles drifting down that gives back less than half the pole, then a close above the flag. Target: the pole's height again. Stop: the flag's low.",
    overlays() { return riskLines(this); },
    decide(I, i, pos) {
      if (pos) return checkExits(this, I, i) || wait(holdingMsg(this));
      const a = I.atr14[i], c = I.close;
      if (a == null || i < 20) return warm(20, i);
      for (let f = 3; f <= 8; f++) {
        const top = i - f, pole = c[top] - c[top - 5];
        if (pole < 3 * a) continue;
        const flagHigh = Math.max(...I.high.slice(top, i)), flagLow = Math.min(...I.low.slice(top + 1, i));
        if (c[top] - flagLow > 0.5 * pole || c[i - 1] > c[top] || flagLow >= c[i]) continue;
        if (c[i] > flagHigh) return enter(this, i, `Bull flag: a ${fmtP(pole)} pole, a ${f - 1}-candle flag, and now a close above it (${fmtP(flagHigh)}). Target ${fmtP(c[i] + pole)}, stop ${fmtP(flagLow)}.`, { stop: flagLow, target: c[i] + pole });
      }
      return wait("No bull flag breaking out.");
    } },
  { id: "gapgo", name: "Gap and Go", type: "Breakout", color: "#ff7b00",
    desc: "A day-trader favorite for stocks: when a candle opens above the previous candle's high (a gap up of at least a quarter ATR) and keeps rising to close above its open, ride it. Stop under that candle's low, and sells after 3 candles. Crypto rarely gaps.",
    overlays() { return riskLines(this); },
    decide(I, i, pos) {
      if (pos) return checkExits(this, I, i) || wait(`${holdingMsg(this)} ${3 - (i - this.st.entryIdx)} candles left.`);
      const a = I.atr14[i - 1];
      if (a == null) return warm(16, i);
      const gap = I.open[i] - I.high[i - 1];
      if (gap >= 0.25 * a && I.close[i] > I.open[i]) return enter(this, i, `Gapped up ${fmtP(gap)} above the last candle's high and kept rising. Riding it for up to 3 candles, stop ${fmtP(I.low[i])}.`, { stop: I.low[i], maxBars: 3 });
      return wait(gap > 0 ? `Small gap up (${fmtP(gap)}). Needs a quarter ATR (${fmtP(0.25 * a)}) and a rise after the open.` : "No gap up.");
    } },

  // ----- candlestick patterns -----
  { id: "piercing", name: "Piercing Line", type: "Pattern", color: "#e76f51",
    desc: "Candlestick pattern. After a drop, a big red candle, then a green candle that opens at or below the red close and closes above the middle of the red body (but not above its open). Buys with a stop under the pattern and a target twice the risk.",
    overlays() { return riskLines(this); },
    decide(I, i, pos) {
      if (pos) return checkExits(this, I, i) || wait(holdingMsg(this));
      const a = I.atr14[i];
      if (a == null) return warm(15, i);
      const j = i - 1, mid = (I.open[j] + I.close[j]) / 2;
      const pierce = isRed(I, j) && I.open[j] - I.close[j] > 0.6 * a && isGreen(I, i) && I.open[i] <= I.close[j] && I.close[i] > mid && I.close[i] < I.open[j];
      if (pierce && I.close[j] < I.close[j - 5]) return twoToOne(this, I, i, `Piercing line after a drop: the green candle closed past the middle of the red one (${fmtP(mid)}).`, Math.min(I.low[j], I.low[i]));
      return wait(pierce ? "Piercing shape, but price wasn't falling before it. Skipping." : "No piercing line.");
    } },
  { id: "tweezer", name: "Tweezer Bottom", type: "Pattern", color: "#8ecae6",
    desc: "Candlestick pattern. Two candles in a row with almost the same low (within a tenth of an ATR) at the lowest point of the last 10 candles, a red one then a green one: price tested a floor twice and held. Buys with a stop just under the floor and a target twice the risk.",
    overlays() { return riskLines(this); },
    decide(I, i, pos) {
      if (pos) return checkExits(this, I, i) || wait(holdingMsg(this));
      const a = I.atr14[i];
      if (a == null || i < 12) return warm(15, i);
      const j = i - 1, floor = Math.min(I.low[i], I.low[j]);
      const tweezer = isRed(I, j) && isGreen(I, i) && Math.abs(I.low[i] - I.low[j]) <= 0.1 * a && floor <= Math.min(...I.low.slice(i - 11, j));
      if (tweezer) return twoToOne(this, I, i, `Tweezer bottom: two lows at about ${fmtP(floor)}, the lowest of the last 10 candles.`, floor - 0.1 * a);
      return wait("No tweezer bottom.");
    } },
  { id: "hikkake", name: "Hikkake", type: "Pattern", color: "#ffbe0b",
    desc: "Dan Chesler's Hikkake, a trap pattern. An inside bar forms, the next candle breaks below it (fooling sellers), then price closes back above the inside bar's high. Buys with a stop under the fake breakdown and a target twice the risk.",
    overlays() { return riskLines(this); },
    decide(I, i, pos) {
      if (pos) return checkExits(this, I, i) || wait(holdingMsg(this));
      if (i < 4) return warm(5, i);
      const inside = I.high[i - 2] < I.high[i - 3] && I.low[i - 2] > I.low[i - 3];
      const fake = I.low[i - 1] < I.low[i - 2] && I.high[i - 1] < I.high[i - 2];
      if (inside && fake && I.close[i] > I.high[i - 2]) return twoToOne(this, I, i, `Hikkake: an inside bar, a fake breakdown under it, then a close above its high (${fmtP(I.high[i - 2])}). The sellers are trapped.`, I.low[i - 1]);
      return wait(inside && fake ? `Fake breakdown under an inside bar. Needs a close above ${fmtP(I.high[i - 2])}.` : "No Hikkake setup.");
    } },
  { id: "risingthree", name: "Rising Three Methods", type: "Pattern", color: "#06d6a0",
    desc: "Candlestick continuation pattern. A long green candle, three small candles that stay inside its range (a pause), then a green candle closing above the long candle's high. Buys with a stop under the pause and a target twice the risk.",
    overlays() { return riskLines(this); },
    decide(I, i, pos) {
      if (pos) return checkExits(this, I, i) || wait(holdingMsg(this));
      const a = I.atr14[i];
      if (a == null || i < 5) return warm(15, i);
      const big = i - 4, body = I.close[big] - I.open[big];
      const small = [i - 3, i - 2, i - 1].every(j => Math.abs(I.close[j] - I.open[j]) < 0.5 * body && I.high[j] <= I.high[big] && I.low[j] >= I.low[big]);
      if (body > a && small && isGreen(I, i) && I.close[i] > I.high[big]) return twoToOne(this, I, i, "Rising three methods: a long green candle, a three-candle pause inside it, and a close above its high.", Math.min(...I.low.slice(i - 3, i)));
      return wait("No rising three methods.");
    } },

  // ----- levels -----
  { id: "roundnum", name: "Round Number Bounce", type: "Levels", color: "#d0f4de",
    desc: "Lots of traders place orders at round numbers ($50, $100, $65,000), so price often reacts there. Buys when price dips to the round number just below it and closes a little above it. Stop 1 ATR under the round number, target twice the risk.",
    overlays() { return riskLines(this); },
    decide(I, i, pos) {
      if (pos) return checkExits(this, I, i) || wait(holdingMsg(this));
      const a = I.atr14[i], c = I.close[i];
      if (a == null) return warm(15, i);
      const step = 5 * 10 ** (Math.floor(Math.log10(c)) - 1), level = Math.floor(c / step + 1e-9) * step;
      if (I.low[i] <= level + 0.1 * a && c > level && c - level <= 0.5 * a) return twoToOne(this, I, i, `Dipped to the round number ${fmtP(level)} and closed just above it.`, level - a);
      return wait(`The round number below is ${fmtP(level)}. Waiting for a dip to it that holds.`);
    } },

  // ----- volume -----
  { id: "chaikinosc", name: "Chaikin Oscillator", type: "Volume", color: "#52b69a",
    desc: "Marc Chaikin's oscillator tracks whether money is flowing in (closes near the highs on volume) faster than it was: the 3-candle EMA minus the 10-candle EMA of the accumulation/distribution line. Buys when it crosses above zero while price is above its 50-candle EMA, and sells when it drops below zero.",
    overlays: I => [["EMA 50", I.ema50, "#52b69a"]],
    decide(I, i, pos) {
      const o = CHOSC(I), e = I.ema50[i];
      if (o[i - 1] == null || e == null) return warm(50, i);
      if (!pos && o[i] > 0 && o[i - 1] <= 0 && I.close[i] > e) return buy("The Chaikin Oscillator crossed above zero with price above its 50-candle EMA. Money is flowing in: buying.");
      if (pos && o[i] < 0) return sell("The Chaikin Oscillator dropped below zero. Selling.");
      return wait(`Chaikin Oscillator ${o[i] > 0 ? "above" : "below"} zero. ${pos ? "Holding." : "Waiting for a cross above zero."}`);
    } },
  { id: "pocket", name: "Pocket Pivot", type: "Volume", color: "#76c893",
    desc: "From Gil Morales and Chris Kacher: an up candle whose volume beats the volume of every down candle in the last 10, while price is above its 10- and 50-candle averages. That hints big buyers are quietly stepping in. Sells a close under the 50-candle average.",
    overlays: I => [["SMA 10", SMA10(I), "#b5e48c"], ["SMA 50", I.sma50, "#34a0a4"]],
    decide(I, i, pos) {
      const c = I.close, s50 = I.sma50[i], s10 = SMA10(I)[i];
      if (s50 == null) return warm(50, i);
      if (pos && c[i] < s50) return sell(`Closed under the 50-candle average (${fmtP(s50)}). Selling.`);
      if (pos) return wait(`Holding while above the 50-candle average (${fmtP(s50)}).`);
      let downVol = 0;
      for (let j = i - 10; j < i; j++) if (c[j] < c[j - 1]) downVol = Math.max(downVol, I.vol[j]);
      if (c[i] > c[i - 1] && downVol > 0 && I.vol[i] > downVol && c[i] > s10 && c[i] > s50) return buy("Pocket pivot: an up candle on more volume than any down candle of the last 10, above both averages. Buying.");
      return wait("No pocket pivot.");
    } },
  { id: "nvi", name: "Quiet-Day Money (NVI)", type: "Volume", color: "#99d98c",
    desc: "The Negative Volume Index only changes on candles with less volume than the one before, on the theory that 'smart money' trades on quiet days. Owns it while that index is above its 200-candle average and sits in cash while it's below.",
    overlays: () => [],
    decide(I, i, pos) {
      const N = NVI(I), x = N.line[i], avg = N.avg[i];
      if (avg == null) return warm(200, i);
      if (!pos && x > avg) return buy("The quiet-day index is above its 200-candle average. Buying.");
      if (pos && x < avg) return sell("The quiet-day index fell under its 200-candle average. Selling.");
      return wait(`The quiet-day index is ${x > avg ? "above" : "below"} its average. ${pos ? "Holding." : "Waiting in cash."}`);
    } },
  { id: "sessionvwap", name: "Day VWAP Reclaim", type: "Volume", color: "#168aad",
    desc: "Day traders watch the VWAP that restarts every morning. When price has been under the day's VWAP for 3 candles and then closes back above it, buyers have taken control. Sells if it loses the VWAP again or at the day's last candle. Needs candles of 1 hour or shorter.",
    overlays: I => { const tf = tfMins(); return tf > 60 ? [] : [["Day VWAP", SVWAP(I, tf).vw, "#168aad"]]; },
    decide(I, i, pos) {
      const tf = tfMins();
      if (tf > 60) return wait("Needs candles of 1 hour or shorter.");
      const S = SVWAP(I, tf), v = S.vw[i], c = I.close[i];
      if (pos && S.last[i]) return sell("Last candle of the day. Selling before the close.");
      if (pos && v != null && c < v) return sell(`Lost the day's VWAP (${fmtP(v)}) again. Selling.`);
      if (pos) return wait(`Holding above the day's VWAP (${fmtP(v)}).`);
      if (v == null || i - S.first[i] < 3) return wait("The day just started. Waiting for a few candles.");
      const under = [i - 3, i - 2, i - 1].every(j => S.vw[j] != null && I.close[j] < S.vw[j]);
      if (under && c > v && !S.last[i]) return buy(`Closed back above the day's VWAP (${fmtP(v)}) after 3 candles under it. Buying.`);
      return wait(`${c > v ? "Above" : "Below"} the day's VWAP (${fmtP(v)}).`);
    } },

  // ----- sizing and risk -----
  { id: "holdstop", name: "Hold With a Stop", type: "Sizing", color: "#ef476f",
    desc: "Answers a beginner's question: does a stop-loss help a buy-and-hold investor? Buys on the first candle like Buy & Hold, but sells if price closes 20% under its highest close since buying. Buys back once price closes above its 50-candle average.",
    reset() { this.st = { started: false, peak: null }; },
    overlays() { return [["Trailing stop (20%)", this.lv.sl, "#ef5350"]]; },
    decide(I, i, pos) {
      const c = I.close[i], s = this.st, avg = I.sma50[i];
      if (pos) {
        s.peak = Math.max(s.peak, c);
        this.lv.sl[i] = s.peak * 0.8;
        if (c <= s.peak * 0.8) return sell(`Closed 20% under its highest close since buying (${fmtP(s.peak)}). The stop says sell.`);
        return wait(`Holding. Sells on a close under ${fmtP(s.peak * 0.8)}.`);
      }
      if (!s.started) return buy("Buying on the first candle, like Buy & Hold, but with a 20% trailing stop.");
      if (avg != null && c > avg) return buy(`Back above the 50-candle average (${fmtP(avg)}) after the stop. Buying back in.`);
      return wait(avg == null ? "Stopped out. Waiting for the 50-candle average to buy back." : `Stopped out. Buys back on a close above ${fmtP(avg)}.`);
    },
    filled(d, r) { if (d.act === "buy") { this.st.started = true; this.st.peak = r.fill; } } },
  { id: "kelly", name: "Half-Kelly Trend", type: "Sizing", color: "#ffd166",
    desc: "The Kelly formula says how much to bet from your win rate and your average win and loss. Trades Trend Rider's EMA 9/21 crosses, sizing each bet at half of Kelly from its own last 20 trades (between 10% and 100% of the cash; 25% until it has 5 trades).",
    reset() { this.st = { results: [], spend: null }; },
    overlays: I => [["EMA 9", I.ema9, "#ffe29a"], ["EMA 21", I.ema21, "#c9a227"]],
    decide(I, i, pos) {
      const a = I.ema9, b = I.ema21;
      if (b[i - 1] == null) return warm(22, i);
      const up = a[i] > b[i], wasUp = a[i - 1] > b[i - 1];
      if (!pos && up && !wasUp) { const k = kellyBet(this.st.results); return { act: "buy", frac: k.frac, why: `EMA 9 crossed above EMA 21. ${k.why}` }; }
      if (pos && !up && wasUp) return sell("EMA 9 crossed back below EMA 21. Trend over.");
      return wait(pos ? "Holding until EMA 9 crosses back below EMA 21." : `Waiting for a cross up. ${kellyBet(this.st.results).why}`);
    },
    filled(d, r) {
      const s = this.st;
      if (d.act === "buy") s.spend = r.spend;
      else if (s.spend) { s.results.push(r.pnl / s.spend); if (s.results.length > 20) s.results.shift(); }
    } },
  { id: "eqcurve", name: "Equity Curve Filter", type: "Sizing", color: "#118ab2",
    desc: "A trick some system traders use: keep a paper record of a strategy's trades and only take real ones while that record is doing well. Tracks Trend Rider's EMA 9/21 trades (with fees) and only takes a buy signal while that record's equity is at or above its average over the last 10 trades.",
    reset() { this.st = { entry: null, curve: [1] }; },
    overlays: I => [["EMA 9", I.ema9, "#73c2e6"], ["EMA 21", I.ema21, "#0b5d7a"]],
    decide(I, i, pos) {
      const a = I.ema9, b = I.ema21, s = this.st, c = I.close[i];
      if (b[i - 1] == null) return warm(22, i);
      const up = a[i] > b[i], wasUp = a[i - 1] > b[i - 1], crossUp = up && !wasUp, crossDown = !up && wasUp;
      if (crossDown && s.entry != null) {   // Trend Rider's trade on paper, whether or not this bot took it
        s.curve.push(s.curve[s.curve.length - 1] * (c / s.entry) * (1 - feeRate()) ** 2);
        s.entry = null;
      }
      if (crossUp) s.entry = c;
      const n = s.curve.length - 1, avg = n >= 10 ? s.curve.slice(-10).reduce((x, y) => x + y, 0) / 10 : null, healthy = avg != null && s.curve[n] >= avg;
      if (pos && crossDown) return sell("EMA 9 crossed back below EMA 21. Trend over.");
      if (!pos && crossUp && healthy) return buy("EMA 9 crossed above EMA 21, and Trend Rider's paper record is healthy (at or above its 10-trade average). Taking the trade.");
      if (!pos && crossUp) return wait(avg == null ? `Trend Rider signal, but its record needs 10 trades to judge (has ${n}). Skipping.` : "Trend Rider signal, but its recent trades are in a slump (under its 10-trade average). Skipping.");
      return wait(pos ? "Holding until EMA 9 crosses back below EMA 21." : `Trend Rider's paper record: ${n} trades${avg == null ? "" : `, ${healthy ? "at or above" : "under"} its 10-trade average`}. Waiting for a cross up.`);
    } },
  { id: "dipdca", name: "Dip-Weighted DCA", type: "Sizing", color: "#a7c957",
    desc: "A twist on Steady Buyer. It has a budget of 20 parts and a scheduled buy every 10 candles, but buys 2 parts when price is below its 50-candle average and only half a part when it's above. Never sells.",
    reset() { this.st = { left: 20, last: null, n: 0 }; },
    overlays: I => [["SMA 50", I.sma50, "#a7c957"]],
    decide(I, i) {
      const s = this.st, avg = I.sma50[i], c = I.close[i];
      if (s.left <= 1e-9) return wait("The whole budget is spent. Holding.");
      if (s.last != null && i - s.last < 10) return wait(`Next scheduled buy in ${10 - (i - s.last)} candles. ${s.left.toFixed(1)} of 20 parts left.`);
      if (avg == null) return warm(50, i);
      const use = Math.min(c < avg ? 2 : 0.5, s.left), frac = use / s.left;
      s.last = i; s.left -= use; s.n++;
      return { act: "buy", frac, why: `Scheduled buy ${s.n}. Price is ${c < avg ? "below" : "above"} its 50-candle average, so it buys ${use} part${use === 1 ? "" : "s"} (${s.left.toFixed(1)} of 20 left).` };
    } },

  // ----- time -----
  { id: "sellmay", name: "Sell in May", type: "Time", color: "#f4acb7",
    desc: "The old saying 'sell in May and go away': own it from November through April and sit in cash from May through October. Needs daily candles.",
    overlays: () => [],
    decide(I, i, pos) {
      if (tfMins() !== 1440) return wait("Needs daily candles.");
      const m = utcDate(I.time[i]).getUTCMonth(), season = m >= 10 || m <= 3;
      if (!pos && season) return buy(`${MONTHS[m]}: inside the November-to-April season. Buying.`);
      if (pos && !season) return sell(`${MONTHS[m]}: sell in May and go away. Back in November.`);
      return wait(season ? `${MONTHS[m]}: holding through the winter months.` : `${MONTHS[m]}: sitting in cash until November.`);
    } },
  { id: "santa", name: "Santa Claus Rally", type: "Time", color: "#e63946",
    desc: "Stocks have often risen in the last week of December and the first days of January. Owns it from December 23 through January 2 and sits in cash the rest of the year. Needs daily candles.",
    overlays: () => [],
    decide(I, i, pos) {
      if (tfMins() !== 1440) return wait("Needs daily candles.");
      const d = utcDate(I.time[i]), m = d.getUTCMonth(), day = d.getUTCDate(), inRally = (m === 11 && day >= 23) || (m === 0 && day <= 2);
      if (!pos && inRally) return buy("The Santa Claus rally window (late December into early January). Buying.");
      if (pos && !inRally) return sell("The Santa Claus rally window is over. Selling.");
      return wait(inRally ? "Holding through the holidays." : "Waiting for December 23.");
    } },
  { id: "powerhour", name: "Power Hour", type: "Time", color: "#ffafcc",
    desc: "The last hour of the US stock market (3 to 4 pm New York time) is often busy as big funds finish their trading. Buys at 3 pm New York time and sells at 4 pm, every weekday. Needs candles of 30 minutes or shorter.",
    overlays: () => [],
    decide(I, i, pos) {
      const tf = tfMins();
      if (tf > 30) return wait("Needs candles of 30 minutes or shorter.");
      const t = nyClock(I.time[i] + OFF + tf * 60), weekday = t.day !== "Sat" && t.day !== "Sun", when = `${t.day} ${hhmm(t.mins)} in New York.`;
      if (!pos && weekday && t.mins >= 900 && t.mins < 900 + tf) return buy(`${when} The last hour of trading starts: buying.`);
      if (pos && (t.mins >= 960 || t.mins < 900 || !weekday)) return sell(`${when} The closing bell: selling.`);
      return wait(`${when} ${pos ? "Holding through the last hour." : "Waiting for 3 pm."}`);
    } },

  // ----- statistics: rules that learn from the history so far -----
  { id: "knn", name: "Pattern Memory", type: "Stats", color: "#cdb4db",
    desc: "A simple machine-learning idea (nearest neighbors). It looks for the 15 moments in the history so far whose last 5 candles looked most like the last 5 now, and checks what happened next. Buys when at least 70% of them were followed by a higher close, and sells when 50% or fewer were.",
    overlays: () => [],
    decide(I, i, pos) {
      if (i < 120) return warm(120, i);
      const vote = knnVote(I, i);
      if (vote == null) return wait("Not enough history to compare with yet.");
      const share = `${Math.round(vote * 15)} of the 15 most similar past moments were followed by a higher close`;
      if (!pos && vote >= 0.7) return buy(`${share}. Buying.`);
      if (pos && vote <= 0.5) return sell(`${share}. Selling.`);
      return wait(`${share}. ${pos ? "Holding while it's over half." : "Needs at least 11."}`);
    } },
  { id: "markov", name: "Streak Odds", type: "Stats", color: "#b5838d",
    desc: "Counts, for every up/down pattern of the last 3 candles (like up-up-down), how often the next candle closed higher so far. Buys when the current pattern has been followed by a rise at least 60% of the time (seen at least 20 times), and sells when it's 50% or less.",
    overlays: () => [],
    decide(I, i, pos) {
      const M = MARKOV(I), p = M.prob[i], n = M.count[i], s = M.state[i];
      if (s == null) return warm(5, i);
      const pattern = [s & 1, s & 2, s & 4].map(bit => bit ? "up" : "down").join("-");
      if (n < 20 || p == null) return wait(`Pattern ${pattern} has only been seen ${n} times. Needs 20.`);
      const odds = `After ${pattern}, the next candle closed higher ${Math.round(p * 100)}% of ${n} times`;
      if (!pos && p >= 0.6) return buy(`${odds}. Buying.`);
      if (pos && p <= 0.5) return sell(`${odds}. Selling.`);
      return wait(`${odds}. ${pos ? "Holding." : "Needs 60%."}`);
    } },
);
})();

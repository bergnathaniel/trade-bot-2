// A fourth batch of Live Arena bots (added 2026-09-13): fast bots built for 5- and 15-minute candles, so they take many
// more trades. Appended to BOTS after extra_bots.js, which is frozen for the paper tests like the files before it.
// None of these are in the year-long paper tests. Every bot, old and new, runs in the weekly speed test (SPEED_TEST.md).
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
const tfMins = () => +$("tf").value;
const RET = I => get(I, "ret1", () => I.close.map((c, j) => j ? c / I.close[j - 1] - 1 : 0));
function zNow(r, i, n = 100) {   // how unusual the latest move is, in standard deviations of the n moves before it
  if (i < n + 1) return null;
  let s = 0, q = 0;
  for (let j = i - n; j < i; j++) { s += r[j]; q += r[j] * r[j]; }
  const m = s / n, sd = Math.sqrt(Math.max(q / n - m * m, 0));
  return sd > 0 ? (r[i] - m) / sd : null;
}
function autocorr(r, i, n = 100) {   // do moves tend to repeat (above 0) or reverse (below 0) over the last n candles?
  let mean = 0;
  for (let j = i - n + 1; j <= i; j++) mean += r[j];
  mean /= n;
  let num = 0, den = 0;
  for (let j = i - n + 1; j <= i; j++) {
    const d = r[j] - mean;
    den += d * d;
    if (j > i - n + 1) num += d * (r[j - 1] - mean);
  }
  return den > 0 ? num / den : 0;
}
const NY_DATE = new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York" });
const nyDate = t => NY_DATE.format(new Date((t + OFF) * 1000));
const LONDON = new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/London", weekday: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
function londonClock(epoch) {
  const p = Object.fromEntries(LONDON.formatToParts(new Date(epoch * 1000)).map(x => [x.type, x.value]));
  return { day: p.weekday, mins: +p.hour * 60 + +p.minute };
}
const utcParts = t => { const d = new Date((t + OFF) * 1000); return { date: d.toISOString().slice(0, 10), mins: d.getUTCHours() * 60 + d.getUTCMinutes() }; };
const hhmm = mins => `${String(Math.floor(mins / 60)).padStart(2, "0")}:${String(mins % 60).padStart(2, "0")}`;
// New York days: each candle's first candle of the day, the previous day's high, low and close, whether it's the day's
// last candle (stock days end at 4 pm New York time, crypto days at midnight), and the day's VWAP with its spread.
function nyDays(I, tf) {
  const n = I.close.length, first = Array(n).fill(0), last = Array(n).fill(false), stock = Array(n).fill(false);
  const prevHigh = Array(n).fill(null), prevLow = prevHigh.slice(), prevClose = prevHigh.slice(), vwap = prevHigh.slice(), spread = prevHigh.slice();
  let day = null, start = 0, isStock = false, days = 0, hi = 0, lo = 0, cl = 0, ph = null, pl = null, pc = null, pv = 0, pv2 = 0, v = 0;
  for (let i = 0; i < n; i++) {
    const d = nyDate(I.time[i]);
    if (d !== day) {
      if (days >= 2) { ph = hi; pl = lo; pc = cl; }   // the first day in the data is usually partial, so it's skipped
      day = d; days++; start = i; hi = -Infinity; lo = Infinity; pv = pv2 = v = 0;
      isStock = nyClock(I.time[i] + OFF).mins >= 540;
    }
    hi = Math.max(hi, I.high[i]); lo = Math.min(lo, I.low[i]); cl = I.close[i];
    const tp = (I.high[i] + I.low[i] + I.close[i]) / 3;
    pv += tp * I.vol[i]; pv2 += tp * tp * I.vol[i]; v += I.vol[i];
    first[i] = start; stock[i] = isStock; prevHigh[i] = ph; prevLow[i] = pl; prevClose[i] = pc;
    if (v > 0) { vwap[i] = pv / v; spread[i] = Math.sqrt(Math.max(pv2 / v - vwap[i] ** 2, 0)); }
    const end = I.time[i] + tf * 60;
    last[i] = isStock ? nyClock(end + OFF).mins >= 960 : nyDate(end) !== d;
  }
  return { first, last, stock, prevHigh, prevLow, prevClose, vwap, spread };
}
// UTC days, for crypto: the day's opening price (only when the data has the midnight candle), the Asian session's
// range (00:00 to 08:00 UTC, available from 08:00 on), the first candle of the day and whether it's the day's last candle.
function utcDays(I, tf) {
  const n = I.close.length, dayOpen = Array(n).fill(null), asiaHigh = dayOpen.slice(), asiaLow = dayOpen.slice(), mins = Array(n).fill(0), first = Array(n).fill(0), last = Array(n).fill(false);
  let day = null, start = 0, open = null, hi = -Infinity, lo = Infinity, count = 0;
  for (let i = 0; i < n; i++) {
    const u = utcParts(I.time[i]);
    if (u.date !== day) { day = u.date; start = i; open = u.mins === 0 ? I.open[i] : null; hi = -Infinity; lo = Infinity; count = 0; }
    mins[i] = u.mins; first[i] = start; dayOpen[i] = open;
    if (u.mins < 480) { hi = Math.max(hi, I.high[i]); lo = Math.min(lo, I.low[i]); count++; }
    else if (count > 0) { asiaHigh[i] = hi; asiaLow[i] = lo; }
    last[i] = utcParts(I.time[i] + tf * 60).date !== u.date;
  }
  return { dayOpen, asiaHigh, asiaLow, mins, first, last };
}
// For each candle: the average move of the next candle seen so far at the New York hour that candle starts in,
// how many times that hour has been seen, and how sure that average is (a t-statistic).
function hourOdds(I, tf) {
  const n = I.close.length, mean = Array(n).fill(null), count = Array(n).fill(0), tstat = Array(n).fill(null);
  const cnt = Array(24).fill(0), sum = Array(24).fill(0), sq = Array(24).fill(0);
  let prevKey = null;
  for (let i = 0; i < n; i++) {
    if (i > 0 && prevKey != null) { const r = I.close[i] / I.close[i - 1] - 1; cnt[prevKey]++; sum[prevKey] += r; sq[prevKey] += r * r; }
    const key = Math.floor(nyClock(I.time[i] + OFF + tf * 60).mins / 60);   // the hour the next candle starts in
    count[i] = cnt[key];
    if (cnt[key] >= 2) {
      const m = sum[key] / cnt[key], sd = Math.sqrt(Math.max(sq[key] / cnt[key] - m * m, 0));
      mean[i] = m; tstat[i] = sd > 0 ? m / sd * Math.sqrt(cnt[key]) : 0;
    }
    prevKey = key;
  }
  return { mean, count, tstat };
}
// A tiny machine-learning model (online logistic regression). One candle at a time, it learns whether the next candle
// closes higher from the last three moves, RSI and volume, and only ever uses candles that have already closed.
function learner(I) {
  const n = I.close.length, c = I.close, prob = Array(n).fill(null), seen = Array(n).fill(0), w = new Float64Array(6);
  const clip = x => Math.max(-3, Math.min(3, x)), sigmoid = z => 1 / (1 + Math.exp(-z));
  const features = j => {
    const a = I.atr14[j], avg = I.volAvg20[j], r = I.rsi14[j];
    if (j < 4 || a == null || !(a > 0) || avg == null || r == null) return null;
    return [1, clip((c[j] - c[j - 1]) / a), clip((c[j - 1] - c[j - 2]) / a), clip((c[j - 2] - c[j - 3]) / a), (r - 50) / 50, clip(avg > 0 ? I.vol[j] / avg - 1 : 0)];
  };
  let count = 0;
  for (let i = 1; i < n; i++) {
    const x = features(i - 1);   // learn from the candle that just closed: did it finish above the one before?
    if (x) {
      const y = c[i] > c[i - 1] ? 1 : 0, p = sigmoid(x.reduce((s, v, k) => s + v * w[k], 0));
      for (let k = 0; k < 6; k++) w[k] += 0.02 * ((y - p) * x[k] - 0.001 * w[k]);
      count++;
    }
    seen[i] = count;
    const now = features(i);
    if (now) prob[i] = sigmoid(now.reduce((s, v, k) => s + v * w[k], 0));
  }
  return { prob, seen };
}

const NYDAYS = (I, tf) => get(I, `nydays${tf}`, () => nyDays(I, tf));
const UTCDAYS = (I, tf) => get(I, `utcdays${tf}`, () => utcDays(I, tf));
const HOURODDS = (I, tf) => get(I, `hourodds${tf}`, () => hourOdds(I, tf));
const LEARNER = I => get(I, "learner", () => learner(I));
const RSI7 = I => get(I, "rsi7", () => rsi(I.close, 7));
const STOCH5 = I => get(I, "stoch5", () => stochastic(I.high, I.low, I.close, 5, 3));
const EMA = (I, n) => get(I, `ema${n}`, () => ema(I.close, n));
const FASTMACD = I => get(I, "fastmacd", () => {
  const f = EMA(I, 5), s = EMA(I, 13), m = I.close.map((_, j) => f[j] == null || s[j] == null ? null : f[j] - s[j]);
  return { m, sig: ema(m, 4) };
});
const FASTST = I => get(I, "fastst", () => supertrend(I.high, I.low, I.close, atr(I.high, I.low, I.close, 7), 2));
const FASTSAR = I => get(I, "fastsar", () => parabolicSar(I.high, I.low, 0.04, 0.4));
const FASTCHAN = I => get(I, "fastchan", () => ({ hi: channel(I.high, 10, Math.max), lo: channel(I.low, 5, Math.min) }));
const FASTKELT = I => get(I, "fastkelt", () => {
  const e = EMA(I, 10), a = atr(I.high, I.low, I.close, 10);
  return { mid: e, up: e.map((x, j) => x == null || a[j] == null ? null : x + 1.5 * a[j]) };
});

// ---------- helpers ----------
const pct = (x, dp = 1) => `${(x * 100).toFixed(dp)}%`;
const warm = (n, i) => wait(`Warming up. Needs ${n} candles (has ${i + 1}).`);
const needFast = tf => wait(`Needs candles of ${tf} minutes or shorter.`);
const feeFloor = c => c * (2 * feeRate() + 0.001);   // the smallest move that pays both fees with a little left over

// ---------- the bots ----------
BOTS.push(
  // ----- scalpers: in and out within a few candles -----
  { id: "fadespike", name: "Fade the Spike", type: "Scalp", color: "#ff8fab",
    desc: "When one candle drops more than 3 standard deviations further than the last 100 candles usually move, buys the panic. Aims to win back half the drop, with a stop 1 ATR lower and a 6-candle limit.",
    overlays() { return riskLines(this); },
    decide(I, i, pos) {
      if (pos) return checkExits(this, I, i) || wait(`${holdingMsg(this)} ${6 - (i - this.st.entryIdx)} candles left.`);
      const z = zNow(RET(I), i), a = I.atr14[i], c = I.close[i];
      if (z == null || a == null) return warm(102, i);
      if (z < -3) return enter(this, i, `A ${(-z).toFixed(1)}-sigma drop in one candle. Betting half of it comes back.`, { target: c + (I.close[i - 1] - c) / 2, stop: c - a, maxBars: 6 });
      return wait(`Last move: ${z.toFixed(1)} sigma. Needs a drop past −3.`);
    } },
  { id: "chasespike", name: "Chase the Spike", type: "Scalp", color: "#fb6f92",
    desc: "The opposite bet: when one candle jumps more than 3 standard deviations on at least 3 times the normal volume, rides it for up to 3 candles, with a stop under that candle's low.",
    overlays() { return riskLines(this); },
    decide(I, i, pos) {
      if (pos) return checkExits(this, I, i) || wait(`${holdingMsg(this)} ${3 - (i - this.st.entryIdx)} candles left.`);
      const z = zNow(RET(I), i), avg = I.volAvg20[i - 1];
      if (z == null || avg == null) return warm(102, i);
      const ratio = avg > 0 ? I.vol[i] / avg : 0;
      if (z > 3 && ratio >= 3) return enter(this, i, `A ${z.toFixed(1)}-sigma jump on ${ratio.toFixed(1)}x volume. Riding it for up to 3 candles.`, { stop: I.low[i], maxBars: 3 });
      return wait(`Last move ${z.toFixed(1)} sigma on ${ratio.toFixed(1)}x volume. Needs 3+ sigma on 3x volume.`);
    } },
  { id: "wickscalp", name: "Wick Scalper", type: "Scalp", color: "#ffc2d1",
    desc: "Buys a candle with a long lower wick (at least 60% of a candle bigger than 1 ATR) that closes near its top on 1.5 times the normal volume: sellers got pushed back hard. Target as far above as the stop is below, 5-candle limit.",
    overlays() { return riskLines(this); },
    decide(I, i, pos) {
      if (pos) return checkExits(this, I, i) || wait(`${holdingMsg(this)} ${5 - (i - this.st.entryIdx)} candles left.`);
      const a = I.atr14[i], avg = I.volAvg20[i - 1];
      if (a == null || avg == null) return warm(21, i);
      const o = I.open[i], c = I.close[i], h = I.high[i], l = I.low[i], range = h - l, lower = Math.min(o, c) - l;
      if (range >= a && lower >= 0.6 * range && c >= l + 0.6 * range && avg > 0 && I.vol[i] >= 1.5 * avg) {
        const stop = l - 0.1 * a;
        return enter(this, i, `Long lower wick on ${(I.vol[i] / avg).toFixed(1)}x volume. Stop ${fmtP(stop)}, target ${fmtP(c + (c - stop))}.`, { stop, target: c + (c - stop), maxBars: 5 });
      }
      return wait("No long lower wick on strong volume.");
    } },
  { id: "quickengulf", name: "Quick Engulf", type: "Scalp", color: "#ff99c8",
    desc: "A one-candle trade: after a red candle, a green candle whose body swallows it (and is at least half an ATR tall). Buys at that close and sells at the next close.",
    overlays() { return riskLines(this); },
    decide(I, i, pos) {
      if (pos) return checkExits(this, I, i) || wait("Holding for one candle.");
      const a = I.atr14[i];
      if (a == null) return warm(15, i);
      const engulf = isRed(I, i - 1) && isGreen(I, i) && I.open[i] <= I.close[i - 1] && I.close[i] >= I.open[i - 1] && I.close[i] - I.open[i] >= 0.5 * a;
      if (engulf) return enter(this, i, "A green candle swallowed the red one before it. Holding for one candle.", { maxBars: 1 });
      return wait("No engulfing candle.");
    } },
  { id: "tightscalp", name: "Tight Scalper", type: "Scalp", color: "#e0aaff",
    desc: "In an uptrend (EMA 8 above EMA 21), buys a dip to EMA 8 that closes back above it, aiming for half an ATR with a stop half an ATR down. Skips the trade when half an ATR is too small to cover both fees, which on short candles is most of the time.",
    overlays(I) { return [["EMA 8", EMA(I, 8), "#e0aaff"], ["EMA 21", I.ema21, "#7b2cbf"], ...riskLines(this)]; },
    decide(I, i, pos) {
      if (pos) return checkExits(this, I, i) || wait(holdingMsg(this));
      const e8 = EMA(I, 8)[i], e21 = I.ema21[i], a = I.atr14[i], c = I.close[i];
      if (e8 == null || e21 == null || a == null) return warm(22, i);
      if (!(e8 > e21)) return wait("No uptrend (EMA 8 under EMA 21).");
      if (!(I.low[i] <= e8 && c > e8)) return wait(`Uptrend. Waiting for a dip to EMA 8 (${fmtP(e8)}).`);
      if (0.5 * a < feeFloor(c)) return wait(`Dip to EMA 8, but half an ATR (${fmtP(0.5 * a)}) wouldn't cover the fees (${fmtP(feeFloor(c))}). Skipping.`);
      return enter(this, i, `Dipped to EMA 8 and closed above it. Aiming for ${fmtP(c + 0.5 * a)}.`, { target: c + 0.5 * a, stop: c - 0.5 * a });
    } },
  { id: "burst", name: "Momentum Burst", type: "Scalp", color: "#c77dff",
    desc: "Buys after three green candles in a row with volume rising each time, and sells on the first red candle.",
    overlays: () => [],
    decide(I, i, pos) {
      if (i < 3) return warm(4, i);
      if (pos && isRed(I, i)) return sell("A red candle. The burst is over: selling.");
      if (pos) return wait("Holding until a red candle.");
      const run = [i - 2, i - 1, i].every(j => isGreen(I, j)) && I.vol[i] > I.vol[i - 1] && I.vol[i - 1] > I.vol[i - 2];
      if (run) return buy("Three green candles with volume climbing each time. Buying the burst.");
      return wait("Waiting for three green candles on rising volume.");
    } },
  { id: "rsi7", name: "RSI-7 Scalper", type: "Scalp", color: "#9d4edd",
    desc: "A fast RSI (7 candles). Buys when it's under 20 and sells when it's back over 60, or after 12 candles.",
    overlays: () => [],
    decide(I, i, pos) {
      const r = RSI7(I)[i];
      if (r == null) return warm(8, i);
      if (pos && r > 60) return sell(`RSI-7 is back up to ${r.toFixed(0)}. Selling.`);
      if (pos) return checkExits(this, I, i) || wait(`Holding until RSI-7 is over 60 (now ${r.toFixed(0)}). ${12 - (i - this.st.entryIdx)} candles left.`);
      if (r < 20) return enter(this, i, `RSI-7 is ${r.toFixed(0)}, under 20. Buying the dip.`, { maxBars: 12 });
      return wait(`RSI-7 ${r.toFixed(0)}. Waiting for it to go under 20.`);
    } },
  { id: "faststoch", name: "Fast Stochastic", type: "Scalp", color: "#7209b7",
    desc: "A fast Stochastic (5 candles, smoothed over 3). Buys when it turns up from under 20 and sells once it's above 80.",
    overlays: () => [],
    decide(I, i, pos) {
      const S = STOCH5(I), k = S.k, d = S.d;
      if (d[i - 1] == null) return warm(9, i);
      if (!pos && k[i] > d[i] && k[i - 1] <= d[i - 1] && k[i] < 20) return buy(`Fast Stochastic turned up at ${k[i].toFixed(0)}. Buying.`);
      if (pos && k[i] > 80) return sell(`Fast Stochastic hit ${k[i].toFixed(0)}. Selling.`);
      return wait(`Fast Stochastic ${k[i].toFixed(0)}. ${pos ? "Holding until it's above 80." : "Waiting for a turn up under 20."}`);
    } },
  { id: "bandscalp", name: "Band Scalper", type: "Scalp", color: "#b8c0ff",
    desc: "A quick version of Band Bouncer. Buys a close under the lower Bollinger Band and sells at the middle band, with a stop 1 ATR lower and a 10-candle limit.",
    overlays(I) { return [["Middle band", I.bb.mid, "#b8c0ff"], ["Lower band", I.bb.lo, "#6b78c9"], ...riskLines(this)]; },
    decide(I, i, pos) {
      const c = I.close[i], mid = I.bb.mid[i], lo = I.bb.lo[i], a = I.atr14[i];
      if (pos && c >= mid) return sell(`Back to the middle band (${fmtP(mid)}). Selling.`);
      if (pos) return checkExits(this, I, i) || wait(`${holdingMsg(this)} Sells at the middle band (${fmtP(mid)}).`);
      if (lo == null || a == null) return warm(20, i);
      if (c < lo) return enter(this, i, `Closed under the lower band (${fmtP(lo)}). Aiming for the middle band.`, { stop: c - a, maxBars: 10 });
      return wait(`Waiting for a close under ${fmtP(lo)}.`);
    } },
  { id: "vwapband", name: "VWAP Band Reversion", type: "Scalp", color: "#4ea8de",
    desc: "Day traders' bands around the VWAP that restarts each New York day. Buys when price closes more than 2 volume-weighted standard deviations under it, and sells back at the VWAP, at a stop 1 ATR lower, or at the day's last candle. Needs candles of 1 hour or shorter.",
    overlays(I) { const tf = tfMins(); return tf > 60 ? riskLines(this) : [["Day VWAP", NYDAYS(I, tf).vwap, "#4ea8de"], ...riskLines(this)]; },
    decide(I, i, pos) {
      const tf = tfMins();
      if (tf > 60) return needFast(60);
      const D = NYDAYS(I, tf), v = D.vwap[i], sd = D.spread[i], c = I.close[i], a = I.atr14[i];
      if (pos && D.last[i]) return sell("Last candle of the day. Selling.");
      if (pos && v != null && c >= v) return sell(`Back to the day's VWAP (${fmtP(v)}). Selling.`);
      if (pos) return checkExits(this, I, i) || wait(holdingMsg(this));
      if (v == null || a == null || i - D.first[i] < 6) return wait("Waiting for 6 candles of the day.");
      const floor = v - 2 * sd;
      if (c < floor && !D.last[i]) return enter(this, i, `Closed under the day's VWAP band (${fmtP(floor)}). Aiming for the VWAP at ${fmtP(v)}.`, { stop: c - a });
      return wait(`Day VWAP ${fmtP(v)}, lower band ${fmtP(floor)}.`);
    } },

  // ----- fast trend followers -----
  { id: "fastcross", name: "Fast Cross 3/8", type: "Trend", color: "#48cae4",
    desc: "A very fast moving-average cross: buys when EMA 3 crosses above EMA 8 and sells when it crosses back below. Trades constantly.",
    overlays: I => [["EMA 3", EMA(I, 3), "#90e0ef"], ["EMA 8", EMA(I, 8), "#0077b6"]],
    decide(I, i, pos) {
      const a = EMA(I, 3), b = EMA(I, 8);
      if (b[i - 1] == null) return warm(9, i);
      const up = a[i] > b[i], wasUp = a[i - 1] > b[i - 1];
      if (!pos && up && !wasUp) return buy("EMA 3 crossed above EMA 8. Buying.");
      if (pos && !up) return sell("EMA 3 dropped under EMA 8. Selling.");
      return wait(`EMA 3 ${up ? "above" : "below"} EMA 8. ${pos ? "Holding." : "Waiting for a fresh cross up."}`);
    } },
  { id: "fastmacd", name: "Fast MACD", type: "Trend", color: "#00b4d8",
    desc: "MACD with fast settings (EMA 5 minus EMA 13, with a 4-candle signal line). Buys when it crosses above its signal and sells when it crosses below.",
    overlays: () => [],
    decide(I, i, pos) {
      const M = FASTMACD(I), m = M.m, s = M.sig;
      if (s[i - 1] == null) return warm(17, i);
      const up = m[i] > s[i], wasUp = m[i - 1] > s[i - 1];
      if (!pos && up && !wasUp) return buy("Fast MACD crossed above its signal. Buying.");
      if (pos && !up) return sell("Fast MACD dropped under its signal. Selling.");
      return wait(`Fast MACD ${up ? "above" : "below"} its signal. ${pos ? "Holding." : "No fresh cross up."}`);
    } },
  { id: "fastst", name: "Fast Supertrend", type: "Trend", color: "#0096c7",
    desc: "Supertrend with a tighter line: 2 ATRs (over 7 candles) from price instead of 3. Owns it while price is above the line and sells when it closes below.",
    overlays: I => [["Fast Supertrend", FASTST(I).line, "#0096c7"]],
    decide(I, i, pos) {
      const S = FASTST(I), d = S.dir[i], line = S.line[i];
      if (d == null) return warm(8, i);
      if (!pos && d === 1) return buy(`Price is above the fast Supertrend line (${fmtP(line)}). Buying.`);
      if (pos && d === -1) return sell("Closed under the fast Supertrend line. Selling.");
      return wait(d === 1 ? `Holding above ${fmtP(line)}.` : `Trend down. Needs a close above ${fmtP(line)}.`);
    } },
  { id: "fastsar", name: "Fast SAR", type: "Trend", color: "#023e8a",
    desc: "Parabolic SAR that speeds up twice as fast (step 0.04, max 0.4), so it flips and trades far more often. Owns it while the SAR is under price.",
    overlays: I => [["Fast SAR", FASTSAR(I).sar, "#5390d9"]],
    decide(I, i, pos) {
      const S = FASTSAR(I), up = S.up[i];
      if (up == null) return warm(3, i);
      if (!pos && up) return buy(`Fast SAR (${fmtP(S.sar[i])}) is under price. Buying.`);
      if (pos && !up) return sell("Price hit the fast SAR and it flipped above. Selling.");
      return wait(up ? `Holding. SAR at ${fmtP(S.sar[i])}.` : `SAR is above price at ${fmtP(S.sar[i])}.`);
    } },
  { id: "fastchan", name: "Fast Channel Breakout", type: "Breakout", color: "#f8961e",
    desc: "A quick Breakout Hunter: buys a close above the highest high of the last 10 candles and sells a close below the lowest low of the last 5.",
    overlays: I => { const C = FASTCHAN(I); return [["10-candle high", C.hi, "#f8961e"], ["5-candle low", C.lo, "#9c5c12"]]; },
    decide(I, i, pos) {
      const C = FASTCHAN(I), c = I.close[i], hi = C.hi[i], lo = C.lo[i];
      if (hi == null) return warm(11, i);
      if (!pos && c > hi) return buy(`Closed above the 10-candle high (${fmtP(hi)}). Buying.`);
      if (pos && c < lo) return sell(`Closed under the 5-candle low (${fmtP(lo)}). Selling.`);
      return wait(pos ? `Holding. Exits under ${fmtP(lo)}.` : `Needs a close above ${fmtP(hi)}.`);
    } },
  { id: "fastkelt", name: "Fast Keltner", type: "Breakout", color: "#f3722c",
    desc: "A quick Keltner Breakout: buys a close above EMA 10 plus 1.5 ATRs and sells a close back under EMA 10.",
    overlays: I => { const K = FASTKELT(I); return [["Upper channel", K.up, "#f3722c"], ["EMA 10", K.mid, "#a3471b"]]; },
    decide(I, i, pos) {
      const K = FASTKELT(I), c = I.close[i], up = K.up[i], mid = K.mid[i];
      if (up == null) return warm(11, i);
      if (!pos && c > up) return buy(`Closed above the fast Keltner channel (${fmtP(up)}). Buying.`);
      if (pos && c < mid) return sell(`Closed back under EMA 10 (${fmtP(mid)}). Selling.`);
      return wait(pos ? `Holding while above ${fmtP(mid)}.` : `Needs a close above ${fmtP(up)}.`);
    } },
  { id: "upmajority", name: "Up Majority", type: "Trend", color: "#90be6d",
    desc: "Counts how many of the last 10 candles closed higher than the one before. Buys at 7 or more and sells at 4 or fewer.",
    overlays: () => [],
    decide(I, i, pos) {
      if (i < 10) return warm(11, i);
      let ups = 0;
      for (let j = i - 9; j <= i; j++) if (I.close[j] > I.close[j - 1]) ups++;
      if (!pos && ups >= 7) return buy(`${ups} of the last 10 candles closed higher. Buying.`);
      if (pos && ups <= 4) return sell(`Only ${ups} of the last 10 closed higher. Selling.`);
      return wait(`${ups} of the last 10 candles closed higher. ${pos ? "Holding until 4 or fewer." : "Buys at 7 or more."}`);
    } },
  { id: "closeloc", name: "Close Location Momentum", type: "Trend", color: "#43aa8b",
    desc: "Buys after three green candles in a row that each closed in the top 10% of their range (buyers in control right to the close). Sells when a candle closes in the bottom half of its range.",
    overlays: () => [],
    decide(I, i, pos) {
      if (i < 3) return warm(4, i);
      const loc = j => { const r = I.high[j] - I.low[j]; return r > 0 ? (I.close[j] - I.low[j]) / r : 0.5; };
      if (pos && loc(i) < 0.5) return sell("Closed in the bottom half of its range. Selling.");
      if (pos) return wait("Holding until a close in the bottom half of a candle.");
      if ([i - 2, i - 1, i].every(j => isGreen(I, j) && loc(j) >= 0.9)) return buy("Three green candles in a row, each closing at the very top of its range. Buying.");
      return wait("Waiting for three strong closes in a row.");
    } },

  // ----- fast breakouts and bounces -----
  { id: "dayrange", name: "Day Range Breakout", type: "Breakout", color: "#f9c74f",
    desc: "Larry Williams' range breakout inside the day: buys when price climbs above the day's opening price plus half of yesterday's range, with a stop at the day's open, and sells at the day's last candle. One trade a day. Needs candles of 1 hour or shorter.",
    overlays() { return riskLines(this); },
    decide(I, i, pos) {
      const tf = tfMins();
      if (tf > 60) return needFast(60);
      const D = NYDAYS(I, tf), f = D.first[i];
      if (pos && D.last[i]) return sell("Last candle of the day. Selling.");
      if (pos) return checkExits(this, I, i) || wait(`${holdingMsg(this)} Sells at the day's last candle.`);
      if (D.prevHigh[i] == null) return wait("Waiting for a full previous day.");
      const trigger = I.open[f] + 0.5 * (D.prevHigh[i] - D.prevLow[i]);
      if (this.st.day === f) return wait("Already traded today.");
      if (I.close[i] > trigger && !D.last[i]) {
        const d = enter(this, i, `Climbed above the day's open plus half of yesterday's range (${fmtP(trigger)}). Stop at the open, ${fmtP(I.open[f])}.`, { stop: I.open[f] });
        this.st.day = f;
        return d;
      }
      return wait(`Buys above ${fmtP(trigger)} today.`);
    } },
  { id: "hourhigh", name: "Hour High Break", type: "Breakout", color: "#ffba08",
    desc: "Buys a close above the highest high of the last hour of candles (at least 3) on 1.5 times the normal volume. Stop at that hour's low, and sells after another hour's worth of candles.",
    overlays() { return riskLines(this); },
    decide(I, i, pos) {
      const k = Math.max(3, Math.round(60 / tfMins()));
      if (pos) return checkExits(this, I, i) || wait(`${holdingMsg(this)} ${k - (i - this.st.entryIdx)} candles left.`);
      const avg = I.volAvg20[i - 1];
      if (i < k + 1 || avg == null) return warm(Math.max(k + 1, 21), i);
      const hi = Math.max(...I.high.slice(i - k, i)), lo = Math.min(...I.low.slice(i - k, i)), ratio = avg > 0 ? I.vol[i] / avg : 0;
      if (I.close[i] > hi && ratio >= 1.5) return enter(this, i, `Closed above the last ${k} candles' high (${fmtP(hi)}) on ${ratio.toFixed(1)}x volume.`, { stop: lo, maxBars: k });
      return wait(`Needs a close above ${fmtP(hi)} on 1.5x volume.`);
    } },
  { id: "squeezescalp", name: "Squeeze Scalp", type: "Breakout", color: "#e85d04",
    desc: "When the Bollinger Bands were at their narrowest of the last 50 candles within the last 3 candles and price then closes above the upper band, buys the breakout. A stop trails 1 ATR under the highest close, and it sells after 12 candles.",
    overlays() { return riskLines(this); },
    decide(I, i, pos) {
      const a = I.atr14[i], c = I.close[i];
      if (pos) {
        const s = this.st;
        s.peak = Math.max(s.peak ?? c, c);
        s.stop = Math.max(s.stop, s.peak - a);
        this.lv.sl[i] = s.stop;
        return checkExits(this, I, i) || wait(`Holding. Stop trails at ${fmtP(s.stop)}. ${12 - (i - s.entryIdx)} candles left.`);
      }
      if (I.bb.mid[i - 53] == null || a == null) return warm(73, i);
      const width = j => (I.bb.up[j] - I.bb.lo[j]) / I.bb.mid[j];
      let pinched = false;
      for (let j = i - 3; j < i && !pinched; j++) {
        let narrowest = true;
        for (let k = j - 49; k < j && narrowest; k++) if (width(k) < width(j)) narrowest = false;
        pinched = narrowest;
      }
      if (pinched && c > I.bb.up[i]) return enter(this, i, `The bands just pinched to their narrowest in 50 candles, and price broke above the upper band (${fmtP(I.bb.up[i])}).`, { stop: c - a, maxBars: 12 });
      return wait(pinched ? `Squeeze. Needs a close above ${fmtP(I.bb.up[i])}.` : "No squeeze.");
    } },
  { id: "atrstretch", name: "ATR Stretch", type: "Bounce", color: "#2a9d8f",
    desc: "Buys when price is stretched more than 2.5 ATRs under its 20-candle EMA, and sells when it's back at the EMA, at a stop 1 ATR lower, or after 20 candles.",
    overlays(I) { return [["EMA 20", I.ema20, "#2a9d8f"], ...riskLines(this)]; },
    decide(I, i, pos) {
      const c = I.close[i], e = I.ema20[i], a = I.atr14[i];
      if (pos && c >= e) return sell(`Back at the EMA 20 (${fmtP(e)}). Selling.`);
      if (pos) return checkExits(this, I, i) || wait(`${holdingMsg(this)} Sells at the EMA 20 (${fmtP(e)}).`);
      if (e == null || a == null) return warm(20, i);
      const stretch = (c - e) / a;
      if (stretch < -2.5) return enter(this, i, `Stretched ${(-stretch).toFixed(1)} ATRs under the EMA 20. Betting on a snap back.`, { stop: c - a, maxBars: 20 });
      return wait(`${stretch.toFixed(1)} ATRs from the EMA 20. Buys past −2.5.`);
    } },
  { id: "rangescalp", name: "Range Scalper", type: "Bounce", color: "#52b788",
    desc: "Only trades when there's no trend (ADX under 20). Buys near the bottom of the last 50 candles' range (the lowest 15%) and sells at the middle, with a stop half an ATR under the range.",
    overlays() { return riskLines(this); },
    decide(I, i, pos) {
      if (pos) return checkExits(this, I, i) || wait(holdingMsg(this));
      const adx = I.dmi.adx[i], a = I.atr14[i], c = I.close[i];
      if (adx == null || a == null || i < 51) return warm(52, i);
      if (adx >= 20) return wait(`ADX ${adx.toFixed(0)}: trending. Range trading is off.`);
      const hi = Math.max(...I.high.slice(i - 50, i)), lo = Math.min(...I.low.slice(i - 50, i)), range = hi - lo;
      if (range > 0 && c > lo && c <= lo + 0.15 * range) return enter(this, i, `No trend (ADX ${adx.toFixed(0)}), and price is near the bottom of its range (${fmtP(lo)} to ${fmtP(hi)}). Aiming for the middle.`, { target: lo + 0.5 * range, stop: lo - 0.5 * a });
      return wait(`No trend. Buys under ${fmtP(lo + 0.15 * range)}.`);
    } },
  { id: "tightgrid", name: "Tight Grid", type: "Grid", color: "#cdb4db",
    desc: "A finer Grid Trader: 10 slices instead of 5, with a step of 0.75 ATR that's never narrower than the fees. Buys a slice each step down and sells each slice one step above its own buy price.",
    reset() { this.st.lots = []; this.lv.nb = []; this.lv.ns = []; },
    overlays() { return [["Next buy", this.lv.nb, "#26a69a"], ["Next sell", this.lv.ns, "#ef5350"]]; },
    decide(I, i) {
      const a = I.atr14[i], c = I.close[i], s = this.st, lots = s.lots;
      if (a == null) return warm(15, i);
      const step = Math.max(0.75 * a, feeFloor(c));
      if (!lots.length && s.ref != null && c > s.ref + 2 * step) s.ref = null;   // price ran away: start a new grid
      const nextBuy = lots.length ? Math.min(...lots.map(l => l.entry)) - step : s.ref != null ? s.ref - step : c;
      const nextSell = lots.length ? Math.min(...lots.map(l => l.target)) : null;
      if (lots.length < 10) this.lv.nb[i] = nextBuy;
      if (nextSell != null) this.lv.ns[i] = nextSell;
      const ready = lots.filter(l => c >= l.target).sort((x, y) => x.entry - y.entry)[0];
      if (ready) return { act: "sell", lot: ready, costBasis: ready.cost, frac: lots.length === 1 ? 1 : ready.qty / acct[this.id].qty,
        why: `The slice bought at ${fmtP(ready.entry)} reached its sell level (${fmtP(ready.target)}).` };
      if (lots.length < 10 && c <= nextBuy) return { act: "buy", step, frac: 1 / (10 - lots.length),
        why: lots.length ? `Down a full step to ${fmtP(c)}. Buying slice ${lots.length + 1} of 10.` : `Starting a grid at ${fmtP(c)}. Buying slice 1 of 10.` };
      return wait(`${lots.length} of 10 slices held.${lots.length < 10 ? ` Next buy at ${fmtP(nextBuy)}.` : ""}${nextSell != null ? ` Next sell at ${fmtP(nextSell)}.` : ""}`);
    },
    filled(d, r) {
      const s = this.st;
      if (d.act === "buy") s.lots.push({ entry: r.fill, qty: r.qty, cost: r.spend, target: r.fill + d.step });
      else { s.lots = s.lots.filter(l => l !== d.lot); if (!s.lots.length) s.ref = r.fill; }
    } },

  // ----- time of day -----
  { id: "asiarange", name: "Asia Range Breakout", type: "Time", color: "#ffd166",
    desc: "Crypto trades around the clock. Marks the high and low of the Asian session (midnight to 8 am UTC), then buys the first close above that high between 8 am and 4 pm UTC, with a stop at the middle of the range. Sells at 8 pm UTC. One trade a day. Crypto only; needs candles of 1 hour or shorter.",
    overlays() { return riskLines(this); },
    decide(I, i, pos) {
      const tf = tfMins();
      if (tf > 60) return needFast(60);
      const U = UTCDAYS(I, tf), m = U.mins[i] + tf;   // minutes past midnight UTC at the candle's close
      if (pos && (m >= 1200 || U.last[i])) return sell("8 pm UTC. Selling.");
      if (pos) return checkExits(this, I, i) || wait(`${holdingMsg(this)} Sells at 8 pm UTC.`);
      const hi = U.asiaHigh[i], lo = U.asiaLow[i];
      if (hi == null) return wait("No Asian session range yet today (crypto only).");
      if (this.st.day === U.first[i]) return wait("Already traded today's range.");
      if (m <= 960 && I.close[i] > hi) {
        const d = enter(this, i, `Closed above the Asian session high (${fmtP(hi)}). Stop at the middle of the range, ${fmtP((hi + lo) / 2)}.`, { stop: (hi + lo) / 2 });
        this.st.day = U.first[i];
        return d;
      }
      return wait(m > 960 ? "Too late in the day for a new trade." : `Asian range ${fmtP(lo)} to ${fmtP(hi)}. Waiting for a close above it.`);
    } },
  { id: "londondrive", name: "London Open Drive", type: "Time", color: "#ef476f",
    desc: "At 8 am London time on weekdays, buys if price is above where the UTC day opened, betting European traders push the move further. Sells at noon London time. Crypto only; needs candles of 1 hour or shorter.",
    overlays: () => [],
    decide(I, i, pos) {
      const tf = tfMins();
      if (tf > 60) return needFast(60);
      const t = londonClock(I.time[i] + OFF + tf * 60), weekday = t.day !== "Sat" && t.day !== "Sun", open = UTCDAYS(I, tf).dayOpen[i];
      if (pos && (t.mins >= 720 || t.mins < 480)) return sell(`${hhmm(t.mins)} in London. Selling.`);
      if (pos) return wait(`${hhmm(t.mins)} in London. Holding until noon.`);
      if (open == null) return wait("Needs the UTC day's opening price (crypto only).");
      if (weekday && t.mins >= 480 && t.mins < 480 + tf && I.close[i] > open) return buy(`8 am in London, and price (${fmtP(I.close[i])}) is above the day's open (${fmtP(open)}). Buying.`);
      return wait(`${t.day} ${hhmm(t.mins)} in London. Waiting for 8 am on a weekday.`);
    } },
  { id: "nyreversal", name: "NY Open Reversal", type: "Time", color: "#06d6a0",
    desc: "If price falls more than 1 ATR in the first half hour after the New York stock market opens (9:30 to 10 am), buys at 10 am, betting the early selling was overdone. Sells at noon New York time. Weekdays; needs candles of 30 minutes or shorter.",
    overlays: () => [],
    decide(I, i, pos) {
      const tf = tfMins();
      if (tf > 30) return needFast(30);
      const t = nyClock(I.time[i] + OFF + tf * 60), a = I.atr14[i];
      if (pos && (t.mins >= 720 || t.mins < 600)) return sell(`${hhmm(t.mins)} in New York. Selling.`);
      if (pos) return wait("Holding until noon in New York.");
      if (a == null) return warm(15, i);
      if (t.mins !== 600 || t.day === "Sat" || t.day === "Sun") return wait(`${t.day} ${hhmm(t.mins)} in New York. Waiting for 10 am on a weekday.`);
      let j = -1;
      for (let k = i; k >= Math.max(0, i - 7) && j < 0; k--) if (nyClock(I.time[k] + OFF).mins === 570) j = k;
      if (j < 0) return wait("No 9:30 candle today.");
      const drop = I.open[j] - I.close[i];
      if (drop > a) return buy(`Fell ${fmtP(drop)} since the 9:30 open, more than 1 ATR. Buying the early selloff.`);
      return wait(`10 am in New York. Moved ${fmtP(-drop)} since 9:30; needs a drop of more than ${fmtP(a)}.`);
    } },
  { id: "midnight", name: "Midnight Reclaim", type: "Time", color: "#118ab2",
    desc: "Crypto's daily candle starts at midnight UTC, and many traders watch that opening price. After price spends 3 candles under the day's open, buys a close back above it. Sells if it falls back under, or at the day's last candle. Crypto only; needs candles of 1 hour or shorter.",
    overlays: () => [],
    decide(I, i, pos) {
      const tf = tfMins();
      if (tf > 60) return needFast(60);
      const U = UTCDAYS(I, tf), open = U.dayOpen[i], c = I.close[i];
      if (pos && U.last[i]) return sell("Last candle of the UTC day. Selling.");
      if (pos && open != null && c < open) return sell(`Back under the day's open (${fmtP(open)}). Selling.`);
      if (pos) return wait(`Holding above the day's open (${fmtP(open)}).`);
      if (open == null) return wait("Needs the UTC day's opening price (crypto only).");
      if (i - U.first[i] < 3) return wait("The UTC day just started.");
      const under = [i - 3, i - 2, i - 1].every(j => I.close[j] < open);
      if (under && c > open && !U.last[i]) return buy(`Reclaimed the day's open (${fmtP(open)}) after 3 candles under it. Buying.`);
      return wait(`The day opened at ${fmtP(open)}. ${c > open ? "Price is above it." : "Price is under it."}`);
    } },
  { id: "gapfill", name: "Morning Gap Fill", type: "Time", color: "#073b4c",
    desc: "For stocks: when the first 5 or 15 minutes open at least 0.3% under yesterday's close and are still below it, buys, aiming to fill the gap back to yesterday's close. Stop half an ATR under that first candle's low; sells at 11 am New York time. Needs candles of 30 minutes or shorter.",
    overlays() { return riskLines(this); },
    decide(I, i, pos) {
      const tf = tfMins();
      if (tf > 30) return needFast(30);
      const t = nyClock(I.time[i] + OFF + tf * 60);
      if (pos && t.mins >= 660) return sell("11 am in New York. Selling.");
      if (pos) return checkExits(this, I, i) || wait(`${holdingMsg(this)} Sells at 11 am.`);
      const D = NYDAYS(I, tf), a = I.atr14[i], prev = D.prevClose[i];
      if (!D.stock[i]) return wait("Stocks only (needs a market that closes overnight).");
      if (i !== D.first[i]) return wait("Only trades the first candle of the day.");
      if (prev == null || a == null) return wait("Waiting for a previous day's close.");
      const gap = (prev - I.open[i]) / prev;
      if (gap >= 0.003 && I.close[i] < prev) return enter(this, i, `Opened ${pct(gap, 2)} under yesterday's close (${fmtP(prev)}). Aiming to fill the gap.`, { target: prev, stop: I.low[i] - 0.5 * a });
      return wait(gap > 0 ? `Small gap down (${pct(gap, 2)}). Needs 0.3%.` : "No gap down this morning.");
    } },

  // ----- statistics and learning -----
  { id: "hourodds", name: "Hour Odds", type: "Stats", color: "#b5179e",
    desc: "Learns which hours of the day have tended to rise. For the New York hour the next candle falls in, it checks the average next-candle move so far. It owns the market when that average is positive with a t-statistic of at least 1.5 (seen 30+ times), and sits out when it's zero or negative. Needs candles of 1 hour or shorter.",
    overlays: () => [],
    decide(I, i, pos) {
      const tf = tfMins();
      if (tf > 60) return needFast(60);
      const H = HOURODDS(I, tf), m = H.mean[i], t = H.tstat[i], n = H.count[i];
      const hour = Math.floor(nyClock(I.time[i] + OFF + tf * 60).mins / 60);
      if (n < 30 || m == null) return wait(`The ${hour}:00 hour has only been seen ${n} times. Needs 30.`);
      const odds = `The ${hour}:00 New York hour has averaged ${pct(m, 3)} per candle (t ${t.toFixed(1)}, ${n} times)`;
      if (!pos && m > 0 && t >= 1.5) return buy(`${odds}. Buying.`);
      if (pos && m <= 0) return sell(`${odds}. Selling.`);
      return wait(`${odds}. ${pos ? "Holding." : "Needs a positive average with t of 1.5+."}`);
    } },
  { id: "regime", name: "Regime Switcher", type: "Stats", color: "#7209b7",
    desc: "Checks whether moves have been repeating or reversing over the last 100 candles (their autocorrelation). When they repeat (above +0.1), it buys after up candles and sells after down ones. When they reverse (below −0.1), it buys after down candles and sells after up ones. In between it sits out.",
    overlays: () => [],
    decide(I, i, pos) {
      if (i < 102) return warm(102, i);
      const r = RET(I), ac = autocorr(r, i), up = r[i] > 0, down = r[i] < 0;
      const mode = ac > 0.1 ? "momentum" : ac < -0.1 ? "reversal" : "neutral", why = `Autocorrelation ${ac.toFixed(2)} (${mode}).`;
      if (mode === "neutral") return pos ? sell(`${why} No clear pattern: selling.`) : wait(`${why} Sitting out.`);
      const wantIn = mode === "momentum" ? up : down, wantOut = mode === "momentum" ? down : up;
      if (!pos && wantIn) return buy(`${why} Last candle ${up ? "rose" : "fell"}: buying.`);
      if (pos && wantOut) return sell(`${why} Last candle ${up ? "rose" : "fell"}: selling.`);
      return wait(`${why} ${pos ? "Holding." : "Waiting."}`);
    } },
  { id: "learner", name: "Learning Bot", type: "Stats", color: "#560bad",
    desc: "A tiny machine-learning model that trains itself one candle at a time on this chart's own history. From the last three moves, RSI and volume, it estimates the chance the next candle closes higher. Buys at 55% or more once it has learned from 200 candles, and sells at 50% or less.",
    overlays: () => [],
    decide(I, i, pos) {
      const L = LEARNER(I), p = L.prob[i], n = L.seen[i];
      if (p == null || n < 200) return wait(`Learning. Has trained on ${n} of 200 candles.`);
      if (!pos && p >= 0.55) return buy(`The model gives the next candle a ${pct(p, 0)} chance of closing higher. Buying.`);
      if (pos && p <= 0.5) return sell(`The model's chance dropped to ${pct(p, 0)}. Selling.`);
      return wait(`Chance the next candle closes higher: ${pct(p, 0)}. ${pos ? "Holding while it's over 50%." : "Needs 55%."}`);
    } },

  // ----- compared with bitcoin -----
  { id: "btcecho", name: "Bitcoin Echo", type: "vs Bitcoin", color: "#f77f00",
    desc: "When bitcoin's last candle jumped more than 2.5 standard deviations but this coin barely moved (under 1), buys the coin, betting it follows bitcoin within 3 candles. Needs bitcoin's candles for the same times.",
    overlays() { return riskLines(this); },
    decide(I, i, pos) {
      if (!I.btc) return wait("Needs bitcoin's candles for the same times.");
      if (pos) return checkExits(this, I, i) || wait(`Holding. ${3 - (i - this.st.entryIdx)} candles left.`);
      const b = get(I, "btcret", () => I.btc.map((x, j) => j ? x / I.btc[j - 1] - 1 : 0));
      const zb = zNow(b, i), zc = zNow(RET(I), i);
      if (zb == null || zc == null) return warm(102, i);
      if (zb > 2.5 && zc < 1) return enter(this, i, `Bitcoin jumped ${zb.toFixed(1)} sigma, but this coin only ${zc.toFixed(1)}. Betting it catches up within 3 candles.`, { maxBars: 3 });
      return wait(`Bitcoin ${zb.toFixed(1)} sigma, this coin ${zc.toFixed(1)}. Waiting for a bitcoin jump this coin misses.`);
    } },
);
})();

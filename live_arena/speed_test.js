// ⚡ Speed test runner (rules in SPEED_TEST.md). speed_test.py opens the app in headless Chrome at /?speed=YYYY-MM-DD,
// the Monday (00:00 UTC) that starts the week. Every bot paper-trades that week on 5- and 15-minute candles, and the
// results go to /api/speedresult. Paper money only.
(() => {
"use strict";
const week = new URLSearchParams(location.search).get("speed");
if (!/^\d{4}-\d{2}-\d{2}$/.test(week || "")) return;

// The timing test. Rebuilds how much of the account was in the market during each candle from the bot's fills, then
// compares its result (before fees) with the same in-and-out pattern slid to other times in the week. A bot with
// real timing skill should beat most of those slid copies; one without it lands anywhere among them.
function timing(rows, fills, from, fee, shifts) {
  const L = rows.length - 1 - from, out = { gross: 0, shifted: new Float64Array(shifts) };
  if (L < 2 || !fills.length) return out;
  const at = new Map();
  for (const f of fills) at.set(f.time, [...(at.get(f.time) || []), f]);
  const exposure = new Float64Array(L), move = new Float64Array(L);
  let qty = 0, cash = START_CASH;
  for (let k = 0; k < L; k++) {
    const t = from + k;
    for (const f of at.get(rows[t].time) || []) {   // fills happen at the open of the candle they're stamped with
      if (f.side === "buy") { qty += f.qty; cash -= f.qty * f.price / (1 - fee); }
      else { qty -= f.qty; cash += f.qty * f.price * (1 - fee); }
    }
    if (qty < 1e-12) qty = 0;
    const value = qty * rows[t].open;
    exposure[k] = value > 0 ? value / (cash + value) : 0;
    move[k] = rows[t + 1].open / rows[t].open - 1;
  }
  for (let k = 0; k < L; k++) out.gross += exposure[k] * move[k];
  for (let j = 0; j < shifts; j++) {
    const s = Math.round((j + 1) * L / (shifts + 1));
    let g = 0;
    for (let k = 0; k < L; k++) g += exposure[(k + s) % L] * move[k];
    out.shifted[j] = g;
  }
  return out;
}

const post = body => fetch("/api/speedresult", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const pause = () => new Promise(done => setTimeout(done, 0));

async function run() {
  gen++; stopPlay(); clearTimeout(retryT);
  if (ws) { ws.onclose = null; ws.close(); ws = null; }
  mode = "replay";
  const M = await (await fetch("data/speed/manifest.json", { cache: "no-store" })).json();
  const start = Date.parse(`${week}T00:00:00Z`) / 1000, end = start + 7 * 86400, groups = [];
  for (const g of M.groups) for (const tf of M.timeframes) {
    $("tf").value = tf;
    $("fee").value = g.fee;
    const fee = +g.fee / 100, data = {}, missing = [];
    for (const symbol of g.symbols) {
      try {
        const rows = (await loadRows(`data/speed/${g.id}/${symbol}_${tf}.json`))
          .filter(r => r.time + OFF >= start - M.warmup_days * 86400 && r.time + OFF < end);
        const inWeek = rows.filter(r => r.time + OFF >= start).length;
        if (inWeek > 10 && rows[rows.length - 1].time + OFF >= end - 3 * 86400) data[symbol] = rows;
        else missing.push(symbol);
      } catch {
        missing.push(symbol);
      }
    }
    const symbols = Object.keys(data);
    if (!symbols.length) { groups.push({ group: g.id, name: g.name, unit: g.unit, tf, fee: g.fee, markets: [], missing, hold: null, bots: [] }); continue; }
    paperFrom = start - OFF;   // candle times are shifted to local time
    REF = g.ref && data[g.ref] ? data[g.ref] : null;
    // the other markets in the group and the outside signals, for the bots that read them (data_bots.js, lesson_bots.js)
    const outside = {}, perTf = new Set(M.per_tf_outside || ["vix"]);   // series saved once per candle size
    for (const name of g.outside || []) {
      try {
        if (name === "kronos") {   // one file per group holding every market's forecasts (kronos_forecasts.py)
          const j = await (await fetch(`data/speed/outside/kronos_${g.id}.json`, { cache: "no-store" })).json();
          outside.kronos = Object.fromEntries(Object.entries(j.result).map(([s, rows]) =>
            [s, rows.map(x => ({ time: x[0] - OFF, open: +x[1], high: +x[2], low: +x[3], close: +x[4], volume: +x[6] }))]));
        } else if (name === "nvidia") {   // one file per group holding every market's daily calls (nvidia_forecasts.py)
          const j = await (await fetch(`data/speed/outside/nvidia_${g.id}.json`, { cache: "no-store" })).json();
          outside.nvidia = Object.fromEntries(Object.entries(j.result).map(([s, rows]) =>
            [s, rows.map(x => ({ time: x[0] - OFF, action: x[1], reason: x[2] }))]));
        } else outside[name] = await loadRows(`data/speed/outside/${perTf.has(name) ? `${name}_${tf}` : name}.json`);
      } catch {
        outside[name] = null;
      }
    }
    window.SPEED_EXT = { tf, group: data, symbols, outside };
    const runs = {};
    for (const s of symbols) {
      const rows = data[s];
      window.SPEED_EXT.current = s;   // which market in the group the bots are trading right now
      runs[s] = { rows, res: simulateRows(rows, true, paperFrom), hold: holdReturn(rows, g.fee), from: forwardIndex(rows) };
      await pause();
    }
    const holds = symbols.map(s => runs[s].hold).filter(x => x != null);
    const hold = holds.length ? holds.reduce((a, x) => a + x, 0) / holds.length : null;
    const bots = BOTS.map(b => {
      const rets = symbols.map(s => runs[s].res[b.id].ret), trades = symbols.reduce((n, s) => n + runs[s].res[b.id].trades, 0);
      const closedOf = s => runs[s].res[b.id].fills.filter(f => f.side === "sell").length;
      const closed = symbols.reduce((n, s) => n + closedOf(s), 0);
      // per-market breakdown, so a picker that trades only one bot on one market (best_recent.py) has real
      // trailing numbers to rank instead of only this group's average across all of them
      const per = Object.fromEntries(symbols.map(s => [s, { ret: runs[s].res[b.id].ret, closed: closedOf(s) }]));
      let gross = 0;
      const shifted = new Float64Array(M.shifts);
      for (const s of symbols) {
        const T = timing(runs[s].rows, runs[s].res[b.id].fills, runs[s].from, fee, M.shifts);
        gross += T.gross;
        for (let j = 0; j < M.shifts; j++) shifted[j] += T.shifted[j];
      }
      let beaten = 0;
      for (let j = 0; j < M.shifts; j++) if (shifted[j] < gross - 1e-12) beaten++;
      const avg = rets.reduce((a, x) => a + x, 0) / rets.length, up = rets.filter(x => x > 0).length, share = beaten / M.shifts;
      const fails = [];
      if (closed < M.min_closed_trades) fails.push(`only ${closed} closed trades`);
      if (!(avg > 0)) fails.push("lost money");
      if (hold != null && !(avg > hold + 1e-6)) fails.push(avg > hold - 1e-6 ? "tied just holding" : "trailed just holding");   // a tie isn't a win
      if (!(up > symbols.length / 2)) fails.push(`made money in ${up} of ${symbols.length}`);
      if (!(share >= M.timing_share)) fails.push(`timing beat ${Math.round(share * 100)}% of random`);
      return { id: b.id, name: b.name, type: b.type, control: !!b.bench || b.type === "Control", avg, med: medianOf(rets), up, trades, closed,
               timing: share, pass: !fails.length, fails, per };
    });
    groups.push({ group: g.id, name: g.name, unit: g.unit, tf, fee: g.fee, markets: symbols, missing, hold,
                  through: Math.max(...symbols.map(s => data[s][data[s].length - 1].time + OFF)), bots });
    await pause();
  }
  paperFrom = PAPER_FROM;
  REF = null;
  window.SPEED_EXT = null;
  $("fee").value = "0.10";
  await post({ week, start, end, generated: new Date().toISOString(), bot_count: BOTS.length, groups });
}
run().catch(e => post({ week, error: String((e && e.stack) || e) }));
})();

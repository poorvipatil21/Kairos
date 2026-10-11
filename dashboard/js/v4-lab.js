/* Kairos v4: Strategy Lab (custom backtests, parameter heatmap, engine benchmark) */
let LAB_SPEC = null, LAB_RES = null, LAB_GRID = null, labSegK = 'full', labGridK = 'is';

async function labInit() {
  if (LAB_SPEC) return;
  try {
    const d = await getJSON('/api/lab/strategies');
    LAB_SPEC = d.strategies;
    const eb = document.getElementById('lab-engine');
    eb.textContent = d.has_cpp ? 'engine: C++ (pybind11) ✓' : 'engine: NumPy (run ./build_cpp.sh for C++)';
    eb.classList.toggle('cpp', !!d.has_cpp);
    document.getElementById('lab-strat').innerHTML = Object.entries(LAB_SPEC).map(([k, v]) => `<option value="${k}">${v.name}</option>`).join('');
    labRenderParams();
    if (!document.getElementById('lab-sym').value) labSetSymbol(curSym || (MARKET === 'india' ? 'RELIANCE.NS' : 'AAPL'));
  } catch { toast('Strategy Lab', 'Could not load strategies', 'err'); }
}
function labSetSymbol(s) { const el = document.getElementById('lab-sym'); if (el) el.value = s; }
function labRenderParams(vals) {
  const k = document.getElementById('lab-strat').value, st = LAB_SPEC[k];
  document.getElementById('lab-desc').textContent = st.desc;
  document.getElementById('lab-params').innerHTML = st.params.map(p => `<div class="fld"><label>${p.label}</label>
    <input class="inp mono" type="number" id="lab-p-${p.key}" value="${vals && vals[p.key] != null ? vals[p.key] : p.default}" min="${p.min}" max="${p.max}" step="${p.step}"></div>`).join('');
  document.getElementById('lab-short-wrap').style.display = st.short ? 'flex' : 'none';
}
function labParams() {
  const st = LAB_SPEC[document.getElementById('lab-strat').value], o = {};
  st.params.forEach(p => { o[p.key] = parseFloat(document.getElementById('lab-p-' + p.key).value); });
  return o;
}
function labQuery(extra = {}) {
  const q = new URLSearchParams({
    symbol: normSym(document.getElementById('lab-sym').value),
    strategy: document.getElementById('lab-strat').value,
    period: document.getElementById('lab-period').value,
    cost: document.getElementById('lab-cost').value || 0,
    oos: (parseFloat(document.getElementById('lab-oos').value) || 0) / 100,
    short: document.getElementById('lab-short').checked,
    capital: document.getElementById('lab-cap').value || 100000,
    ...extra,
  });
  return q;
}
async function labRun() {
  await labInit();
  const sym = normSym(document.getElementById('lab-sym').value);
  if (!sym) { toast('Strategy Lab', 'Enter a symbol first', 'warn'); return; }
  document.getElementById('lab-sym').value = sym;
  const btn = document.getElementById('lab-run'); busy(btn, true, 'Running…');
  try {
    const r = await getJSON('/api/lab/backtest?' + labQuery({ params: JSON.stringify(labParams()) }));
    if (r.error) { toast('Backtest failed', r.error, 'err'); return; }
    LAB_RES = r;
    if (!r.metrics[labSegK]) labSegK = 'full';
    document.querySelectorAll('#lab-seg .chip').forEach(c => c.classList.toggle('active', c.getAttribute('onclick').includes(`'${labSegK}'`)));
    const pstr = Object.entries(r.params).map(([k, v]) => `${k}=${v}`).join(', ');
    document.getElementById('lab-title').textContent = `${shortSym(r.symbol)} · ${r.name}`;
    document.getElementById('lab-sub').textContent = `${pstr} · ${r.dates[0]} → ${r.dates[r.dates.length - 1]} · ${document.getElementById('lab-cost').value} bps costs · ${r.engine}`;
    labMetrics(); labCharts(); labTrades();
    if (LAB_GRID && LAB_GRID.symbol === r.symbol && LAB_GRID.strategy === r.strategy) labGridRender();
  } catch { toast('Backtest failed', 'Server error', 'err'); }
  finally { busy(btn, false); }
}
function labSeg(k, el) {
  labSegK = k;
  document.querySelectorAll('#lab-seg .chip').forEach(c => c.classList.remove('active'));
  el.classList.add('active'); if (LAB_RES) labMetrics();
}
function labMetrics() {
  const m = LAB_RES.metrics[labSegK];
  const el = document.getElementById('lab-metrics');
  if (!m) { el.innerHTML = '<div class="note">Set out-of-sample above 0% to see this split.</div>'; return; }
  const card = (l, v, c = '', sub = '') => `<div class="fc-stat"><div class="l">${l}</div><div class="v ${c}">${v}${sub ? `<small style="display:block;font-size:.58rem;color:var(--muted);font-weight:400">${sub}</small>` : ''}</div></div>`;
  const pf = m.profit_factor == null ? '∞' : m.profit_factor.toFixed(2);
  el.innerHTML =
    card('Total return', pct(m.total_return), cls(m.total_return), `buy & hold ${pct(m.bh_return)}`) +
    card('CAGR', pct(m.cagr), cls(m.cagr)) +
    card('Sharpe', m.sharpe.toFixed(2), cls(m.sharpe), `buy & hold ${m.bh_sharpe.toFixed(2)}`) +
    card('Sortino', m.sortino.toFixed(2), cls(m.sortino)) +
    card('Max drawdown', pct(-m.max_dd), 'neg') +
    card('Calmar', m.calmar.toFixed(2), cls(m.calmar)) +
    card('Trades', m.trades, '', `avg ${m.avg_bars.toFixed(0)} bars`) +
    card('Win rate', (m.win_rate * 100).toFixed(0) + '%') +
    card('Avg trade', pct(m.avg_trade, 2), cls(m.avg_trade)) +
    card('Profit factor', pf) +
    card('Exposure', ((m.exposure || 0) * 100).toFixed(0) + '%', '', 'time in market') +
    card('Volatility', pct(m.vol), '', 'annualised');
}
function labCharts() {
  const r = LAB_RES, idx = new Map(r.dates.map((d, i) => [d, i]));
  const split = r.split;
  plot(document.getElementById('lab-price-svg'), [{ vals: r.close, color: 'var(--cyan)', w: 1.5 }], {
    H: 260, dates: r.dates, split, yfmt: v => nfs(v),
    pre: ({ xs, ys, pl, H }) => {   // shade periods in the market
      let g = '', s = null;
      r.position.forEach((p, i) => {
        if (p !== 0 && s === null) s = i;
        if ((p === 0 || i === r.position.length - 1) && s !== null) {
          const e = p === 0 ? i : i, col = r.position[s] > 0 ? 'rgba(0,208,132,.06)' : 'rgba(255,71,87,.07)';
          g += `<rect x="${xs(s)}" y="${pl.t}" width="${Math.max(1, xs(e) - xs(s))}" height="${H - pl.t - pl.b}" fill="${col}"/>`; s = null;
        }
      });
      return g;
    },
    extra: ({ xs, ys }) => r.trades.map(t => {
      const i = idx.get(t.entry_date), j = idx.get(t.exit_date); let g = '';
      if (i != null) { const x = xs(i), y = ys(r.close[i]), lg = t.side === 'LONG';
        g += `<path d="M${x},${lg ? y + 4 : y - 4} l-4,${lg ? 7 : -7} h8 z" fill="${lg ? 'var(--green)' : 'var(--orange)'}"><title>${t.side} ${t.entry_date} @ ${nf(t.entry)}</title></path>`; }
      if (j != null && !t.open) { const x = xs(j), y = ys(r.close[j]);
        g += `<path d="M${x},${y - 4} l-4,-7 h8 z" fill="${t.ret >= 0 ? 'var(--gold)' : 'var(--red)'}"><title>exit ${t.exit_date} @ ${nf(t.exit)} · ${pct(t.ret)}</title></path>`; }
      return g;
    }).join(''),
  });
  plot(document.getElementById('lab-eq-svg'), [
    { vals: r.bh_equity, color: 'var(--muted)', w: 1.2, dash: '4 3' },
    { vals: r.equity, color: 'var(--blue)', w: 2, area: 'rgba(79,163,255,.08)' }], {
    H: 200, dates: r.dates, split, hlines: [{ v: r.equity[0], color: 'var(--border2)' }],
    extra: ({ W, pl }) => `<text x="${pl.l + 4}" y="${pl.t + 10}" fill="var(--blue)" font-size="9" font-family="IBM Plex Mono">● strategy ${pct(r.equity[r.equity.length - 1] / r.equity[0] - 1)}</text>
      <text x="${pl.l + 4}" y="${pl.t + 22}" fill="var(--muted)" font-size="9" font-family="IBM Plex Mono">┄ buy &amp; hold ${pct(r.bh_equity[r.bh_equity.length - 1] / r.bh_equity[0] - 1)}</text>`,
  });
  plot(document.getElementById('lab-dd-svg'), [{ vals: r.drawdown.map(v => v * 100), color: 'var(--red)', w: 1.2, area: 'rgba(255,71,87,.15)', areaBase: 0 }], {
    H: 110, split, max: 0, yfmt: v => v.toFixed(0) + '%',
  });
}
function labTrades() {
  const t = LAB_RES.trades.slice().reverse();
  document.getElementById('lab-trades').innerHTML = t.length ? `<table class="tbl"><tr><th>Side</th><th>Entry</th><th>Entry px</th><th>Exit</th><th>Exit px</th><th>Bars</th><th>Return</th></tr>` +
    t.slice(0, 60).map(x => `<tr><td style="font-family:var(--sans)"><span class="pill ${x.side === 'LONG' ? 'g' : 'r'}">${x.side}</span>${x.open ? ' <span class="note">open</span>' : ''}</td>
      <td>${x.entry_date}</td><td>${nf(x.entry)}</td><td>${x.open ? '—' : x.exit_date}</td><td>${nf(x.exit)}</td><td>${x.bars}</td><td class="${cls(x.ret)}">${pct(x.ret, 2)}</td></tr>`).join('') +
    `</table>${t.length > 60 ? `<div class="note" style="margin-top:6px">Showing the latest 60 of ${t.length} trades.</div>` : ''}` : '<div class="note">No trades in this period.</div>';
}

/* parameter heatmap */
async function labGrid() {
  await labInit();
  const sym = normSym(document.getElementById('lab-sym').value);
  if (!sym) { toast('Strategy Lab', 'Enter a symbol first', 'warn'); return; }
  const btn = document.getElementById('lab-grid-btn'); busy(btn, true, 'Sweeping…');
  try {
    const g = await getJSON('/api/lab/grid?' + labQuery());
    if (g.error) { toast('Heatmap failed', g.error, 'err'); return; }
    g.symbol = sym; g.strategy = document.getElementById('lab-strat').value;
    LAB_GRID = g;
    document.getElementById('lab-grid-card').style.display = 'block';
    labGridRender();
    document.getElementById('lab-grid-card').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  } catch { toast('Heatmap failed', 'Server error', 'err'); }
  finally { busy(btn, false); }
}
function labGridView(k, el) {
  labGridK = k;
  document.querySelectorAll('#lab-grid-tabs .chip').forEach(c => c.classList.remove('active'));
  el.classList.add('active'); if (LAB_GRID) labGridRender();
}
function sharpeColor(v) {
  if (v == null) return '#0b131d';
  const t = Math.max(-1, Math.min(1, v / 1.5));
  return t >= 0 ? `rgba(0,${Math.round(90 + t * 118)},${Math.round(90 - t * 40)},${0.35 + t * 0.6})` : `rgba(${Math.round(120 - t * 135)},50,${Math.round(60 - t * 10)},${0.35 - t * 0.6})`;
}
function labGridRender() {
  const g = LAB_GRID, M = g[labGridK], st = LAB_SPEC[g.strategy];
  const lbl = k => (st.params.find(p => p.key === k) || {}).label || k;
  const cur = labParams();
  let h = `<div class="hm-grid" style="grid-template-columns:70px repeat(${g.x.length},1fr)"><div class="hm-hd">${lbl(g.y_key)} ↓ / ${lbl(g.x_key)} →</div>` +
    g.x.map(x => `<div class="hm-hd">${x}</div>`).join('');
  g.y.forEach((y, yi) => {
    h += `<div class="hm-hd">${y}</div>`;
    g.x.forEach((x, xi) => {
      const v = M[yi][xi];
      const isCur = +cur[g.x_key] === +x && +cur[g.y_key] === +y;
      h += v == null ? `<div class="hm-cell na">·</div>` :
        `<div class="hm-cell ${isCur ? 'cur' : ''}" style="background:${sharpeColor(v)}" title="${g.x_key}=${x}, ${g.y_key}=${y}\nIS Sharpe ${g.is[yi][xi]}\nOOS Sharpe ${g.oos[yi][xi]}" onclick="labPick('${g.x_key}',${x},'${g.y_key}',${y})">${v.toFixed(2)}</div>`;
    });
  });
  document.getElementById('lab-grid').innerHTML = h + '</div>';
  document.getElementById('lab-grid-title').textContent = `Parameter heatmap · ${shortSym(g.symbol)} · ${st.name} · ${g.engine} · ${g.ms} ms`;
  const b = g.best;
  document.getElementById('lab-grid-note').innerHTML = b ? `Best in-sample: <b>${g.x_key}=${b.x}, ${g.y_key}=${b.y}</b> with Sharpe <b>${b.is_sharpe.toFixed(2)}</b>, which scored <b class="${cls(b.oos_sharpe)}">${b.oos_sharpe == null ? '—' : b.oos_sharpe.toFixed(2)}</b> out-of-sample (after ${g.split_date}).
    ${b.oos_sharpe != null && b.oos_sharpe < b.is_sharpe * 0.5 ? ' That is a big drop, a typical sign of overfitting. ' : ' '}Prefer a broad green plateau over a single bright cell. Click any cell to load those parameters and run.` : '';
}
function labPick(xk, x, yk, y) {
  const a = document.getElementById('lab-p-' + xk), b = document.getElementById('lab-p-' + yk);
  if (a) a.value = x; if (b) b.value = y;
  labRun();
}

/* engine benchmark */
async function labBench() {
  const btn = document.getElementById('bench-btn'); busy(btn, true, 'Benchmarking…');
  const el = document.getElementById('lab-bench');
  try {
    const b = await getJSON('/api/lab/benchmark');
    if (b.error) { el.innerHTML = `<div class="note">${b.error}</div>`; return; }
    const max = Math.max(...b.results.map(r => r.per_sec));
    el.innerHTML = `<div class="note" style="margin-bottom:8px">${b.grid} moving-average backtests on ${b.bars} daily bars of ${b.symbol}. Pure Python runs a 60-backtest sample, then everything is compared per backtest.</div>` +
      b.results.map(r => `<div class="bench-bar"><span>${r.engine}</span>
        <div class="bench-track"><div class="bench-fill ${r.engine.startsWith('C++') ? 'cpp' : ''}" style="width:${Math.max(1.5, r.per_sec / max * 100)}%"></div></div>
        <span style="font-family:var(--mono);text-align:right">${Math.round(r.per_sec).toLocaleString()}/s · <b>${r.speedup.toFixed(0)}×</b></span></div>`).join('') +
      (b.has_cpp ? `<div class="note" style="margin-top:6px">C++ and NumPy agree to ${b.max_abs_diff_cpp_vs_numpy != null ? b.max_abs_diff_cpp_vs_numpy.toExponential(1) : '—'} in Sharpe (max absolute difference across the grid).</div>`
        : `<div class="note" style="margin-top:6px">C++ engine not built yet. Run <code>./build_cpp.sh</code> in the kairos folder and restart the server.</div>`);
  } catch { el.innerHTML = '<div class="note">Benchmark failed</div>'; }
  finally { busy(btn, false); }
}

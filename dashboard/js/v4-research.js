/* Kairos v4: research views. Cointegration pairs + pairs backtest, portfolio optimiser,
   forecasts with Gaussian / conformal / regime-conformal bands and coverage check. */

/* ══════════════════════════════════════ PAIRS */
let _pairSel = null, _pairRes = null;
function renderPairs(pairs) {
  const el = document.getElementById('pairs-list');
  if (!pairs.length) { el.innerHTML = '<div class="note" style="padding:14px">No pairs above this correlation. Try a lower threshold.</div>'; return; }
  el.innerHTML = pairs.map(p => {
    const pctv = (p.correlation * 100).toFixed(0), same = p.sector1 === p.sector2;
    const pc = p.pbucket === '<1%' || p.pbucket === '<5%' ? 'g' : p.pbucket === '<10%' ? '' : 'r';
    return `<div class="pair-row" onclick="showPair('${p.sym1}','${p.sym2}',${p.correlation},this)">
      <div><div class="pair-syms">${shortSym(p.sym1)} / ${shortSym(p.sym2)}</div>
        <div class="pair-sectors">${esc(p.sector1)}${same ? '' : ' · ' + esc(p.sector2)}</div>
        <div class="pair-meta"><span class="pill ${pc}" title="Engle-Granger cointegration p-value (ADF on the hedge-ratio spread)">coint p ${p.pbucket || '?'}</span>${p.half_life != null ? `<span class="pill" style="color:var(--muted)" title="Half-life of mean reversion">½-life ${p.half_life}d</span>` : ''}</div></div>
      <div class="pair-corr-bar"><div class="pair-corr-fill" style="width:${pctv}%"></div></div>
      <div class="pair-corr-val">r=${p.correlation}</div></div>`;
  }).join('');
}
async function showPair(s1, s2, corr, row) {
  if (row) { document.querySelectorAll('.pair-row').forEach(r => r.classList.remove('active')); row.classList.add('active'); }
  _pairSel = { s1, s2, corr };
  document.getElementById('pair-title').textContent = shortSym(s1) + ' / ' + shortSym(s2);
  document.getElementById('pair-subtitle').textContent = 'Testing cointegration and backtesting…';
  document.getElementById('pair-expand-btn').style.display = 'flex';
  const v = id => document.getElementById(id).value;
  try {
    const r = await getJSON('/api/pairs/analyze?' + new URLSearchParams({ s1, s2, entry: v('pbt-entry'), exit: v('pbt-exit'), window: v('pbt-win'), cost: v('pbt-cost') }));
    if (r.error) { document.getElementById('pair-subtitle').textContent = r.error; return; }
    _pairRes = r; _pairRes.corr = corr;
    _lastPairData = { c1: r.p1, c2: r.p2, s1, s2 };
    drawPairAll();
  } catch { document.getElementById('pair-subtitle').textContent = 'Could not analyse this pair'; }
}
function pairRerun() { if (_pairSel) showPair(_pairSel.s1, _pairSel.s2, _pairSel.corr, null); }
function drawPairAll() {
  const r = _pairRes, ct = r.coint, a = shortSym(r.s1), b = shortSym(r.s2);
  const hl = ct.half_life == null ? '∞' : ct.half_life.toFixed(1) + ' days';
  const pv = ct.p_exact && ct.pvalue != null ? ct.pvalue.toFixed(3) : ct.pbucket;
  document.getElementById('pair-subtitle').innerHTML = `r = ${r.corr} · hedge ratio β = ${ct.beta.toFixed(3)} · ADF ${ct.adf.toFixed(2)} · coint p <b class="${(ct.pvalue ?? 1) < 0.05 ? 'pos' : 'neg'}">${pv}</b> · half-life ${hl}`;
  plot(document.getElementById('pair-price-svg'), [
    { vals: r.p1.map(v => v / r.p1[0] * 100), color: 'var(--blue)', w: 1.8 },
    { vals: r.p2.map(v => v / r.p2[0] * 100), color: 'var(--orange)', w: 1.8 }], {
    H: 180, dates: r.dates, hlines: [{ v: 100 }],
    extra: ({ pl }) => `<text x="${pl.l + 4}" y="${pl.t + 10}" fill="var(--blue)" font-size="9" font-family="IBM Plex Mono">● ${a}</text><text x="${pl.l + 4}" y="${pl.t + 22}" fill="var(--orange)" font-size="9" font-family="IBM Plex Mono">● ${b}</text>`,
  });
  document.getElementById('pair-spread-lbl').textContent = `Spread z-score · log ${a} − ${ct.beta.toFixed(2)} × log ${b} · ${r.window}-day window`;
  const zv = r.z.filter(v => v != null), zmax = Math.max(r.entry + 0.5, ...zv.map(Math.abs));
  plot(document.getElementById('pair-spread-svg'), [{ vals: r.z, color: 'var(--cyan)', w: 1.3 }], {
    H: 140, dates: r.dates, min: -zmax, max: zmax, yfmt: v => v.toFixed(1),
    hlines: [{ v: r.entry, color: 'rgba(255,71,87,.7)', label: `+${r.entry}σ short spread` }, { v: -r.entry, color: 'rgba(0,208,132,.7)', label: `−${r.entry}σ long spread` },
      { v: r.exit, color: 'var(--border2)' }, { v: -r.exit, color: 'var(--border2)' }, { v: 0, color: 'var(--border2)', dash: '' }],
    pre: ({ xs, pl, H }) => {
      let g = '', s = null;
      r.position.forEach((p, i) => {
        if (p !== 0 && s === null) s = i;
        if ((p === 0 || i === r.position.length - 1) && s !== null) {
          g += `<rect x="${xs(s)}" y="${pl.t}" width="${Math.max(1, xs(i) - xs(s))}" height="${H - pl.t - pl.b}" fill="${r.position[s] > 0 ? 'rgba(0,208,132,.08)' : 'rgba(255,71,87,.08)'}"/>`; s = null;
        }
      });
      return g;
    },
  });
  // live signal
  const z = r.current_z, card = document.getElementById('signal-card');
  if (z != null) {
    const az = Math.abs(z); let badge, bc, title, desc;
    const legB = ct.beta >= 0 ? `sell ${Math.abs(ct.beta).toFixed(2)}× ${b}` : `buy ${Math.abs(ct.beta).toFixed(2)}× ${b}`;
    const legBs = ct.beta >= 0 ? `buy ${Math.abs(ct.beta).toFixed(2)}× ${b}` : `sell ${Math.abs(ct.beta).toFixed(2)}× ${b}`;
    if (z >= r.entry) { badge = '⬇ SHORT SPREAD'; bc = 'short'; title = `Sell ${a}, ${legBs}`; desc = `Spread is ${z.toFixed(2)}σ above its ${r.window}-day mean. Bet it falls back to within ±${r.exit}σ.`; }
    else if (z <= -r.entry) { badge = '⬆ LONG SPREAD'; bc = 'long'; title = `Buy ${a}, ${legB}`; desc = `Spread is ${Math.abs(z).toFixed(2)}σ below its mean. Bet it rises back to within ±${r.exit}σ.`; }
    else if (az >= r.exit) { badge = '👁 WATCH'; bc = 'watch'; title = 'Between exit and entry bands'; desc = `z = ${z.toFixed(2)}. An open trade would be held. A new entry needs |z| ≥ ${r.entry}.`; }
    else { badge = '◉ NEUTRAL'; bc = 'neutral'; title = 'Spread near its mean'; desc = `z = ${z.toFixed(2)}. No edge right now.`; }
    if ((ct.pvalue ?? 1) >= 0.10) desc += ' Caution: this pair is not cointegrated at 10%, so the spread may not mean-revert.';
    card.style.display = 'flex';
    document.getElementById('signal-badge').className = 'signal-badge ' + bc;
    document.getElementById('signal-badge').textContent = badge;
    document.getElementById('signal-title').textContent = title;
    document.getElementById('signal-desc').textContent = desc;
    document.getElementById('zscore-val').textContent = z.toFixed(2);
    document.getElementById('zscore-val').className = 'zscore-val ' + (az >= r.entry ? 'pos' : '');
  } else card.style.display = 'none';
  const m = r.metrics, st = (l, v, c = '') => `<div class="fc-stat"><div class="l">${l}</div><div class="v ${c}">${v}</div></div>`;
  document.getElementById('pbt-stats').innerHTML = st('Return', pct(m.total_return), cls(m.total_return)) + st('Sharpe', (m.sharpe ?? 0).toFixed(2), cls(m.sharpe)) +
    st('Max drawdown', pct(-(m.max_dd || 0)), 'neg') + st('Trades', m.trades) + st('Win rate', ((m.win_rate || 0) * 100).toFixed(0) + '%') +
    st('Time in trade', ((m.exposure || 0) * 100).toFixed(0) + '%') + st('Half-life', hl) + st('Coint p', pv, (ct.pvalue ?? 1) < 0.05 ? 'pos' : 'neg');
  plot(document.getElementById('pbt-eq-svg'), [{ vals: r.equity, color: 'var(--green)', w: 1.8, area: 'rgba(0,208,132,.08)' }], { H: 150, dates: r.dates, hlines: [{ v: r.equity[0] }] });
  document.getElementById('pbt-note').textContent = r.note + (r.has_statsmodels ? '' : ' The p-value comes from MacKinnon critical values; pip install statsmodels for the exact value.') + ' Costs are charged on both legs.';
  const t = (r.trades || []).slice().reverse();
  document.getElementById('pbt-trades').innerHTML = t.length ? `<table class="tbl"><tr><th>Side</th><th>Entry</th><th>Exit</th><th>Bars</th><th>Return</th></tr>` +
    t.map(x => `<tr><td style="font-family:var(--sans)"><span class="pill ${x.side.startsWith('LONG') ? 'g' : 'r'}">${x.side}</span></td><td>${x.entry_date}</td><td>${x.exit_date}</td><td>${x.bars}</td><td class="${cls(x.ret)}">${pct(x.ret, 2)}</td></tr>`).join('') + '</table>' : '<div class="note">No completed trades with these settings.</div>';
}

/* ══════════════════════════════════════ PORTFOLIO OPTIMISER */
let _optRes = null;
const OPT_COLORS = { 'Max Sharpe': 'var(--gold)', 'Min Variance': 'var(--cyan)', 'Risk Parity': 'var(--purple)', 'Equal Weight': 'var(--muted)', 'Your Weights': 'var(--blue)' };
async function pfOptimize() {
  const w = {}; pfHoldings.forEach(h => { w[h.sym] = (w[h.sym] || 0) + h.wt; });
  const syms = Object.keys(w);
  if (syms.length < 2) { toast('Portfolio', 'Add at least 2 stocks first', 'warn'); return; }
  const btn = document.getElementById('pf-opt-btn'); busy(btn, true, 'Optimizing…');
  try {
    const r = await postJSON('/api/portfolio/optimize', { symbols: syms, weights: w, period: '1y' });
    if (r.error) { toast('Optimizer', r.error, 'err'); return; }
    _optRes = r;
    document.getElementById('pf-opt').style.display = 'flex';
    pfFrontier(); pfCorr(); pfMethods();
  } catch { toast('Optimizer', 'Server error', 'err'); }
  finally { busy(btn, false); }
}
function pfFrontier() {
  const r = _optRes, svg = document.getElementById('pf-frontier-svg');
  const W = svg.parentElement.offsetWidth || 600, H = 300, pl = { t: 12, b: 28, l: 46, r: 14 };
  const pts = [...r.cloud, ...r.assets, ...r.frontier, ...Object.values(r.methods).map(m => ({ vol: m.vol_pt, ret: m.ret_pt }))];
  const v0 = Math.min(...pts.map(p => p.vol)) * 0.9, v1 = Math.max(...pts.map(p => p.vol)) * 1.05;
  const r0 = Math.min(...pts.map(p => p.ret)), r1 = Math.max(...pts.map(p => p.ret)), rp = (r1 - r0) * 0.08 || 0.05;
  const xs = v => pl.l + (v - v0) / (v1 - v0) * (W - pl.l - pl.r), ys = v => H - pl.b - (v - (r0 - rp)) / ((r1 + rp) - (r0 - rp)) * (H - pl.t - pl.b);
  const smax = Math.max(...r.cloud.map(c => c.sharpe)), smin = Math.min(...r.cloud.map(c => c.sharpe));
  let g = '';
  for (let k = 0; k <= 4; k++) {
    const rv = (r0 - rp) + k / 4 * ((r1 + rp) - (r0 - rp)), vv = v0 + k / 4 * (v1 - v0);
    g += `<line x1="${pl.l}" y1="${ys(rv)}" x2="${W - pl.r}" y2="${ys(rv)}" stroke="var(--border)" stroke-width=".35"/><text x="${pl.l - 4}" y="${ys(rv) + 3}" fill="var(--muted)" font-size="8.5" text-anchor="end" font-family="IBM Plex Mono">${(rv * 100).toFixed(0)}%</text>
      <text x="${xs(vv)}" y="${H - 12}" fill="var(--muted)" font-size="8.5" text-anchor="middle" font-family="IBM Plex Mono">${(vv * 100).toFixed(0)}%</text>`;
  }
  g += `<text x="${W - pl.r}" y="${H - 2}" fill="var(--muted)" font-size="8" text-anchor="end" font-family="IBM Plex Mono">annual volatility →</text><text x="${pl.l}" y="${pl.t - 2}" fill="var(--muted)" font-size="8" font-family="IBM Plex Mono">annual return ↑</text>`;
  r.cloud.forEach(c => { const t = (c.sharpe - smin) / ((smax - smin) || 1); g += `<circle cx="${xs(c.vol)}" cy="${ys(c.ret)}" r="1.6" fill="hsla(${Math.round(t * 140)},80%,55%,.45)"/>`; });
  if (r.frontier.length) g += `<polyline points="${r.frontier.map(f => `${xs(f.vol)},${ys(f.ret)}`).join(' ')}" fill="none" stroke="var(--gold)" stroke-width="2"/>`;
  r.assets.forEach(a => { g += `<circle cx="${xs(a.vol)}" cy="${ys(a.ret)}" r="3" fill="#fff" opacity=".8"/><text x="${xs(a.vol) + 5}" y="${ys(a.ret) + 3}" fill="var(--text)" font-size="8.5" font-family="IBM Plex Mono">${shortSym(a.symbol)}</text>`; });
  Object.entries(r.methods).forEach(([n, m]) => { g += `<circle cx="${xs(m.vol_pt)}" cy="${ys(m.ret_pt)}" r="6" fill="none" stroke="${OPT_COLORS[n]}" stroke-width="2.2"><title>${n}: return ${pct(m.ret_pt)}, vol ${pct(m.vol_pt)}</title></circle>`; });
  g += Object.keys(r.methods).map((n, i) => `<circle cx="${pl.l + 12}" cy="${pl.t + 18 + i * 13}" r="4" fill="none" stroke="${OPT_COLORS[n]}" stroke-width="2"/><text x="${pl.l + 20}" y="${pl.t + 21 + i * 13}" fill="var(--text)" font-size="8.5" font-family="IBM Plex Mono">${n}</text>`).join('');
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`); svg.setAttribute('height', H); svg.innerHTML = g;
}
function pfCorr() {
  const r = _optRes, k = r.symbols.length;
  const col = v => v >= 0 ? `rgba(255,${Math.round(150 - v * 110)},${Math.round(120 - v * 90)},${0.15 + v * 0.75})` : `rgba(60,${Math.round(140 - v * 40)},255,${0.15 - v * 0.75})`;
  let h = `<div class="corr-grid" style="grid-template-columns:62px repeat(${k},1fr)"><div></div>` + r.symbols.map(s => `<div style="color:var(--muted)">${shortSym(s).slice(0, 6)}</div>`).join('');
  r.corr.forEach((row, i) => { h += `<div style="color:var(--muted);text-align:left">${shortSym(r.symbols[i]).slice(0, 8)}</div>` + row.map(v => `<div style="background:${col(v)}" title="${v}">${v.toFixed(2)}</div>`).join(''); });
  document.getElementById('pf-corr').innerHTML = h + '</div>';
}
function pfMethods() {
  const r = _optRes, mk = mktOf(r.symbols[0]);
  const rows = Object.entries(r.methods).map(([n, m]) => `<tr>
    <td style="font-family:var(--sans)"><span style="color:${OPT_COLORS[n]}">●</span> <b>${n}</b></td>
    <td class="${cls(m.ann_return)}">${pct(m.ann_return)}</td><td>${pct(m.ann_vol)}</td><td class="${cls(m.sharpe)}">${m.sharpe.toFixed(2)}</td>
    <td class="neg">${pct(-m.max_dd)}</td><td>${money(m.var95_hist, mk)}</td><td>${money(m.cvar95_hist, mk)}</td><td>${m.beta != null ? m.beta.toFixed(2) : '—'}</td>
    <td style="font-size:.62rem;color:var(--muted);max-width:260px;white-space:normal;text-align:left">${Object.entries(m.weights).filter(([, x]) => x >= 0.005).sort((a, b) => b[1] - a[1]).map(([s, x]) => `${shortSym(s)} ${(x * 100).toFixed(0)}%`).join(' · ')}</td>
    <td>${n === 'Your Weights' ? '' : `<button class="btn ghost" style="padding:3px 9px;font-size:.62rem" onclick="pfApply('${n}')">Apply</button>`}</td></tr>`).join('');
  document.getElementById('pf-methods').innerHTML = `<table class="tbl"><tr><th>Method</th><th>Return</th><th>Vol</th><th>Sharpe</th><th>Max DD</th><th title="1-day 95% historical Value at Risk on 100,000">VaR 95% · 1d</th><th title="Average loss on the worst 5% of days">CVaR 95%</th><th>Beta vs ${r.benchmark === '^NSEI' ? 'Nifty' : 'S&P'}</th><th style="text-align:left">Weights</th><th></th></tr>${rows}</table>`;
  document.getElementById('pf-opt-note').textContent = `Based on ${r.days} trading days (${r.start} to ${r.end}), long only, no leverage. VaR and CVaR are for a ${money(100000, mk)} portfolio over one day. Optimised weights fit the past year and will not hold exactly going forward, which is why risk parity and min variance are often more stable than max Sharpe.`;
}
function pfApply(name) {
  const w = _optRes.methods[name].weights;
  pfHoldings = Object.entries(w).filter(([, x]) => x >= 0.005).map(([sym, x]) => ({ sym, wt: Math.round(x * 1000) / 10 }));
  renderPfHoldings(); pfRun();
  toast('Weights applied', name, 'ok');
}

/* ══════════════════════════════════════ FORECASTS */
let fcBand = 'gauss';
const BAND_NAME = { gauss: 'Gaussian', conf: 'Conformal', rc: 'Regime conformal' };
function setFcBand(b, el) {
  fcBand = b;
  document.querySelectorAll('#fc-band-chips .chip').forEach(c => c.classList.remove('active'));
  el.classList.add('active');
  const d = _fcData[curFcMkt];
  if (d) { renderFcTable(d); selectFc(..._fcIdx); }
}
function bandOf(q) { return fcBand === 'gauss' || !q[fcBand] ? { lo: q.lo, hi: q.hi } : q[fcBand]; }
async function loadForecasts() {
  const tb = document.getElementById('fc-table');
  tb.innerHTML = '<tr><td><div class="loading"><div class="spinner"></div>Building forecasts from 10 years of data (first load ~20s)…</div></td></tr>';
  try {
    const d = _fcData[curFcMkt] || await getJSON('/api/forecast-table?mkt=' + curFcMkt);
    if (!d.groups || !d.groups.some(g => g.rows.length)) throw 0;
    _fcData[curFcMkt] = d;
    renderFcTable(d);
    selectFc(d.groups.findIndex(g => g.rows.length), 0);
  } catch { tb.innerHTML = '<tr><td><div class="empty-note">Forecast data unavailable right now. Check your connection and refresh.</div></td></tr>'; }
}
function renderFcTable(d) {
  const sigTxt = { up: '▲', down: '▼', flat: '●' }, sigTitle = { up: 'Above SMA50 & SMA200', down: 'Below SMA50 & SMA200', flat: 'Mixed vs SMA50/200' };
  let html = `<tr><th>Name</th><th>Price</th><th>Signal</th><th>Ann. vol</th>${d.quarters.map(q => `<th>${q}</th>`).join('')}</tr>`;
  d.groups.forEach((g, gi) => {
    if (!g.rows.length) return;
    html += `<tr class="fc-grp"><td colspan="${4 + d.quarters.length}">${g.group} · ${BAND_NAME[fcBand]} 80% band</td></tr>`;
    g.rows.forEach((r, ri) => {
      html += `<tr class="fc-row ${_fcIdx[0] === gi && _fcIdx[1] === ri ? 'active' : ''}" id="fcr-${gi}-${ri}" onclick="selectFc(${gi},${ri})">
        <td>${r.name}</td><td>${nf(r.price, pd(r.price))}</td>
        <td><span class="fc-sig ${r.signal}" title="${sigTitle[r.signal]}">${sigTxt[r.signal]}</span></td><td>${r.annVol.toFixed(1)}%</td>
        ${r.quarters.map(q => { const ch = (q.mid / r.price - 1) * 100, b = bandOf(q); return `<td>${nf(q.mid, pd(q.mid))}<small>${nf(b.lo, pd(b.lo))} – ${nf(b.hi, pd(b.hi))} <span class="${ch >= 0 ? 'pos' : 'neg'}">${fmtPct(ch)}</span></small></td>`; }).join('')}</tr>`;
    });
  });
  document.getElementById('fc-table').innerHTML = html;
}
async function selectFc(gi, ri) {
  const d = _fcData[curFcMkt]; if (!d || !d.groups[gi] || !d.groups[gi].rows[ri]) return;
  const r = d.groups[gi].rows[ri]; _fcSel = r; _fcIdx = [gi, ri];
  document.querySelectorAll('.fc-row').forEach(x => x.classList.remove('active'));
  const tr = document.getElementById(`fcr-${gi}-${ri}`); if (tr) tr.classList.add('active');
  document.getElementById('fc-title').textContent = r.name;
  const last = r.quarters[r.quarters.length - 1], cov0 = r.quarters[0].coverage;
  document.getElementById('fc-sub').textContent = `${r.symbol} · last ${nf(r.price, pd(r.price))} · trend drift ${fmtPct(r.annDrift)}/yr · vol ${r.annVol.toFixed(1)}%/yr${cov0 ? ' · regime now: ' + cov0.regime_now : ''}`;
  const st = (l, v, c = '') => `<div class="fc-stat"><div class="l">${l}</div><div class="v ${c}">${v}</div></div>`;
  const ch = (last.mid / r.price - 1) * 100, b = bandOf(last);
  document.getElementById('fc-stats').innerHTML = st(`Median ${last.q}`, nf(last.mid, pd(last.mid)), ch >= 0 ? 'pos' : 'neg') +
    st(`${BAND_NAME[fcBand]} 80%`, `${nf(b.lo, pd(b.lo))} – ${nf(b.hi, pd(b.hi))}`) +
    st('Signal', { up: '▲ Uptrend', down: '▼ Downtrend', flat: '● Mixed' }[r.signal], r.signal === 'up' ? 'pos' : r.signal === 'down' ? 'neg' : '') +
    st('Annual vol', r.annVol.toFixed(1) + '%');
  const covCell = v => { if (v == null) return '—'; const c = Math.abs(v - 0.8) <= 0.05 ? 'pos' : Math.abs(v - 0.8) <= 0.12 ? '' : 'neg'; return `<span class="${c}">${(v * 100).toFixed(0)}%</span>`; };
  const hasCov = r.quarters.some(q => q.coverage);
  document.getElementById('fc-cov').innerHTML = hasCov ? `<div class="sec-lbl">Coverage check · how often the 80% band held on unseen data</div>
    <table class="tbl"><tr><th>Horizon</th><th>Trading days</th><th>Gaussian</th><th>Conformal</th><th>Regime conformal</th><th title="test windows divided by horizon; overlapping windows are not independent">Independent windows</th></tr>` +
    r.quarters.map(q => q.coverage ? `<tr><td>${q.q}</td><td>${q.tdays}</td><td>${covCell(q.coverage.gauss)}</td><td>${covCell(q.coverage.conf)}</td><td>${covCell(q.coverage.rc)}</td><td>${q.coverage.n_eff}${q.coverage.n_eff < 10 ? ' <span class="note">(noisy)</span>' : ''}</td></tr>` : `<tr><td>${q.q}</td><td>${q.tdays}</td><td colspan="4" class="note">not enough history</td></tr>`).join('') +
    `</table><div class="note" style="margin-top:6px">Calibrated on the first 60% of forecast dates, tested on the last 40%. Closer to 80% is better. Long horizons have few independent windows, so treat those numbers loosely.</div>` : '';
  try {
    const h = await getJSON(`/api/stock/${encodeURIComponent(r.symbol)}?period=1y`);
    if (_fcSel !== r || !h.length) return;
    drawFan(h, r);
  } catch { }
}
function drawFan(hist, r) {
  const svg = document.getElementById('fc-svg');
  const W = (svg.parentElement.offsetWidth || 830) - 30, H = 300, pl = { t: 16, b: 26, l: 10, r: 64 };
  const closes = hist.map(x => x.close), N = closes.length;
  const mu = r.annDrift / 100 / 252, sd = r.annVol / 100 / Math.sqrt(252), p = r.price;
  const qs = r.quarters, Hd = qs[qs.length - 1].tdays;
  const Qat = k => {   // band multiplier at horizon k, interpolated between quarter ends
    const pts = qs.map(q => [q.tdays, fcBand === 'gauss' ? 1.2816 : (q.Q && q.Q[fcBand]) || 1.2816]);
    if (k <= pts[0][0]) return pts[0][1];
    for (let i = 1; i < pts.length; i++) if (k <= pts[i][0]) { const [a, qa] = pts[i - 1], [b, qb] = pts[i]; return qa + (qb - qa) * (k - a) / (b - a); }
    return pts[pts.length - 1][1];
  };
  const ks = [...Array(Hd + 1).keys()];
  const mid = ks.map(k => p * Math.exp(mu * k));
  const lo80 = ks.map(k => p * Math.exp(mu * k - Qat(k) * sd * Math.sqrt(k))), hi80 = ks.map(k => p * Math.exp(mu * k + Qat(k) * sd * Math.sqrt(k)));
  const show50 = fcBand === 'gauss';
  const lo50 = ks.map(k => p * Math.exp(mu * k - 0.6745 * sd * Math.sqrt(k))), hi50 = ks.map(k => p * Math.exp(mu * k + 0.6745 * sd * Math.sqrt(k)));
  const mn = Math.min(...closes, ...lo80), mx = Math.max(...closes, ...hi80);
  const T = N - 1 + Hd, pw = W - pl.l - pl.r, ph = H - pl.t - pl.b;
  const xs = i => pl.l + (i / T) * pw, ys = v => pl.t + ph - ((v - mn) / (mx - mn || 1)) * ph;
  const poly = (a, b) => a.map((v, k) => `${xs(N - 1 + k)},${ys(v)}`).join(' ') + ' ' + b.map((v, k) => `${xs(N - 1 + k)},${ys(v)}`).reverse().join(' ');
  let grid = ''; for (let k = 0; k <= 4; k++) { const v = mn + k / 4 * (mx - mn), y = ys(v); grid += `<line x1="${pl.l}" y1="${y}" x2="${W - pl.r}" y2="${y}" stroke="var(--border)" stroke-width=".35"/><text x="${W - pl.r + 4}" y="${y + 3}" fill="var(--muted)" font-size="8.5" font-family="IBM Plex Mono">${nf(v, pd(v))}</text>`; }
  let qm = ''; qs.forEach(q => {
    const x = xs(N - 1 + q.tdays);
    qm += `<line x1="${x}" y1="${pl.t}" x2="${x}" y2="${H - pl.b}" stroke="var(--border2)" stroke-width=".6" stroke-dasharray="2 3"/><circle cx="${x}" cy="${ys(q.mid)}" r="3" fill="var(--gold)"/><text x="${x}" y="${H - 8}" fill="var(--gold)" font-size="8.5" text-anchor="middle" font-family="IBM Plex Mono">${q.q}</text>`;
  });
  const xl = [0, Math.round((N - 1) / 2), N - 1].map(i => `<text x="${xs(i)}" y="${H - 8}" fill="var(--muted)" font-size="8.5" text-anchor="${i === 0 ? 'start' : 'middle'}" font-family="IBM Plex Mono">${hist[i].date.slice(0, 7)}</text>`).join('');
  const nowX = xs(N - 1), col = fcBand === 'gauss' ? '79,163,255' : fcBand === 'conf' ? '167,139,250' : '0,208,132';
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`); svg.setAttribute('height', H);
  svg.innerHTML = `${grid}
    <polygon points="${poly(hi80, lo80)}" fill="rgba(${col},.12)"/>
    ${show50 ? `<polygon points="${poly(hi50, lo50)}" fill="rgba(${col},.18)"/>` : ''}
    <polyline points="${closes.map((v, i) => `${xs(i)},${ys(v)}`).join(' ')}" fill="none" stroke="var(--cyan)" stroke-width="1.7" stroke-linejoin="round"/>
    <polyline points="${mid.map((v, k) => `${xs(N - 1 + k)},${ys(v)}`).join(' ')}" fill="none" stroke="var(--gold)" stroke-width="1.4" stroke-dasharray="5 3"/>
    <line x1="${nowX}" y1="${pl.t}" x2="${nowX}" y2="${H - pl.b}" stroke="var(--blue)" stroke-width=".8"/>
    <text x="${nowX + 4}" y="${pl.t + 8}" fill="var(--blue)" font-size="8.5" font-family="IBM Plex Mono">today</text>${qm}${xl}
    <text x="${pl.l + 4}" y="${pl.t + 8}" fill="var(--muted)" font-size="8" font-family="IBM Plex Mono">${BAND_NAME[fcBand]} 80% band${show50 ? ' (inner: 50%)' : ''}</text>`;
}

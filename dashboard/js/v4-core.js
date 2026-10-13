/* Kairos v4 core: helpers, market clock, Ctrl+K palette, toasts, alerts polling,
   screener, and the explorer price chart (candles, Bollinger, VWAP, MACD, compare). */

/* ══════════════════════════════════════ HELPERS */
const FLAG = m => `<span class="fl fl-${m === 'india' ? 'in' : 'us'}"></span>`;
const mktOf = s => /\.(NS|BO)$/.test(s || '') || /^\^(NSE|BSE|INDIA)/.test(s || '') ? 'india' : 'usa';
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const pct = (v, d = 1) => v == null || !isFinite(v) ? '—' : (v >= 0 ? '+' : '') + (v * 100).toFixed(d) + '%';
const cls = v => v == null ? '' : v >= 0 ? 'pos' : 'neg';
function nfs(v) {
  if (v == null || !isFinite(v)) return '—';
  const a = Math.abs(v);
  if (a >= 1e9) return (v / 1e9).toFixed(2) + 'B';
  if (a >= 1e6) return (v / 1e6).toFixed(2) + 'M';
  if (a >= 1e4) return (v / 1e3).toFixed(1) + 'k';
  if (a >= 100) return v.toFixed(0);
  if (a >= 1) return v.toFixed(2);
  return v.toFixed(3);
}
function fmtCap(v, mkt) {
  if (v == null) return '—';
  if (mkt === 'india') return '₹' + (v / 1e7).toLocaleString('en-IN', { maximumFractionDigits: 0 }) + ' Cr';
  return '$' + (v >= 1e12 ? (v / 1e12).toFixed(2) + 'T' : (v / 1e9).toFixed(1) + 'B');
}
function money(v, mkt, d = 0) {
  if (v == null || !isFinite(v)) return '—';
  if (Math.abs(v) < 0.5 * Math.pow(10, -d)) v = 0;
  const c = mkt === 'india' ? '₹' : '$';
  const s = Math.abs(v).toLocaleString(mkt === 'india' ? 'en-IN' : 'en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
  return (v < 0 ? '-' : '') + c + s;
}
function toast(title, msg = '', kind = '') {
  const el = document.createElement('div');
  el.className = 'toast ' + kind;
  el.innerHTML = `<b>${title}</b>${msg}`;
  document.getElementById('toasts').appendChild(el);
  setTimeout(() => el.remove(), 5500);
}
async function postJSON(u, body) {
  const r = await fetch(u, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) });
  return r.json();
}
async function delJSON(u) { return (await fetch(u, { method: 'DELETE' })).json(); }
function busy(btn, on, label) {
  if (!btn) return;
  if (on) { btn.dataset.lbl = btn.innerHTML; btn.innerHTML = label || 'Working…'; btn.disabled = true; }
  else { btn.innerHTML = btn.dataset.lbl || btn.innerHTML; btn.disabled = false; }
}

let SEARCH_IDX = [];
async function loadSearchIndex() {
  try {
    SEARCH_IDX = await getJSON('/api/search-index');
    document.getElementById('sym-all').innerHTML =
      SEARCH_IDX.map(x => `<option value="${x.symbol}">${x.mkt === 'india' ? 'NSE' : 'US'} · ${esc(x.sector)}</option>`).join('');
  } catch { }
}
/** "reliance" -> "RELIANCE.NS", "aapl" -> "AAPL" */
function normSym(v) {
  const s = String(v || '').trim().toUpperCase();
  if (!s) return '';
  if (SEARCH_IDX.some(x => x.symbol === s)) return s;
  if (SEARCH_IDX.some(x => x.symbol === s + '.NS')) return s + '.NS';
  return s;
}
function openSymbol(sym) {
  const m = mktOf(sym);
  if (m !== MARKET) { window._pendingSym = sym; setMarket(m); goTab('explorer'); }
  else { goTab('explorer'); selectStock(sym); }
}

/** Generic SVG line plotter. series: [{vals, color, w, dash, area, areaBase}] */
function plot(svg, series, o = {}) {
  const W = (svg.parentElement.offsetWidth || 800), H = o.H || 220;
  const pl = { t: 10, b: o.dates ? 22 : 8, l: 8, r: o.yAxis === false ? 8 : 56 };
  const N = Math.max(...series.map(s => s.vals.length));
  let mn = Infinity, mx = -Infinity;
  series.forEach(s => s.vals.forEach(v => { if (v != null && isFinite(v)) { if (v < mn) mn = v; if (v > mx) mx = v; } }));
  if (o.min != null) mn = Math.min(mn, o.min);
  if (o.max != null) mx = Math.max(mx, o.max);
  if (!isFinite(mn)) { mn = 0; mx = 1; }
  if (mn === mx) { mn -= 1; mx += 1; }
  const pw = W - pl.l - pl.r, ph = H - pl.t - pl.b;
  const xs = i => pl.l + (i / ((N - 1) || 1)) * pw;
  const ys = v => pl.t + ph - ((v - mn) / (mx - mn)) * ph;
  const yf = o.yfmt || nfs;
  let g = '';
  for (let k = 0; k <= 3; k++) {
    const v = mn + k / 3 * (mx - mn), y = ys(v);
    g += `<line x1="${pl.l}" y1="${y}" x2="${W - pl.r}" y2="${y}" stroke="var(--border)" stroke-width=".35"/>`;
    if (o.yAxis !== false) g += `<text x="${W - pl.r + 4}" y="${y + 3}" fill="var(--muted)" font-size="8.5" font-family="IBM Plex Mono">${yf(v)}</text>`;
  }
  if (o.split != null && o.split < N) {
    const x = xs(o.split);
    g += `<rect x="${x}" y="${pl.t}" width="${W - pl.r - x}" height="${ph}" fill="rgba(251,191,36,.05)"/>
      <line x1="${x}" y1="${pl.t}" x2="${x}" y2="${H - pl.b}" stroke="var(--gold)" stroke-width=".8" stroke-dasharray="4 3"/>
      <text x="${x + 4}" y="${pl.t + 9}" fill="var(--gold)" font-size="8" font-family="IBM Plex Mono">out-of-sample →</text>`;
  }
  if (o.hlines) o.hlines.forEach(h => {
    if (h.v < mn || h.v > mx) return;
    g += `<line x1="${pl.l}" y1="${ys(h.v)}" x2="${W - pl.r}" y2="${ys(h.v)}" stroke="${h.color || 'var(--border2)'}" stroke-width="${h.w || .7}" stroke-dasharray="${h.dash || '3 3'}"/>`;
    if (h.label) g += `<text x="${pl.l + 3}" y="${ys(h.v) - 3}" fill="${h.color || 'var(--muted)'}" font-size="8" font-family="IBM Plex Mono">${h.label}</text>`;
  });
  if (o.pre) g += o.pre({ xs, ys, W, H, pl, mn, mx });
  series.forEach(s => {
    const segs = []; let cur = [];
    s.vals.forEach((v, i) => {
      if (v == null || !isFinite(v)) { if (cur.length) { segs.push(cur); cur = []; } }
      else cur.push([xs(i), ys(v)]);
    });
    if (cur.length) segs.push(cur);
    segs.forEach(sg => {
      const pts = sg.map(p => p.join(',')).join(' ');
      if (s.area) {
        const b = ys(s.areaBase != null ? Math.max(mn, Math.min(mx, s.areaBase)) : mn);
        g += `<polygon points="${pts} ${sg[sg.length - 1][0]},${b} ${sg[0][0]},${b}" fill="${s.area}"/>`;
      }
      g += `<polyline points="${pts}" fill="none" stroke="${s.color}" stroke-width="${s.w || 1.6}" stroke-dasharray="${s.dash || ''}" stroke-linejoin="round"/>`;
    });
  });
  if (o.dates && o.dates.length > 1) {
    const D = o.dates;
    for (let k = 0; k < 6; k++) {
      const i = Math.round(k * (D.length - 1) / 5);
      g += `<text x="${xs(i)}" y="${H - 6}" fill="var(--muted)" font-size="8.5" text-anchor="${k === 0 ? 'start' : k === 5 ? 'end' : 'middle'}" font-family="IBM Plex Mono">${D[i].slice(0, 7)}</text>`;
    }
  }
  if (o.extra) g += o.extra({ xs, ys, W, H, pl, mn, mx });
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.setAttribute('height', H);
  svg.innerHTML = g;
  return { xs, ys, W, H, pl };
}

/* ══════════════════════════════════════ MARKET CLOCK */
function tzNow(tz) {
  const f = new Intl.DateTimeFormat('en-US', { timeZone: tz, weekday: 'short', hour: '2-digit', minute: '2-digit', hour12: false });
  const p = Object.fromEntries(f.formatToParts(new Date()).map(x => [x.type, x.value]));
  return { wd: p.weekday, mins: (parseInt(p.hour) % 24) * 60 + parseInt(p.minute) };
}
function dur(m) {
  const d = Math.floor(m / 1440), h = Math.floor((m % 1440) / 60), mm = m % 60;
  return d ? `${d}d ${h}h` : h ? `${h}h ${mm}m` : `${mm}m`;
}
function mktState(tz, open, close, pre) {
  const { wd, mins } = tzNow(tz);
  const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  const wk = !['Sat', 'Sun'].includes(wd);
  if (wk && mins >= open && mins < close) return { c: 'open', t: `open · closes in ${dur(close - mins)}` };
  if (wk && mins >= pre && mins < open) return { c: 'pre', t: `pre-market · opens in ${dur(open - mins)}` };
  let to;
  if (wk && mins < pre) to = open - mins;
  else {
    let d = 1, di = days.indexOf(wd);
    while (['Sat', 'Sun'].includes(days[(di + d) % 7])) d++;
    to = (1440 - mins) + (d - 1) * 1440 + open;
  }
  return { c: '', t: `closed · opens in ${dur(to)}` };
}
function renderClock() {
  const el = document.getElementById('mclock'); if (!el) return;
  const n = mktState('Asia/Kolkata', 555, 930, 540), u = mktState('America/New_York', 570, 960, 240);
  el.innerHTML = `<div class="mc-pill" title="NSE 9:15–15:30 IST. Exchange holidays are not included."><span class="mc-dot ${n.c}"></span><b>NSE</b>${n.t}</div>
    <div class="mc-pill" title="NYSE 9:30–16:00 ET. Exchange holidays are not included."><span class="mc-dot ${u.c}"></span><b>NYSE</b>${u.t}</div>`;
}

/* ══════════════════════════════════════ COMMAND PALETTE (Ctrl+K) */
const TABS = [['markets', 'Markets'], ['leaderboard', 'Leaderboard'], ['lab', 'Strategy Lab'], ['explorer', 'Stock Explorer'],
  ['screener', 'Screener'], ['forecasts', 'Forecasts'], ['pairs', 'Pairs Analysis'], ['heatmap', 'Sector Heatmap'],
  ['portfolio', 'Portfolio Builder'], ['paper', 'Paper Trading'], ['comparator', 'Strategy Comparator']];
let _palItems = [], _palSel = 0;
function palOpen() {
  document.getElementById('pal-ov').classList.add('open');
  const i = document.getElementById('pal-input'); i.value = ''; palFilter('');
  setTimeout(() => i.focus(), 20);
}
function palClose() { document.getElementById('pal-ov').classList.remove('open'); }
function palFilter(q) {
  q = q.trim().toLowerCase();
  const items = [];
  TABS.forEach(([id, name]) => items.push({ k: 'TAB', l: name, s: 'go to tab', run: () => goTab(id) }));
  items.push({ k: 'ACTION', l: 'Switch to India market', s: 'NSE', run: () => setMarket('india') });
  items.push({ k: 'ACTION', l: 'Switch to US market', s: 'NYSE / NASDAQ', run: () => setMarket('usa') });
  items.push({ k: 'ACTION', l: 'Run C++ engine benchmark', s: 'Strategy Lab', run: () => { goTab('lab'); labBench(); } });
  items.push({ k: 'ACTION', l: 'Export trades CSV', s: 'download', run: () => { location.href = '/api/export/trades'; } });
  const stocks = SEARCH_IDX.map(x => ({ k: 'STOCK', l: shortSym(x.symbol), sym: x.symbol, s: `${x.mkt === 'india' ? 'NSE' : 'US'} · ${x.sector}`, run: () => openSymbol(x.symbol) }));
  let list;
  if (!q) list = items.concat(stocks.slice(0, 6));
  else {
    const score = it => { const L = it.l.toLowerCase(); return L === q ? 0 : L.startsWith(q) ? 1 : L.includes(q) ? 2 : (it.s || '').toLowerCase().includes(q) ? 3 : 9; };
    list = items.concat(stocks).map(it => [score(it), it]).filter(x => x[0] < 9).sort((a, b) => a[0] - b[0]).map(x => x[1]).slice(0, 14);
    const top = list.find(x => x.k === 'STOCK');
    if (top && list.indexOf(top) < 2) {
      list.splice(list.indexOf(top) + 1, 0,
        { k: 'LAB', l: `Backtest ${top.l}`, s: 'Strategy Lab', run: () => { goTab('lab'); labSetSymbol(top.sym); labRun(); } },
        { k: 'TRADE', l: `Paper trade ${top.l}`, s: 'Paper Trading', run: () => tradeQuick(top.sym) });
    }
  }
  _palItems = list; _palSel = 0; palRender();
}
function palRender() {
  document.getElementById('pal-list').innerHTML = _palItems.map((it, i) =>
    `<div class="pal-item ${i === _palSel ? 'sel' : ''}" onmouseenter="_palSel=${i};palRender()" onclick="palRun(${i})">
      <span class="pi-kind">${it.k}</span><span>${esc(it.l)}</span><span class="pi-sub">${esc(it.s || '')}</span></div>`).join('')
    || '<div class="note" style="padding:12px">No matches</div>';
}
function palRun(i) { const it = _palItems[i]; palClose(); if (it) it.run(); }
document.addEventListener('keydown', e => {
  const ov = document.getElementById('pal-ov');
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); ov.classList.contains('open') ? palClose() : palOpen(); return; }
  if (e.key === 'Escape') { palClose(); closeModalBtn(); document.querySelectorAll('.mini-pop').forEach(p => p.remove()); return; }
  if (!ov.classList.contains('open')) return;
  if (e.key === 'ArrowDown') { e.preventDefault(); _palSel = Math.min(_palItems.length - 1, _palSel + 1); palRender(); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); _palSel = Math.max(0, _palSel - 1); palRender(); }
  else if (e.key === 'Enter') { e.preventDefault(); palRun(_palSel); }
});

/* ══════════════════════════════════════ ALERT POLLING */
async function alertPoll() {
  try {
    const fired = await getJSON('/api/alerts/check');
    fired.forEach(a => {
      const msg = `${shortSym(a.symbol)} is ${a.cond} ${nf(a.price)} (now ${nf(a.trig_price)})`;
      toast('🔔 Price alert', msg, 'warn');
      if (window.Notification && Notification.permission === 'granted') new Notification('Kairos price alert', { body: msg });
    });
    if (fired.length && typeof alLoad === 'function') alLoad();
  } catch { }
}

function initV4() {
  loadSearchIndex();
  renderClock(); setInterval(renderClock, 30000);
  if (typeof wlLoad === 'function') wlLoad();
  alertPoll(); setInterval(alertPoll, 60000);
  renderCmpRow();
}

/* ══════════════════════════════════════ SCREENER */
let SCR = [], _scrMkt = null, scrSort = { k: 'mcap', d: -1 }, scrP = 'all';
const SCR_COLS = [['symbol', 'Symbol'], ['name', 'Name'], ['sector', 'Sector'], ['price', 'Price'], ['chg1d', '1D'], ['chg1m', '1M'],
  ['chg3m', '3M'], ['chg1y', '1Y'], ['rsi', 'RSI'], ['from_high', 'From 52W H'], ['above_sma200', 'Trend'], ['vol', 'Vol'], ['pe', 'P/E'], ['mcap', 'Mkt cap']];
async function loadScreener(force) {
  if (!force && _scrMkt === MARKET && SCR.length) return;
  _scrMkt = MARKET;
  document.getElementById('scr-table').innerHTML = '<tr><td><div class="loading"><div class="spinner"></div>Scanning 60 stocks (first load takes ~20s)…</div></td></tr>';
  try {
    SCR = await getJSON('/api/screener?mkt=' + MARKET);
    const secs = [...new Set(SCR.map(r => r.sector).filter(Boolean))].sort();
    document.getElementById('scr-sector').innerHTML = '<option value="">All sectors</option>' + secs.map(s => `<option>${esc(s)}</option>`).join('');
    scrRender();
  } catch { document.getElementById('scr-table').innerHTML = '<tr><td class="note">Screener unavailable</td></tr>'; }
}
const SCR_PRESETS = {
  all: ['All', () => true], oversold: ['Oversold (RSI<30)', r => r.rsi < 30], overbought: ['Overbought (RSI>70)', r => r.rsi > 70],
  highs: ['Near 52W high', r => r.from_high > -5], lows: ['Near 52W low', r => r.from_low < 5],
  trend: ['Above 50 & 200 DMA', r => r.above_sma50 && r.above_sma200], value: ['Value (P/E<15)', r => r.pe != null && r.pe > 0 && r.pe < 15],
  momentum: ['Momentum (3M>10%)', r => (r.chg3m || 0) > 10],
};
function scrPreset(k, el) {
  scrP = k;
  document.querySelectorAll('#scr-presets .chip').forEach(c => c.classList.remove('active'));
  el.classList.add('active'); scrRender();
}
/** Every active filter as {label, fn}, so an empty result can say which one is the blocker. */
function scrFilters() {
  const v = id => { const x = document.getElementById(id).value.trim(); return x === '' || isNaN(parseFloat(x)) ? null : parseFloat(x); };
  const f = [];
  if (scrP !== 'all') f.push({ label: SCR_PRESETS[scrP][0], fn: SCR_PRESETS[scrP][1] });
  const sec = document.getElementById('scr-sector').value;
  if (sec) f.push({ label: `Sector: ${sec}`, fn: r => r.sector === sec });
  const rmin = v('scr-rsi-min'), rmax = v('scr-rsi-max'), pe = v('scr-pe-max'), m1 = v('scr-1m-min'), hi = v('scr-high');
  if (rmin != null) f.push({ label: `RSI ≥ ${rmin}`, fn: r => r.rsi >= rmin });
  if (rmax != null) f.push({ label: `RSI ≤ ${rmax}`, fn: r => r.rsi <= rmax });
  if (pe != null) f.push({ label: `P/E ≤ ${pe}`, fn: r => r.pe != null && r.pe > 0 && r.pe <= pe });
  if (m1 != null) f.push({ label: `1M change ≥ ${m1}%`, fn: r => (r.chg1m ?? -1e9) >= m1 });
  if (hi != null) { const h = Math.abs(hi); f.push({ label: `Within ${h}% of 52W high`, fn: r => -r.from_high <= h }); }
  const q = document.getElementById('scr-q').value.trim().toLowerCase();
  if (q) f.push({ label: `Search "${q}"`, fn: r => r.symbol.toLowerCase().includes(q) || (r.name || '').toLowerCase().includes(q) });
  return f;
}
function scrPass(r) { return scrFilters().every(x => x.fn(r)); }
function scrReset() {
  ['scr-rsi-min', 'scr-rsi-max', 'scr-pe-max', 'scr-1m-min', 'scr-high', 'scr-q'].forEach(id => { document.getElementById(id).value = ''; });
  document.getElementById('scr-sector').value = '';
  scrP = 'all';
  document.querySelectorAll('#scr-presets .chip').forEach((c, i) => c.classList.toggle('active', i === 0));
  scrRender();
}
function scrEmptyHelp() {
  const f = scrFilters();
  if (!f.length) return 'No data for this market yet.';
  const alone = f.map(x => ({ label: x.label, n: SCR.filter(x.fn).length }));
  const zero = alone.filter(x => x.n === 0);
  let msg = '<b>No stocks match all ' + f.length + ' filters together.</b> ';
  if (zero.length) msg += 'These match nothing even on their own: ' + zero.map(x => `<b>${esc(x.label)}</b>`).join(', ') + '. ';
  msg += 'On its own, each filter keeps: ' + alone.map(x => `${esc(x.label)} → ${x.n}`).join(' · ') + '.';
  return msg + ` <a href="#" class="ext-link" onclick="scrReset();return false">Reset filters</a>`;
}
function scrSortBy(k) { scrSort = { k, d: scrSort.k === k ? -scrSort.d : -1 }; scrRender(); }
function scrRows() {
  const k = scrSort.k, d = scrSort.d;
  return SCR.filter(scrPass).sort((a, b) => {
    const x = a[k], y = b[k];
    if (x == null) return 1; if (y == null) return -1;
    return (typeof x === 'string' ? x.localeCompare(y) : x - y) * d;
  });
}
function scrRender() {
  const rows = scrRows();
  const nf_ = scrFilters().length;
  document.getElementById('scr-count').innerHTML = `${rows.length} of ${SCR.length} stocks` + (nf_ ? ` · ${nf_} filter${nf_ > 1 ? 's' : ''} · <a href="#" class="ext-link" onclick="scrReset();return false">reset</a>` : '');
  const pc = v => v == null ? '—' : `<span class="${cls(v)}">${v >= 0 ? '+' : ''}${v.toFixed(1)}%</span>`;
  const head = '<tr>' + SCR_COLS.map(([k, l]) => `<th class="sortable ${scrSort.k === k ? 'sorted' : ''} ${k === 'name' || k === 'sector' ? 'l' : ''}" onclick="scrSortBy('${k}')">${l}${scrSort.k === k ? (scrSort.d > 0 ? ' ▲' : ' ▼') : ''}</th>`).join('') + '</tr>';
  const body = rows.map(r => `<tr class="click" onclick="openSymbol('${r.symbol}')">
    <td><b>${shortSym(r.symbol)}</b></td><td class="l" style="font-family:var(--sans);color:var(--muted);max-width:170px;overflow:hidden;text-overflow:ellipsis">${esc(r.name || '')}</td>
    <td class="l" style="font-family:var(--sans)">${esc(r.sector)}</td><td>${CUR(r.symbol)}${nf(r.price)}</td>
    <td>${pc(r.chg1d)}</td><td>${pc(r.chg1m)}</td><td>${pc(r.chg3m)}</td><td>${pc(r.chg1y)}</td>
    <td class="${r.rsi < 30 ? 'pos' : r.rsi > 70 ? 'neg' : ''}">${r.rsi.toFixed(0)}<span class="rsi-bar"><i style="left:${Math.max(0, Math.min(100, r.rsi))}%"></i></span></td>
    <td>${r.from_high.toFixed(1)}%</td>
    <td>${r.above_sma200 == null ? '—' : r.above_sma50 && r.above_sma200 ? '<span class="pill g">UP</span>' : !r.above_sma50 && !r.above_sma200 ? '<span class="pill r">DOWN</span>' : '<span class="pill" style="color:var(--gold)">MIXED</span>'}</td>
    <td>${r.vol.toFixed(0)}%</td><td>${r.pe != null ? r.pe.toFixed(1) : '—'}</td><td>${fmtCap(r.mcap, mktOf(r.symbol))}</td></tr>`).join('');
  document.getElementById('scr-table').innerHTML = head + (body || `<tr><td colspan="${SCR_COLS.length}" class="l note" style="white-space:normal;line-height:1.7;padding:14px 10px">${scrEmptyHelp()}</td></tr>`);
}
function scrExport() {
  const rows = scrRows(); if (!rows.length) return;
  const keys = ['symbol', 'name', 'sector', 'price', 'chg1d', 'chg1m', 'chg3m', 'chg1y', 'rsi', 'from_high', 'above_sma50', 'above_sma200', 'vol', 'pe', 'mcap'];
  const csv = [keys.join(',')].concat(rows.map(r => keys.map(k => { const v = r[k]; return typeof v === 'string' ? `"${v.replace(/"/g, '""')}"` : v ?? ''; }).join(','))).join('\n');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
  a.download = `screener_${MARKET}_${new Date().toISOString().slice(0, 10)}.csv`; a.click();
}

/* ══════════════════════════════════════ EXPLORER: chart modes, indicators, compare */
let chartMode = 'line', lowerPanel = 'rsi', compareSyms = [], _cmpCache = {};
const CMP_COLORS = ['#fb923c', '#a78bfa', '#22d3ee', '#fbbf24'];
function redrawStock() { if (window._lastPriceData) drawStockChart(window._lastPriceData); }
function toggleCandle() {
  chartMode = chartMode === 'line' ? 'candle' : 'line';
  document.getElementById('obtn-candle').classList.toggle('on', chartMode === 'candle'); redrawStock();
}
function setLower(v) { lowerPanel = v; redrawStock(); }
async function loadCompareData() {
  await Promise.all(compareSyms.map(async s => {
    const k = s + '|' + curPer;
    if (!_cmpCache[k]) { try { _cmpCache[k] = await getJSON(`/api/stock/${encodeURIComponent(s)}?period=${curPer}`); } catch { _cmpCache[k] = []; } }
  }));
}
async function cmpAdd(v) {
  const s = normSym(v);
  if (!s || s === curSym || compareSyms.includes(s)) return;
  if (compareSyms.length >= 4) { toast('Compare', 'Up to 4 extra symbols', 'warn'); return; }
  compareSyms.push(s); renderCmpRow(); await loadCompareData(); redrawStock();
}
function cmpRemove(s) { compareSyms = compareSyms.filter(x => x !== s); renderCmpRow(); redrawStock(); }
function renderCmpRow() {
  const el = document.getElementById('cmp-row'); if (!el) return;
  el.innerHTML = compareSyms.map((s, i) => `<span class="cmp-chip"><i style="background:${CMP_COLORS[i]}"></i>${shortSym(s)}<button onclick="cmpRemove('${s}')">✕</button></span>`).join('') +
    `<input class="cmp-input" list="sym-all" placeholder="+ compare with…" onkeydown="if(event.key==='Enter'){cmpAdd(this.value);this.value='';}" onchange="cmpAdd(this.value);this.value='';">`;
}
function onStockSelected(sym) {
  const b = document.getElementById('watch-btn');
  if (b) { const on = (typeof WATCH !== 'undefined') && WATCH.has(sym); b.classList.toggle('on', on); b.textContent = on ? '★ Watching' : '☆ Watch'; }
}
function bollinger(c, n = 20, k = 2) {
  const m = sma(c, n), up = [], lo = [];
  for (let i = 0; i < c.length; i++) {
    if (m[i] == null) { up.push(null); lo.push(null); continue; }
    let s = 0; for (let j = i - n + 1; j <= i; j++) s += (c[j] - m[i]) ** 2;
    const sd = Math.sqrt(s / n); up.push(m[i] + k * sd); lo.push(m[i] - k * sd);
  }
  return { up, lo };
}
function vwapAnchored(d) {
  let pv = 0, vv = 0;
  return d.map(x => { const tp = (x.high + x.low + x.close) / 3; pv += tp * (x.volume || 0); vv += (x.volume || 0); return vv ? pv / vv : null; });
}
function emaJS(a, n) { const k = 2 / (n + 1), o = []; for (let i = 0; i < a.length; i++) o.push(i ? a[i] * k + o[i - 1] * (1 - k) : a[i]); return o; }

function drawStockChart(data) {
  if (!data.length) return;
  const closes = data.map(d => d.close), vols = data.map(d => d.volume), dates = data.map(d => d.date);
  const N = closes.length, long = curPer === '5y' || curPer === 'max';
  const psvg = document.getElementById('price-svg');
  const W = psvg.parentElement.offsetWidth || 800, H = 250, pl = { t: 10, b: 24, l: 10, r: 10 };
  const pw = W - pl.l - pl.r, ph = H - pl.t - pl.b;
  const cmpOn = compareSyms.length > 0;
  const cone = !cmpOn && overlays.fcst && N >= 40 ? coneFrom(closes) : null;
  const F = cone ? cone.H : 0;
  const xs = i => pl.l + (i / ((N - 1 + F) || 1)) * pw;
  let body = '', grid = '', mn, mx, ys;
  const gridLines = fmtY => { let g = ''; for (let k = 0; k <= 3; k++) { const v = mn + (k / 3) * (mx - mn), y = ys(v); g += `<line x1="${pl.l}" y1="${y}" x2="${W - pl.r}" y2="${y}" stroke="var(--border)" stroke-width=".35"/><text x="${W - pl.r - 2}" y="${y - 2}" fill="var(--muted)" font-size="8" text-anchor="end" font-family="IBM Plex Mono">${fmtY(v)}</text>`; } return g; };

  if (cmpOn) {
    const series = [{ sym: curSym, color: 'var(--blue)', vals: closes.map(v => (v / closes[0] - 1) * 100) }];
    compareSyms.forEach((s, k) => {
      const m = new Map((_cmpCache[s + '|' + curPer] || []).map(x => [x.date, x.close]));
      let base = null, last = null;
      const vals = dates.map(dt => { const v = m.get(dt); if (v != null) last = v; if (last == null) return null; if (base == null) base = last; return (last / base - 1) * 100; });
      series.push({ sym: s, color: CMP_COLORS[k], vals });
    });
    const all = series.flatMap(s => s.vals.filter(v => v != null));
    mn = Math.min(...all, 0); mx = Math.max(...all, 0);
    ys = v => pl.t + ph - ((v - mn) / (mx - mn || 1)) * ph;
    grid = gridLines(v => v.toFixed(0) + '%') + `<line x1="${pl.l}" y1="${ys(0)}" x2="${W - pl.r}" y2="${ys(0)}" stroke="var(--border2)" stroke-width=".8" stroke-dasharray="3"/>`;
    series.forEach(s => {
      body += drawSvgLine(psvg, s.vals.map((v, i) => v == null ? null : [xs(i), ys(v)]), s.color, s === series[0] ? 2 : 1.5);
      const lv = [...s.vals].reverse().find(v => v != null);
      if (lv != null) body += `<text x="${W - pl.r - 2}" y="${ys(lv) - 4}" fill="${s.color}" font-size="9" text-anchor="end" font-family="IBM Plex Mono">${shortSym(s.sym)} ${fmtPct(lv)}</text>`;
    });
  } else {
    const useC = chartMode === 'candle';
    const bb = overlays.bb && N >= 20 ? bollinger(closes) : null;
    const vw = overlays.vwap ? vwapAnchored(data) : null;
    const ext = useC ? [...data.map(d => d.low), ...data.map(d => d.high)] : [...closes];
    if (cone) ext.push(...cone.lo, ...cone.hi);
    if (bb) ext.push(...bb.up.filter(v => v != null), ...bb.lo.filter(v => v != null));
    mn = Math.min(...ext); mx = Math.max(...ext);
    ys = v => pl.t + ph - ((v - mn) / (mx - mn || 1)) * ph;
    grid = gridLines(v => v >= 1000 ? v.toFixed(0) : v.toFixed(2));
    if (bb) {
      const up = bb.up.map((v, i) => v == null ? null : `${xs(i)},${ys(v)}`).filter(Boolean);
      const lo = bb.lo.map((v, i) => v == null ? null : `${xs(i)},${ys(v)}`).filter(Boolean);
      body += `<polygon points="${up.join(' ')} ${lo.reverse().join(' ')}" fill="rgba(79,163,255,.07)"/>`;
      body += drawSvgLine(psvg, bb.up.map((v, i) => v == null ? null : [xs(i), ys(v)]), 'rgba(79,163,255,.55)', 1, '2 2');
      body += drawSvgLine(psvg, bb.lo.map((v, i) => v == null ? null : [xs(i), ys(v)]), 'rgba(79,163,255,.55)', 1, '2 2');
    }
    const lineColor = closes[N - 1] >= closes[0] ? 'var(--green)' : 'var(--red)';
    if (useC) {
      const k = Math.max(1, Math.ceil(N / 260)), step = pw / ((N - 1 + F) || 1);
      for (let s = 0; s < N; s += k) {
        const e = Math.min(N - 1, s + k - 1), o = data[s].open || data[s].close, c = data[e].close;
        let h = -Infinity, l = Infinity;
        for (let j = s; j <= e; j++) { h = Math.max(h, data[j].high); l = Math.min(l, data[j].low); }
        const xc = xs((s + e) / 2), bw = Math.max(1, step * k * 0.7), col = c >= o ? 'var(--green)' : 'var(--red)';
        body += `<line x1="${xc}" y1="${ys(h)}" x2="${xc}" y2="${ys(l)}" stroke="${col}" stroke-width="1"/>
          <rect x="${xc - bw / 2}" y="${ys(Math.max(o, c))}" width="${bw}" height="${Math.max(1, Math.abs(ys(o) - ys(c)))}" fill="${col}"/>`;
      }
    } else {
      const pts = closes.map((v, i) => `${xs(i)},${ys(v)}`).join(' ');
      body += `<defs><linearGradient id="pg" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="${lineColor}" stop-opacity=".18"/><stop offset="100%" stop-color="${lineColor}" stop-opacity="0"/></linearGradient></defs>
        <polygon points="${pts} ${xs(N - 1)},${pl.t + ph} ${pl.l},${pl.t + ph}" fill="url(#pg)"/>
        <polyline points="${pts}" fill="none" stroke="${lineColor}" stroke-width="1.8" stroke-linejoin="round"/>
        <line x1="${pl.l}" y1="${ys(closes[0])}" x2="${xs(N - 1)}" y2="${ys(closes[0])}" stroke="var(--border2)" stroke-width=".7" stroke-dasharray="3"/>`;
    }
    if (overlays.sma20) body += drawSvgLine(psvg, sma(closes, 20).map((v, i) => v !== null ? [xs(i), ys(v)] : null), 'var(--purple)', 1.2, '3');
    if (overlays.sma50) body += drawSvgLine(psvg, sma(closes, 50).map((v, i) => v !== null ? [xs(i), ys(v)] : null), 'var(--gold)', 1.2, '5');
    if (vw) body += drawSvgLine(psvg, vw.map((v, i) => v == null ? null : [xs(i), ys(v)]), 'var(--cyan)', 1.3, '1 2');
    if (cone) {
      const cp = (a, b) => a.map((v, k) => `${xs(N - 1 + k)},${ys(v)}`).join(' ') + ' ' + b.map((v, k) => `${xs(N - 1 + k)},${ys(v)}`).reverse().join(' ');
      const m = cone.mid[F];
      body += `<polygon points="${cp(cone.hi, cone.lo)}" fill="rgba(251,191,36,.08)"/><polygon points="${cp(cone.hi50, cone.lo50)}" fill="rgba(251,191,36,.14)"/>
        <polyline points="${cone.mid.map((v, k) => `${xs(N - 1 + k)},${ys(v)}`).join(' ')}" fill="none" stroke="var(--gold)" stroke-width="1.2" stroke-dasharray="4 3"/>
        <text x="${xs(N - 1 + F) - 2}" y="${ys(m) - 5}" fill="var(--gold)" font-size="8.5" text-anchor="end" font-family="IBM Plex Mono">+${F}d ${nf(m)} (${nf(cone.lo[F])}–${nf(cone.hi[F])})</text>`;
    } else if (overlays.fcst && !cmpOn) {
      body += `<text x="${W / 2}" y="${pl.t + 12}" fill="var(--gold)" font-size="9" text-anchor="middle" font-family="IBM Plex Mono">FCST needs 3M or longer period</text>`;
    }
  }
  let xL = '';
  const tc = Math.min(7, N);
  for (let k = 0; k < tc; k++) { const idx = Math.round(k * (N - 1) / ((tc - 1) || 1)); xL += `<text x="${xs(idx)}" y="${H - 3}" fill="var(--muted)" font-size="8.5" text-anchor="middle" font-family="IBM Plex Mono">${long ? dates[idx].slice(0, 7) : dates[idx].slice(5)}</text>`; }
  psvg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  psvg.innerHTML = grid + body + xL;

  // volume
  const vsvg = document.getElementById('vol-svg'), VH = 60, maxV = Math.max(...vols) || 1;
  const barW = Math.max(1, pw / (N - 1 + F) - 0.4);
  vsvg.setAttribute('viewBox', `0 0 ${W} ${VH}`);
  vsvg.innerHTML = vols.map((v, i) => {
    const bh = (v / maxV) * (VH - 6), col = closes[i] >= (closes[i - 1] || closes[i]) ? 'rgba(0,208,132,.45)' : 'rgba(255,71,87,.45)';
    return `<rect x="${xs(i) - barW / 2}" y="${VH - 4 - bh}" width="${barW}" height="${bh}" fill="${col}" rx="1"/>`;
  }).join('') + `<text x="${W - pl.r}" y="10" fill="var(--muted)" font-size="7.5" text-anchor="end" font-family="IBM Plex Mono">VOL</text>`;

  // lower panel
  const rsvg = document.getElementById('rsi-svg'), RH = 70;
  rsvg.setAttribute('viewBox', `0 0 ${W} ${RH}`);
  if (lowerPanel === 'macd' && N > 35) {
    const e12 = emaJS(closes, 12), e26 = emaJS(closes, 26), macd = e12.map((v, i) => v - e26[i]), sig = emaJS(macd, 9), hist = macd.map((v, i) => v - sig[i]);
    const from = 26, vals = [...macd.slice(from), ...sig.slice(from), ...hist.slice(from)];
    const lo = Math.min(...vals, 0), hi = Math.max(...vals, 0), my = v => 4 + ((hi - v) / (hi - lo || 1)) * (RH - 8);
    const bw = Math.max(1, pw / (N - 1 + F) - 0.5);
    let g = `<line x1="${pl.l}" y1="${my(0)}" x2="${W - pl.r}" y2="${my(0)}" stroke="var(--border2)" stroke-width=".6"/>`;
    for (let i = from; i < N; i++) { const y0 = my(0), y1 = my(hist[i]); g += `<rect x="${xs(i) - bw / 2}" y="${Math.min(y0, y1)}" width="${bw}" height="${Math.abs(y1 - y0)}" fill="${hist[i] >= 0 ? 'rgba(0,208,132,.5)' : 'rgba(255,71,87,.5)'}"/>`; }
    g += drawSvgLine(rsvg, macd.map((v, i) => i < from ? null : [xs(i), my(v)]), 'var(--cyan)', 1.3);
    g += drawSvgLine(rsvg, sig.map((v, i) => i < from ? null : [xs(i), my(v)]), 'var(--orange)', 1.1);
    g += `<text x="${W - pl.r - 2}" y="10" fill="var(--muted)" font-size="7.5" text-anchor="end" font-family="IBM Plex Mono">MACD ${macd[N - 1].toFixed(2)} · signal ${sig[N - 1].toFixed(2)}</text>`;
    rsvg.innerHTML = g;
  } else {
    const rv = rsi14(closes);
    if (rv.filter(v => v !== null).length > 2) {
      const rY = v => 3 + ((100 - v) / 100) * (RH - 6), y70 = rY(70), y30 = rY(30), y50 = rY(50);
      rsvg.innerHTML = `<rect x="${pl.l}" y="${y70}" width="${pw}" height="${y30 - y70}" fill="rgba(79,163,255,.04)"/>
        <line x1="${pl.l}" y1="${y70}" x2="${W - pl.r}" y2="${y70}" stroke="rgba(255,71,87,.3)" stroke-width=".6" stroke-dasharray="3"/>
        <line x1="${pl.l}" y1="${y30}" x2="${W - pl.r}" y2="${y30}" stroke="rgba(0,208,132,.3)" stroke-width=".6" stroke-dasharray="3"/>
        <line x1="${pl.l}" y1="${y50}" x2="${W - pl.r}" y2="${y50}" stroke="var(--border)" stroke-width=".35"/>
        ${drawSvgLine(rsvg, rv.map((v, i) => v !== null ? [xs(i), rY(v)] : null), 'var(--cyan)', 1.4)}
        <text x="${W - pl.r - 2}" y="${y70 - 2}" fill="rgba(255,71,87,.7)" font-size="7.5" text-anchor="end" font-family="IBM Plex Mono">70</text>
        <text x="${W - pl.r - 2}" y="${y30 - 2}" fill="rgba(0,208,132,.7)" font-size="7.5" text-anchor="end" font-family="IBM Plex Mono">30</text>`;
    } else rsvg.innerHTML = '';
  }
}

/* explorer quick actions */
function alertQuick(btn) {
  document.querySelectorAll('.mini-pop').forEach(p => p.remove());
  if (!curSym) return;
  const r = btn.getBoundingClientRect();
  const last = window._lastPriceData && window._lastPriceData.length ? window._lastPriceData[window._lastPriceData.length - 1].close : '';
  const pop = document.createElement('div');
  pop.className = 'mini-pop';
  pop.style.left = (r.left + window.scrollX) + 'px'; pop.style.top = (r.bottom + window.scrollY + 6) + 'px';
  pop.innerHTML = `<div class="sec-lbl">Alert for ${shortSym(curSym)}</div>
    <div class="row2" style="margin-bottom:8px"><select class="sel" id="qa-cond"><option value="above">above</option><option value="below">below</option></select>
    <input class="inp mono" id="qa-price" type="number" value="${last ? (+last).toFixed(2) : ''}"></div>
    <div style="display:flex;gap:6px"><button class="btn" style="flex:1" onclick="alAdd('${curSym}',document.getElementById('qa-cond').value,document.getElementById('qa-price').value);this.closest('.mini-pop').remove()">Add alert</button>
    <button class="btn ghost" onclick="this.closest('.mini-pop').remove()">✕</button></div>`;
  document.body.appendChild(pop);
}
function tradeQuick(sym) {
  sym = sym || curSym; if (!sym) return;
  goTab('paper'); ptSetMkt(mktOf(sym));
  document.getElementById('pt-sym').value = sym; ptQuote();
}
function labFromExplorer() { if (!curSym) return; goTab('lab'); labSetSymbol(curSym); labRun(); }

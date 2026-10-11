/* Kairos v4: paper trading, watchlist, price alerts */
let PT_MKT = 'india', PT_SIDE = 'BUY', _ptQuote = null, _ptT = null, WATCH = new Set();

function ptSetMkt(m) {
  PT_MKT = m;
  ['india', 'usa'].forEach(x => document.getElementById('pt-btn-' + x).classList.toggle('active', x === m));
  ptLoad();
}
function ptSide(s) {
  PT_SIDE = s;
  document.getElementById('pt-buy').classList.toggle('on', s === 'BUY');
  document.getElementById('pt-sell').classList.toggle('on', s === 'SELL');
  const b = document.getElementById('pt-submit');
  b.textContent = s === 'BUY' ? 'Buy at market' : 'Sell at market';
  b.className = 'btn ' + (s === 'BUY' ? 'green' : 'red');
  b.style.width = '100%';
  ptEst();
}
function ptQuote() {
  clearTimeout(_ptT);
  _ptT = setTimeout(async () => {
    const s = normSym(document.getElementById('pt-sym').value);
    if (!s) { _ptQuote = null; ptEst(); return; }
    try {
      const d = await getJSON(`/api/stock/${encodeURIComponent(s)}?period=5d`);
      _ptQuote = d.length ? { sym: s, price: d[d.length - 1].close, chg: d.length > 1 ? (d[d.length - 1].close / d[d.length - 2].close - 1) * 100 : 0 } : null;
    } catch { _ptQuote = null; }
    ptEst();
  }, 350);
}
function ptEst() {
  const el = document.getElementById('pt-est');
  const q = parseFloat(document.getElementById('pt-qty').value) || 0;
  if (!_ptQuote) { el.textContent = 'Type a symbol to see the price'; return; }
  const m = mktOf(_ptQuote.sym);
  el.innerHTML = `${shortSym(_ptQuote.sym)} ${money(_ptQuote.price, m, 2)} <span class="${cls(_ptQuote.chg)}">${fmtPct(_ptQuote.chg)}</span> · ${q} × = <b style="color:var(--text)">${money(q * _ptQuote.price, m, 2)}</b>`;
}
async function ptSubmit() {
  const sym = normSym(document.getElementById('pt-sym').value), qty = parseFloat(document.getElementById('pt-qty').value);
  if (!sym) { toast('Order', 'Enter a symbol', 'warn'); return; }
  const btn = document.getElementById('pt-submit'); busy(btn, true, 'Sending…');
  try {
    const r = await postJSON('/api/paper/order', { symbol: sym, side: PT_SIDE, qty });
    if (!r.ok) { toast('Order rejected', r.error, 'err'); return; }
    const m = mktOf(sym);
    toast(`${r.side === 'BUY' ? 'Bought' : 'Sold'} ${r.qty} ${shortSym(sym)}`, `at ${money(r.price, m, 2)} · ${money(r.value, m, 2)}${r.side === 'SELL' ? ` · realized ${money(r.realized, m, 2)}` : ''}`, 'ok');
    if (mktOf(sym) !== PT_MKT) ptSetMkt(mktOf(sym)); else ptLoad();
  } catch { toast('Order failed', 'Server error', 'err'); }
  finally { busy(btn, false); ptSide(PT_SIDE); }
}
function ptPrefill(sym, side, qty) {
  document.getElementById('pt-sym').value = sym;
  document.getElementById('pt-qty').value = qty;
  ptSide(side); ptQuote();
  document.getElementById('pt-sym').scrollIntoView({ behavior: 'smooth', block: 'center' });
}
async function ptLoad() {
  const m = PT_MKT;
  try {
    const a = await getJSON('/api/paper/account?mkt=' + m);
    const st = (l, v, c = '', sub = '') => `<div class="glass fc-stat"><div class="l">${l}</div><div class="v ${c}">${v}${sub ? `<small style="display:block;font-size:.6rem;font-weight:400">${sub}</small>` : ''}</div></div>`;
    document.getElementById('pt-summary').innerHTML =
      st('Account value', money(a.equity, m), '', `started ${money(a.start_cash, m)}`) +
      st('Total P&L', money(a.pnl, m), cls(a.pnl), pct(a.pnl_pct, 2)) +
      st('Cash', money(a.cash, m)) +
      st('Invested', money(a.market_value, m), '', `${a.positions.length} position${a.positions.length === 1 ? '' : 's'}`) +
      st('Realized P&L', money(a.realized, m), cls(a.realized));
    document.getElementById('pt-positions').innerHTML = a.positions.length ? `<table class="tbl"><tr><th>Symbol</th><th>Qty</th><th>Avg cost</th><th>Last</th><th>Today</th><th>Value</th><th>Weight</th><th>Unrealized</th><th></th></tr>` +
      a.positions.map(p => `<tr><td><b style="cursor:pointer" onclick="openSymbol('${p.symbol}')">${shortSym(p.symbol)}</b></td><td>${p.qty}</td><td>${money(p.avg_price, m, 2)}</td><td>${money(p.last, m, 2)}</td>
        <td class="${cls(p.change)}">${fmtPct(p.change)}</td><td>${money(p.value, m)}</td><td>${(p.weight * 100).toFixed(1)}%</td>
        <td class="${cls(p.unrealized)}">${money(p.unrealized, m)} <small>${pct(p.unrealized_pct)}</small></td>
        <td><button class="btn ghost" style="padding:3px 9px;font-size:.62rem" onclick="ptPrefill('${p.symbol}','SELL',${p.qty})">Sell</button></td></tr>`).join('') + '</table>'
      : '<div class="note">No open positions. Place a buy order on the left, or hit ⇄ Trade on any stock in the Explorer.</div>';
    const hs = a.history || [];
    const svg = document.getElementById('pt-eq-svg');
    if (hs.length >= 2) plot(svg, [{ vals: hs.map(x => x.equity), color: 'var(--blue)', w: 1.8, area: 'rgba(79,163,255,.08)' }], { H: 150, hlines: [{ v: a.start_cash, label: 'start' }], yfmt: v => nfs(v) });
    else { svg.setAttribute('height', 40); svg.innerHTML = `<text x="8" y="22" fill="var(--muted)" font-size="11" font-family="IBM Plex Mono">Equity is snapshotted every 15 minutes while you use the dashboard. Check back later.</text>`; }
    document.getElementById('pt-orders').innerHTML = a.orders.length ? `<table class="tbl"><tr><th>Time</th><th>Side</th><th>Symbol</th><th>Qty</th><th>Price</th><th>Value</th><th>Realized</th></tr>` +
      a.orders.map(o => `<tr><td>${new Date(o.ts * 1000).toLocaleString()}</td><td style="font-family:var(--sans)"><span class="pill ${o.side === 'BUY' ? 'g' : 'r'}">${o.side}</span></td><td>${shortSym(o.symbol)}</td><td>${o.qty}</td>
        <td>${money(o.price, m, 2)}</td><td>${money(o.value, m)}</td><td class="${o.side === 'SELL' ? cls(o.realized) : ''}">${o.side === 'SELL' ? money(o.realized, m) : '—'}</td></tr>`).join('') + '</table>'
      : '<div class="note">No orders yet.</div>';
  } catch { document.getElementById('pt-summary').innerHTML = '<div class="note">Paper account unavailable</div>'; }
}
async function ptReset() {
  if (!confirm(`Reset the ${PT_MKT === 'india' ? 'India' : 'US'} paper account? This clears positions and order history.`)) return;
  await postJSON('/api/paper/reset?mkt=' + PT_MKT); toast('Account reset', '', 'ok'); ptLoad();
}

/* ── watchlist ── */
async function wlLoad() {
  try {
    const d = await getJSON('/api/watchlist');
    WATCH = new Set(d.map(x => x.symbol));
    if (curSym) onStockSelected(curSym);
    document.getElementById('wl-count').textContent = d.length ? d.length + (d.length === 1 ? ' symbol' : ' symbols') : '';
    document.getElementById('wl-list').innerHTML = d.length ? d.map(x => `<div class="wl-row">
      <span class="sym" onclick="openSymbol('${x.symbol}')">${FLAG(x.mkt)}${shortSym(x.symbol)}</span>
      <span style="font-family:var(--mono)">${x.price != null ? money(x.price, x.mkt, 2) : '—'}</span>
      <span style="font-family:var(--mono)" class="${cls(x.change)}">${x.change != null ? fmtPct(x.change) : ''}</span>
      <button class="x-btn" title="Remove" onclick="wlRemove('${x.symbol}')">✕</button></div>`).join('')
      : '<div class="note">Empty. Star a stock in the Explorer or add one here.</div>';
  } catch { }
}
async function wlAdd(sym) {
  sym = normSym(sym || document.getElementById('wl-add').value); if (!sym) return;
  await postJSON(`/api/watchlist/${encodeURIComponent(sym)}`);
  document.getElementById('wl-add').value = '';
  toast('Added to watchlist', shortSym(sym), 'ok'); wlLoad();
}
async function wlRemove(sym) { await delJSON(`/api/watchlist/${encodeURIComponent(sym)}`); wlLoad(); }
async function watchToggle() {
  if (!curSym) return;
  if (WATCH.has(curSym)) { await wlRemove(curSym); toast('Removed from watchlist', shortSym(curSym)); }
  else await wlAdd(curSym);
}

/* ── alerts ── */
async function alLoad() {
  try {
    const d = await getJSON('/api/alerts/rules');
    document.getElementById('al-list').innerHTML = d.length ? d.map(a => {
      const m = mktOf(a.symbol);
      return `<div class="wl-row" style="grid-template-columns:1fr auto 22px;${a.active ? '' : 'opacity:.55'}">
        <span><b>${shortSym(a.symbol)}</b> ${a.cond} ${money(a.price, m, 2)}</span>
        <span class="note">${a.active ? 'watching' : `hit ${money(a.trig_price, m, 2)} · ${new Date(a.triggered * 1000).toLocaleDateString()}`}</span>
        <button class="x-btn" onclick="alDel(${a.id})">✕</button></div>`;
    }).join('') : '<div class="note">No alerts yet.</div>';
  } catch { }
}
async function alAdd(sym, cond, price) {
  sym = normSym(sym || document.getElementById('al-sym').value);
  cond = cond || document.getElementById('al-cond').value;
  price = price ?? document.getElementById('al-price').value;
  if (!sym || price === '' || isNaN(parseFloat(price))) { toast('Alert', 'Enter a symbol and a price', 'warn'); return; }
  const r = await postJSON('/api/alerts/rules', { symbol: sym, cond, price: parseFloat(price) });
  if (!r.ok) { toast('Alert', r.error, 'err'); return; }
  toast('Alert set', `${shortSym(sym)} ${cond} ${nf(parseFloat(price))}`, 'ok');
  if (window.Notification && Notification.permission === 'default') Notification.requestPermission();
  alLoad();
}
async function alDel(id) { await delJSON('/api/alerts/rules/' + id); alLoad(); }
function alNotifyPerm() {
  if (!window.Notification) { toast('Notifications', 'Not supported in this browser', 'warn'); return; }
  Notification.requestPermission().then(p => toast('Notifications', p === 'granted' ? 'Enabled. Alerts will pop up on your desktop.' : 'Blocked. Alerts still show inside the page.', p === 'granted' ? 'ok' : 'warn'));
}

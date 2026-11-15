// Marswalk weather outlook: a statistical projection from past and recent weather at Gale crater (Curiosity REMS).
// Method: seasonal climatology from every past Mars year at the same solar longitude (Ls), plus the departure of the
// latest observations from that climatology, fading out with a 10-sol e-folding time. It is a projection, not a forecast:
// it cannot see dust storms or anything that has not happened at this season before.
// Data: NASA/JPL-Caltech/CAB REMS daily summaries (outreach feed; CAB discourages scientific use of it).
(function (root) {
const FEED = 'https://mars.nasa.gov/rss/api/?feed=weather&category=msl&feedtype=json&ver=1.0';
const SNAPSHOT = 'data/weather/rems_snapshot.json';
const SOL_DAYS = 1.02749125;            // Earth days per sol
const MARS_YEAR_SOLS = 668.6;
const WIN = 5, RECENT = 10;             // climatology Ls half-window (deg), recent sols averaged
// How long the latest departure from climatology lasts (e-folding, sols). Temperature departures are weather and fade;
// the pressure departure is mostly the rover's own altitude (Curiosity keeps climbing Mount Sharp), so it is kept.
const TAU = { minT: 10, maxT: 10, p: 2000 };
const VARS = [['minT', 'Min air temp', '°C'], ['maxT', 'Max air temp', '°C'], ['p', 'Pressure', 'Pa']];
let D = null, err = null, loading = null;

const num = v => (v === '--' || v === '' || v == null || isNaN(+v)) ? null : +v;
const lsd = (a, b) => { const d = Math.abs(a - b) % 360; return d > 180 ? 360 - d : d; };
function load() {
  if (loading) return loading;
  // live feed first; if it is unreachable, the snapshot shipped with the app (data/weather/rems_snapshot.json), clearly labelled
  const get = u => fetch(u).then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); });
  let source = 'live';
  loading = get(FEED).catch(e => { source = 'snapshot'; return get(SNAPSHOT); }).then(j => {
    const rows = (j.soles || []).map(s => ({ sol: +s.sol, ls: +s.ls, date: s.terrestrial_date, minT: num(s.min_temp), maxT: num(s.max_temp), p: num(s.pressure) }))
      .filter(r => isFinite(r.sol) && isFinite(r.ls)).sort((a, b) => a.sol - b.sol);
    let my = 0; rows.forEach((r, i) => { if (i && r.ls < rows[i - 1].ls - 180) my++; r.my = my; });     // Mars-year index from Ls wrap
    D = { rows, bySol: new Map(rows.map(r => [r.sol, r])), source, snapshotDate: j.snapshot_date }; return D;
  }).catch(e => { err = e; throw e; });
  return loading;
}
// climatology at Ls from Mars years before `beforeMy`, variable k: median and 10th to 90th percentile (cached by 0.5 deg of Ls)
function clim(ls, k, beforeMy) {
  const key = k + '|' + Math.round(ls * 2) + '|' + beforeMy, cache = D.cc || (D.cc = new Map());
  if (cache.has(key)) return cache.get(key);
  const v = []; for (const r of D.rows) { if (r.my >= beforeMy) break; if (r[k] != null && lsd(r.ls, ls) <= WIN) v.push(r[k]); }
  let out = null;
  if (v.length >= 5) { v.sort((a, b) => a - b); const q = f => v[Math.min(v.length - 1, Math.floor(f * v.length))]; out = { med: q(.5), lo: q(.1), hi: q(.9), n: v.length }; }
  cache.set(key, out); return out;
}
// Ls of a future sol: the same sol one Mars year earlier, else extrapolate
function lsOf(sol) {
  for (const back of [Math.round(MARS_YEAR_SOLS), Math.round(MARS_YEAR_SOLS) + 1, Math.round(2 * MARS_YEAR_SOLS)]) { const r = D.bySol.get(sol - back); if (r) return r.ls; }
  const last = D.rows[D.rows.length - 1]; return (last.ls + (sol - last.sol) * 0.524) % 360;
}
// projection for sols after `origin` using only rows with sol <= origin (so it can be replayed on the past)
function project(origin, sols, k) {
  const oRow = D.bySol.get(origin) || D.rows.filter(r => r.sol <= origin).slice(-1)[0], Y = oRow.my;  // climatology: earlier Mars years only
  const recent = D.rows.filter(r => r.sol <= origin && r[k] != null).slice(-RECENT);
  let an = 0, na = 0; for (const r of recent) { const c = clim(r.ls, k, Y); if (c) { an += r[k] - c.med; na++; } }
  an = na ? an / na : 0; const lastSol = recent.length ? recent[recent.length - 1].sol : origin;
  return sols.map(s => { const ls = lsOf(s), c = clim(ls, k, Y); if (!c) return { sol: s, ls, med: null };
    const w = Math.exp(-(s - lastSol) / TAU[k]); return { sol: s, ls, med: c.med + an * w, lo: c.lo + an * w, hi: c.hi + an * w, climMed: c.med, an: an * w }; });
}
// replay on past years: mean absolute error at several horizons, against climatology alone and persistence
function skill() {
  if (D.skill) return D.skill;
  const H = [1, 7, 30], out = {};
  const firstOk = D.rows.find(r => r.my >= 2);                                                          // need at least two earlier years
  const origins = D.rows.filter(r => firstOk && r.sol >= firstOk.sol && r.sol % 7 === 0 && r.minT != null);
  for (const [k] of VARS) {
    const e = H.map(() => ({ m: 0, c: 0, p: 0, n: 0 }));
    for (const o of origins) {
      const pr = project(o.sol, H.map(h => o.sol + h), k);
      H.forEach((h, i) => { const obs = D.bySol.get(o.sol + h); if (!obs || obs[k] == null || pr[i].med == null) return;
        e[i].m += Math.abs(pr[i].med - obs[k]); e[i].c += Math.abs(pr[i].climMed - obs[k]); e[i].p += Math.abs(o[k] - obs[k]); e[i].n++; });
    }
    out[k] = e.map((x, i) => ({ h: H[i], method: x.m / x.n, clim: x.c / x.n, persist: x.p / x.n, n: x.n }));
  }
  return (D.skill = out);
}
function outlook(todayDate) {
  const rows = D.rows, last = rows.filter(r => r.minT != null || r.p != null).slice(-1)[0];
  const lagDays = (todayDate - new Date(last.date + 'T12:00:00Z')) / 864e5, todaySol = Math.round(last.sol + lagDays / SOL_DAYS);
  const sols = []; for (let s = last.sol + 1; s <= todaySol + 30; s++) sols.push(s);
  const proj = {}; for (const [k] of VARS) proj[k] = project(last.sol, sols, k);
  return { last, lagDays, todaySol, sols, proj, hist: rows.filter(r => r.sol > last.sol - 90) };
}
const fmt = (v, u) => v == null ? '–' : (u === 'Pa' ? Math.round(v) : Math.round(v)) + ' ' + u;

// ---- rendering into a host element: chart, outlook table, skill table, caveats
function render(host, siteId) {
  if (!host) return;
  host.dataset.site = siteId;                                                     // the latest request wins when the feed arrives
  if (!D) { host.innerHTML = '<p class="note">' + (err ? 'Weather feed unreachable (' + err.message + '): no outlook.' : 'Loading Curiosity REMS weather history…') + '</p>';
    if (!err) load().then(() => render(host, host.dataset.site), () => render(host, host.dataset.site)); return; }
  const o = outlook(new Date()), at = siteId === 'gale';
  const ref = at ? '' : ' <span class="ev draft">Gale reference</span>';
  const pick = (k, s) => o.proj[k].find(x => x.sol === s);
  const rowsFor = sols => VARS.map(([k, label, u]) => '<tr><td>' + label + '</td>' + sols.map(s => { const x = pick(k, s);
      return '<td>' + (x && x.med != null ? fmt(x.med, u) + '<br><span class="note">' + fmt(x.lo, u) + ' to ' + fmt(x.hi, u) + '</span>' : '–') + '</td>'; }).join('') + '</tr>').join('');
  const sk = skill(), skRow = (k, label, u) => '<tr><td>' + label + '</td>' + sk[k].map(x => '<td>±' + x.method.toFixed(u === 'Pa' ? 0 : 1) + '<br><span class="note">clim ±' + x.clim.toFixed(u === 'Pa' ? 0 : 1) + ', persist ±' + x.persist.toFixed(u === 'Pa' ? 0 : 1) + '</span></td>').join('') + '</tr>';
  const T = o.todaySol, cols = [T, T + 7, T + 30];
  host.innerHTML =
    '<p class="note" style="margin:0">' + (at ? 'Measured here by Curiosity\'s REMS station.' : 'No weather station here' + (siteId === 'phoenix' ? ' since Phoenix ended in 2008' : siteId === 'jezero' ? ': NASA\'s Perseverance MEDA feed holds only seven sols, from April 2024' : '') + '. Shown instead: the projection for Gale crater, a reference only. Local weather is not characterized.') + '</p>' +
    '<canvas class="wx" width="680" height="300"></canvas>' +
    '<p class="note" style="margin:4px 0 0">Dots: REMS observations (last 90 sols). Lines and bands: projected median and 10th to 90th percentile. Last observation sol ' + o.last.sol + ' (' + o.last.date + '), ' + Math.round(o.lagDays) + ' days before today; by today the recent departure has faded and the projection is the seasonal climatology.</p>' +
    '<div class="tblwrap"><table class="cmp"><tr><th>Projection' + ref + '</th><th>Today<br>sol ' + T + '</th><th>+7 sols</th><th>+30 sols</th></tr>' + rowsFor(cols) + '</table></div>' +
    '<h2 style="margin-top:10px">Tested on past years</h2><div class="tblwrap"><table class="cmp"><tr><th>Mean error</th><th>1 sol ahead</th><th>7 sols</th><th>30 sols</th></tr>' +
    VARS.map(([k, l, u]) => skRow(k, l + ' (' + u + ')', u)).join('') + '</table></div>' +
    '<p class="note">Replayed every 7th sol from Curiosity\'s third Mars year on, using only data available at the time (' + sk.minT[0].n + ' replays). "clim": seasonal climatology alone. "persist": tomorrow equals today. ' +
    'Seasonal climatology from ' + (o.last.my + 1) + ' Mars years of REMS data at the same solar longitude (±' + WIN + '°), plus the latest observations\' departure from it. Temperature departures fade over about ' + TAU.minT + ' sols. The pressure departure is kept, because most of it is the rover\'s own altitude: Curiosity has climbed hundreds of metres up Mount Sharp, so earlier years read higher. ' +
    '<b>Not a forecast:</b> it cannot anticipate dust storms (the 2018 global storm is in the record as an outlier), and the bands are past spread, not a guarantee. <span class="ev sim">projection</span></p>' +
    '<p class="note">Data: NASA/JPL-Caltech, Centro de Astrobiología (CAB), REMS daily summaries via <a href="https://mars.nasa.gov/msl/weather/" target="_blank" rel="noopener">mars.nasa.gov</a>, ' + (D.source === 'live' ? 'fetched live.' : '<b>live feed unreachable: using the snapshot saved with this app on ' + D.snapshotDate + '</b>.') + ' CAB provides this feed for outreach and discourages other uses; scientific REMS data are in NASA PDS.</p>';
  drawChart(host.querySelector('canvas.wx'), o);
}
function drawChart(c, o) {
  const ctx = c.getContext('2d'), W = c.width, H = c.height; ctx.fillStyle = '#14110e'; ctx.fillRect(0, 0, W, H);
  const x0 = o.hist[0].sol, x1 = o.todaySol + 30, X = s => 44 + (s - x0) / (x1 - x0) * (W - 96);
  const pts = []; for (const k of ['minT', 'maxT']) { o.hist.forEach(r => r[k] != null && pts.push(r[k])); o.proj[k].forEach(p => p.med != null && pts.push(p.lo, p.hi)); }
  const tlo = Math.floor(Math.min(...pts) / 10) * 10, thi = Math.ceil(Math.max(...pts) / 10) * 10, Y = v => H - 24 - (v - tlo) / (thi - tlo) * (H - 44);
  const pp = []; o.hist.forEach(r => r.p != null && pp.push(r.p)); o.proj.p.forEach(p => p.med != null && pp.push(p.lo, p.hi));
  const plo = Math.min(...pp) - 5, phi = Math.max(...pp) + 5, YP = v => H - 24 - (v - plo) / (phi - plo) * (H - 44);
  ctx.font = '18px IBM Plex Mono'; ctx.strokeStyle = '#3a322a'; ctx.lineWidth = 1;
  for (let t = tlo; t <= thi; t += 10) { ctx.beginPath(); ctx.moveTo(44, Y(t)); ctx.lineTo(W - 52, Y(t)); ctx.stroke(); ctx.fillStyle = '#a3978a'; ctx.fillText(t + '°', 2, Y(t) + 6); }
  const band = (k, col, yf) => { const P = o.proj[k].filter(p => p.med != null); if (!P.length) return;
    ctx.fillStyle = col + '33'; ctx.beginPath(); P.forEach((p, i) => i ? ctx.lineTo(X(p.sol), yf(p.hi)) : ctx.moveTo(X(p.sol), yf(p.hi))); [...P].reverse().forEach(p => ctx.lineTo(X(p.sol), yf(p.lo))); ctx.fill();
    ctx.strokeStyle = col; ctx.lineWidth = 2.5; ctx.setLineDash([8, 6]); ctx.beginPath(); P.forEach((p, i) => i ? ctx.lineTo(X(p.sol), yf(p.med)) : ctx.moveTo(X(p.sol), yf(p.med))); ctx.stroke(); ctx.setLineDash([]); };
  band('p', '#a3978a', YP); band('minT', '#7fb3e6', Y); band('maxT', '#e0683a', Y);
  const dots = (k, col, yf) => { ctx.fillStyle = col; o.hist.forEach(r => { if (r[k] != null) { ctx.beginPath(); ctx.arc(X(r.sol), yf(r[k]), 2.6, 0, 7); ctx.fill(); } }); };
  dots('p', '#a3978a', YP); dots('minT', '#7fb3e6', Y); dots('maxT', '#e0683a', Y);
  const vline = (s, label, col) => { ctx.strokeStyle = col; ctx.setLineDash([3, 4]); ctx.beginPath(); ctx.moveTo(X(s), 10); ctx.lineTo(X(s), H - 24); ctx.stroke(); ctx.setLineDash([]); ctx.fillStyle = col; ctx.fillText(label, Math.min(W - 120, X(s) + 4), H - 4); };
  vline(o.last.sol, 'last data', '#a3978a'); vline(o.todaySol, 'today', '#e5b64a');
  ctx.fillStyle = '#a3978a'; ctx.textAlign = 'right'; ctx.fillText(Math.round(phi) + ' Pa', W - 2, 22); ctx.fillText(Math.round(plo) + ' Pa', W - 2, H - 28); ctx.textAlign = 'left';
  ctx.fillStyle = '#e0683a'; ctx.fillText('max', 50, 22); ctx.fillStyle = '#7fb3e6'; ctx.fillText('min', 100, 22); ctx.fillStyle = '#a3978a'; ctx.fillText('pressure', 150, 22);
}
root.MarswalkWeather = { load, render, outlook: () => D && outlook(new Date()), skill: () => D && skill() };
})(window);

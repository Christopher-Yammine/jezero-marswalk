// Marswalk planner core: walk sites, terrain grid, A* routing and route metrics.
// Shared by the 2D planner (index.html) and the 3D view (3d.html) so both compute the same routes.
// Plain {lat,lng} objects throughout; no Leaflet or three.js here.
(function (root) {
const R = 3396190;                    // Mars mean radius, m (same as NASA MMGIS and the Leaflet CRS)
const CELL = 30;                      // grid cell, m
const M_PER_DEG = R * Math.PI / 180;
const RAD = Math.PI / 180;
const NIGHT_ID = 'THEMIS_NightIR_ControlledMosaics_100m_v2_oct2018';

// Great-circle distance, identical to Leaflet's CRS distance with R.
function dist(a, b) {
  const lat1 = a.lat * RAD, lat2 = b.lat * RAD, sLat = Math.sin((b.lat - a.lat) * RAD / 2), sLon = Math.sin((b.lng - a.lng) * RAD / 2);
  const h = sLat * sLat + Math.cos(lat1) * Math.cos(lat2) * sLon * sLon;
  return R * 2 * Math.atan2(Math.sqrt(h), Math.sqrt(1 - h));
}

// ---- Walk sites. They share no data: each has its own grid, elevation source, targets and habitat.
const JEZ_TARGETS = [
  { n: 'Octavia E. Butler landing site', sol: 14, ll: [18.444627, 77.450886], d: 'Touchdown 18 Feb 2021. Crater floor, Máaz formation basalts.' },
  { n: 'Séítah', sol: 200, ll: [18.432548, 77.440687], d: 'Olivine-rich layered rocks, first cores. Ridged, sandy ground the rover had to drive around.' },
  { n: 'Delta front, Hawksbill Gap', sol: 420, ll: [18.449825, 77.401363], d: 'Sandstone and mudstone of the ancient delta. Clays and carbonates from orbit (CRISM).' },
  { n: 'Three Forks sample depot', sol: 693, ll: [18.454176, 77.408448], d: 'Ten sealed sample tubes left on the surface for Mars Sample Return.' },
  { n: 'Bright Angel', sol: 1182, ll: [18.497182, 77.305358], d: 'Light-toned rock in Neretva Vallis. Cheyava Falls leopard-spot core, July 2024.' },
  { n: 'Crater rim, Witch Hazel Hill', sol: 1400, ll: [18.460553, 77.264745], d: 'Oldest rocks of the mission, 700 m above the floor. Steepest ground driven.' },
  { n: 'Rover now (last published drive)', sol: 2022, ll: [18.435594, 77.233223], d: 'Position at the end of the traverse file.' },
];
// Arcadia targets: positions located by eye in HRSC orbit 26333 (12.5 m), about 100 m accuracy. Each has a fallback.
// alt marks a fallback; ph marks a placeholder with no position.
const ARC_TARGETS = [
  { n: 'Yardang field edge', ll: [41.353, -148.092], ev: 'orb', d: 'Boundary between ridged, wind-carved terrain (west) and darker terrain without ridges (east). The ridges are just under 20 m across, near the image limit, so individual ridges are not resolved.' },
  { n: 'Yardang field edge, fallback', alt: 1, ll: [41.470, -148.080], ev: 'orb', d: 'Same boundary about 13 km to the north, where a tongue of ridged terrain meets the dark plain.' },
  { n: 'Dark deposit against the ridge', ll: [41.410, -147.962], ev: 'orb', d: 'Dark material on the north-east (lee) side of a bright knob, read as dark volcanic sand piled against a rock ridge that blocks the wind. Composition not measured. HiRISE ESP_046912_2215 covers it but is not loaded here.' },
  { n: 'Dark deposit, fallback', alt: 1, ll: [41.454, -147.970], ev: 'orb', d: 'A second, smaller dark patch north of the knob. Same interpretation, lower confidence.' },
  { n: 'Rampart crater ejecta (candidate)', ll: [43.47, -147.75], ev: 'orb', d: 'South edge of the lobate ejecta apron of a crater about 20 km wide at 43.70°N 212.27°E. The release describes a rampart crater of about 15 km; this is the best match found in the scene, not confirmed. About 125 km from the habitat: outside the walk grid, so no routes.' },
  { n: 'Rampart crater ejecta, fallback', alt: 1, ph: 1, ev: 'ph', d: 'Placeholder: no second crater with fluidized ejecta was found in the HRSC scene.' },
  { n: 'Ice-related landform', ph: 1, ev: 'ph', d: 'Placeholder: no ice-related landform (scalloped pits, polygons, ice-exposing scarp) was located in the walk area at 12.5 m. Ice is likely near the surface regionally, not measured here.' },
  { n: 'Ice-related landform, fallback', alt: 1, ph: 1, ev: 'ph', d: 'Placeholder: candidate is the rampart crater ejecta above, whose shape suggests volatile-rich ground at impact.' },
];
const SITES = {
  jezero: { id: 'jezero', bounds: [[18.3067994, 77.2229331], [18.669315, 77.583964]], hab: [18.444627, 77.450886],
    dtm: 'data/jez_dtm_30m.i16', rough: null, track: 'm20_traverse.json', targets: JEZ_TARGETS },
  // Arcadia walk grid sits inside HRSC orbit 26333 (data/arcadia/build_arcadia.py). Draft habitat on the smoother dark terrain.
  arcadia: { id: 'arcadia', bounds: [[41.22, -148.22], [41.52, -147.88]], hab: [41.36, -148.05],
    dtm: 'data/arcadia/arc_dtm_30m.i16', dtmOffset: -3000, rough: 'data/arcadia/arc_rough_30m.u8', fill: 'data/arcadia/arc_elev_fill_30m.i16', track: null, targets: ARC_TARGETS },
};

// ---- Grid geometry: cell centres, equirectangular at the grid's mid latitude
function geom(b) {
  const lat0 = b[1][0], lat1 = b[0][0], lon0 = b[0][1], lon1 = b[1][1];
  const latC = (lat0 + lat1) / 2, mLon = M_PER_DEG * Math.cos(latC * RAD), mLat = M_PER_DEG;
  return { lat0, lat1, lon0, lon1, mLon, mLat, nx: Math.ceil((lon1 - lon0) * mLon / CELL), ny: Math.ceil((lat0 - lat1) * mLat / CELL) };
}
// THEMIS night IR tiles at Trek zoom 9 covering the grid (Jezero: rows 202-203, cols 731-732)
function themisTiles(b) {
  const td = 180 / 512;
  return { td, c0: Math.floor((b[0][1] + 180) / td), c1: Math.floor((b[1][1] + 180) / td), r0: Math.floor((90 - b[1][0]) / td), r1: Math.floor((90 - b[0][0]) / td) };
}
function loadThemis(b) {
  const NT = themisTiles(b), c = document.createElement('canvas'); c.width = (NT.c1 - NT.c0 + 1) * 256; c.height = (NT.r1 - NT.r0 + 1) * 256;
  const ctx = c.getContext('2d'), jobs = [];
  for (let r = NT.r0; r <= NT.r1; r++) for (let col = NT.c0; col <= NT.c1; col++) jobs.push(new Promise((res, rej) => {
    const im = new Image(); im.crossOrigin = 'anonymous';
    im.onload = () => { ctx.drawImage(im, (col - NT.c0) * 256, (r - NT.r0) * 256); res(); }; im.onerror = rej;
    im.src = 'https://trek.nasa.gov/tiles/Mars/EQ/' + NIGHT_ID + '/1.0.0/default/default028mm/9/' + r + '/' + col + '.png';
  }));
  return Promise.all(jobs).then(() => c);
}

// Terrain grid for routing. Inputs are real: THEMIS night IR pixels (orbital proxy for sand), rover track points
// [lat, lon, el] (proven ground, Jezero only), the site's elevation grid, and on Arcadia the HRSC texture grid.
function buildGrid({ site, nirCanvas, dtmBuf, roughBuf, pts = [] }) {
  const b = site.bounds, { lat0, lon0, mLon, mLat, nx, ny } = geom(b), n = nx * ny, arc = site.id === 'arcadia';
  const sand = new Float32Array(n), driven = new Uint8Array(n), elev = new Float32Array(n).fill(NaN), ecount = new Uint16Array(n);
  const NT = themisTiles(b), W = nirCanvas.width, H = nirCanvas.height, pxDeg = NT.td / 256, tLon0 = -180 + NT.c0 * NT.td, tLat0 = 90 - NT.r0 * NT.td;
  const img = nirCanvas.getContext('2d').getImageData(0, 0, W, H).data, raw = new Float32Array(n);
  for (let y = 0; y < ny; y++) for (let x = 0; x < nx; x++) {
    const lon = lon0 + (x + .5) * CELL / mLon, lat = lat0 - (y + .5) * CELL / mLat;
    const px = Math.min(W - 1, Math.max(0, Math.floor((lon - tLon0) / pxDeg))), py = Math.min(H - 1, Math.max(0, Math.floor((tLat0 - lat) / pxDeg))), o = (py * W + px) * 4;
    raw[y * nx + x] = img[o + 3] === 0 ? NaN : img[o];          // transparent pixel = no THEMIS data, not dark sand
  }
  // data-driven normalisation: 15th and 65th percentile of night brightness over the grid (cells with data)
  const sorted = raw.filter(v => !isNaN(v)).sort(), m = sorted.length || 1, p15 = sorted[Math.floor(m * .15)], p65 = sorted[Math.floor(m * .65)];
  for (let i = 0; i < n; i++) sand[i] = isNaN(raw[i]) ? NaN : Math.min(1, Math.max(0, (p65 - raw[i]) / Math.max(1, p65 - p15)));
  const toCell = (lat, lon) => { const x = Math.floor((lon - lon0) * mLon / CELL), y = Math.floor((lat0 - lat) * mLat / CELL); return (x < 0 || y < 0 || x >= nx || y >= ny) ? -1 : y * nx + x; };
  for (const p of pts) {
    const i = toCell(p[0], p[1]); if (i < 0) continue;
    const x = i % nx, y = (i / nx) | 0;
    for (let dy = -2; dy <= 2; dy++) for (let dx = -2; dx <= 2; dx++) { const xx = x + dx, yy = y + dy; if (xx >= 0 && yy >= 0 && xx < nx && yy < ny && dx * dx + dy * dy <= 4) driven[yy * nx + xx] = 1; }
    if (p[2] != null) { elev[i] = (isNaN(elev[i]) ? 0 : elev[i] * ecount[i]) / (ecount[i] + 1) + p[2] / (ecount[i] + 1); ecount[i]++; }
  }
  // Elevation grid, same nx x ny: Int16 decimetres above site.dtmOffset (m), -32768 = no data
  // (Jezero: CTX DTM, offset 0; Arcadia: MOLA, offset -3000 m because -3,700 m in decimetres overflows Int16; no data = bin without a laser shot)
  let dtm = false, shotN = 0, cnt = 0, mean = 0, sd = 0;
  const off = site.dtmOffset || 0;
  if (dtmBuf && dtmBuf.byteLength === n * 2) {
    const d = new Int16Array(dtmBuf); let sum = 0, sum2 = 0;
    for (let i = 0; i < n; i++) { if (d[i] !== -32768) { const v = d[i] / 10 + off; shotN++; if (!isNaN(elev[i])) { const df = v - elev[i]; sum += df; sum2 += df * df; cnt++; } elev[i] = v; } }
    mean = cnt ? sum / cnt : 0; sd = cnt ? Math.sqrt(Math.max(0, sum2 / cnt - mean * mean)) : 0; dtm = true;
  }
  // Arcadia: HRSC image-texture roughness 0..1, NaN where no HRSC pixel
  let rough = null;
  if (roughBuf && roughBuf.byteLength === n) { const r = new Uint8Array(roughBuf); rough = new Float32Array(n); for (let i = 0; i < n; i++) rough[i] = r[i] === 255 ? NaN : r[i] / 254; }
  let drv = 0; for (let i = 0; i < n; i++) drv += driven[i];
  return { ready: true, site: site.id, arc, nx, ny, n, sand, driven, elev, dtm, rough, lat0, lon0, mLon, mLat, toCell, p15, p65, shotN, drv,
    dtmCheck: { cnt, mean, sd }, cellLL: i => ({ lat: lat0 - ((i / nx | 0) + .5) * CELL / mLat, lng: lon0 + ((i % nx) + .5) * CELL / mLon }) };
}

// Elevation at a point: bilinear in the grid; null where any corner has no data.
function elevAt(G, ll) {
  if (!G || !G.ready || !G.dtm) return null;
  const fx = (ll.lng - G.lon0) * G.mLon / CELL - .5, fy = (G.lat0 - ll.lat) * G.mLat / CELL - .5, x0 = Math.floor(fx), y0 = Math.floor(fy);
  if (x0 < 0 || y0 < 0 || x0 >= G.nx - 1 || y0 >= G.ny - 1) return null;
  const tx = fx - x0, ty = fy - y0, e = G.elev, i = y0 * G.nx + x0;
  const v = e[i] * (1 - tx) * (1 - ty) + e[i + 1] * tx * (1 - ty) + e[i + G.nx] * (1 - tx) * ty + e[i + G.nx + 1] * tx * ty;
  return isNaN(v) ? null : v;
}
const cellVal = (G, arr, ll) => { if (!G || !G.ready || !arr) return null; const i = G.toCell(ll.lat, ll.lng); return i < 0 || isNaN(arr[i]) ? null : arr[i]; };
const sandAt = (G, ll) => cellVal(G, G && G.sand, ll);
const roughAt = (G, ll) => cellVal(G, G && G.rough, ll);
const drivenAt = (G, ll) => { if (!G || !G.ready) return null; const i = G.toCell(ll.lat, ll.lng); return i < 0 ? null : G.driven[i]; };

// A* over the 8-neighbour grid. mode: 'terrain' | 'best' | 'soft'. Returns the path after `from`, ending at `to`.
function astar(G, from, to, mode, slopeLim) {
  if (!G || !G.ready) return null;
  const s0 = G.toCell(from.lat, from.lng), t0 = G.toCell(to.lat, to.lng); if (s0 < 0 || t0 < 0) return null;
  const { nx, ny, n, sand, driven, elev, rough, arc } = G;
  const g = new Float32Array(n).fill(Infinity), par = new Int32Array(n).fill(-1), done = new Uint8Array(n);
  const hp = []; const push = (f, i) => { hp.push([f, i]); let k = hp.length - 1; while (k) { const p = (k - 1) >> 1; if (hp[p][0] <= hp[k][0]) break; [hp[p], hp[k]] = [hp[k], hp[p]]; k = p; } };
  const pop = () => { const t = hp[0], l = hp.pop(); if (hp.length) { hp[0] = l; let k = 0; for (;;) { const a = 2 * k + 1, b = a + 1; let s = k; if (a < hp.length && hp[a][0] < hp[s][0]) s = a; if (b < hp.length && hp[b][0] < hp[s][0]) s = b; if (s === k) break; [hp[s], hp[k]] = [hp[k], hp[s]]; k = s; } } return t; };
  const tx = t0 % nx, ty = (t0 / nx) | 0;
  const h = i => { const dx = Math.abs(i % nx - tx), dy = Math.abs(((i / nx) | 0) - ty); return (Math.max(dx, dy) + (Math.SQRT2 - 1) * Math.min(dx, dy)) * CELL * 0.6; };
  const mu = j => { let m = 1 + 2.5 * (isNaN(sand[j]) ? 0 : sand[j]);
    if (rough && !isNaN(rough[j])) m += 1.5 * rough[j];                                // Arcadia: HRSC texture, yardang proxy
    if (driven[j]) m *= 0.6; else if (mode === 'best' || mode === 'soft') m += 1.0;
    if (arc && (mode === 'best' || mode === 'soft') && isNaN(elev[j])) m += 0.5;          // Arcadia: prefer cells where MOLA has a shot
    return m; };
  g[s0] = 0; push(h(s0), s0); let expanded = 0;
  while (hp.length) {
    const [, i] = pop(); if (done[i]) continue; done[i] = 1; if (i === t0) break; if (++expanded > 400000) return null;
    const x = i % nx, y = (i / nx) | 0;
    for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
      if (!dx && !dy) continue; const xx = x + dx, yy = y + dy; if (xx < 0 || yy < 0 || xx >= nx || yy >= ny) continue;
      const j = yy * nx + xx; if (done[j]) continue;
      const d = Math.hypot(dx, dy) * CELL;
      let steep = 0;
      if ((mode === 'best' || mode === 'soft') && j !== t0 && !isNaN(elev[i]) && !isNaN(elev[j])) { const sl = Math.atan2(Math.abs(elev[j] - elev[i]), d) * 180 / Math.PI; if (sl > slopeLim) { if (mode === 'best') continue; steep = sl / slopeLim; } }
      const c = g[i] + d * mu(j) * (1 + 8 * steep);
      if (c < g[j]) { g[j] = c; par[j] = i; push(c + h(j), j); }
    }
  }
  if (!done[t0]) return null;
  const cells = []; for (let i = t0; i !== -1; i = par[i]) cells.push(i); cells.reverse();
  return simplify(G, cells.map(i => G.cellLL(i)), 12).slice(1, -1).concat([to]);
}
// Route under the slope limit; if no such path exists (a point inside a crater), take the least steep one and say so.
function routeTo(G, from, to, lim) {
  let path = astar(G, from, to, 'best', lim); if (path) return { path, soft: false };
  path = astar(G, from, to, 'soft', lim); return path ? { path, soft: true } : null;
}
function simplify(G, ll, tol) { // Douglas-Peucker on metres
  if (ll.length < 3) return ll;
  const perp = (p, a, b) => { const ax = (p.lng - a.lng) * G.mLon, ay = (p.lat - a.lat) * G.mLat, bx = (b.lng - a.lng) * G.mLon, by = (b.lat - a.lat) * G.mLat; const l2 = bx * bx + by * by || 1; const t = Math.max(0, Math.min(1, (ax * bx + ay * by) / l2)); return Math.hypot(ax - t * bx, ay - t * by); };
  let idx = 0, md = 0; for (let i = 1; i < ll.length - 1; i++) { const d = perp(ll[i], ll[0], ll[ll.length - 1]); if (d > md) { md = d; idx = i; } }
  if (md > tol) { const a = simplify(G, ll.slice(0, idx + 1), tol), b = simplify(G, ll.slice(idx), tol); return a.slice(0, -1).concat(b); }
  return [ll[0], ll[ll.length - 1]];
}
// walk a leg in 30 m steps so long straight legs are judged on every cell they cross, not their midpoint
function samples(a, b, step) { const d = dist(a, b), n = Math.max(1, Math.ceil(d / step)), out = []; for (let k = 0; k <= n; k++) { const f = k / n; out.push({ lat: a.lat + (b.lat - a.lat) * f, lng: a.lng + (b.lng - a.lng) * f }); } return out; }
// Length, sandy / proven / rough shares, share with known slope, breaks (steps over the limit + leaving the walk-back circle)
function routeMetrics(G, path, from, { slopeLim, radius, hab, elevFn }) {
  const full = [from, ...path], el = elevFn || (ll => elevAt(G, ll)); let len = 0, sandy = 0, drv = 0, known = 0, breaks = 0, far = 0, rgh = 0;
  for (let i = 1; i < full.length; i++) {
    const sp = samples(full[i - 1], full[i], CELL); let ePrev = el(sp[0]);
    for (let k = 1; k < sp.length; k++) {
      const d = dist(sp[k - 1], sp[k]); len += d;
      const mid = { lat: (sp[k - 1].lat + sp[k].lat) / 2, lng: (sp[k - 1].lng + sp[k].lng) / 2 };
      const s = sandAt(G, mid); if (s != null && s > 0.5) sandy += d;
      if (drivenAt(G, mid)) drv += d;
      const rg = roughAt(G, mid); if (rg != null && rg > 0.5) rgh += d;
      const e1 = el(sp[k]);
      if (ePrev != null && e1 != null) { known += d; if (Math.atan2(Math.abs(e1 - ePrev), d) * 180 / Math.PI > slopeLim) breaks++; }
      ePrev = e1;
      far = Math.max(far, dist(hab, sp[k]));
    }
  }
  if (far > radius) breaks++;
  return { len, sandy: sandy / len, drv: drv / len, rough: rgh / len, known: known / len, breaks, far };
}

root.MarswalkCore = { R, CELL, M_PER_DEG, NIGHT_ID, dist, SITES, geom, themisTiles, loadThemis, buildGrid, elevAt, sandAt, roughAt, drivenAt, astar, routeTo, simplify, samples, routeMetrics };
})(window);

// Shared by the command and astronaut views: live stream, Earth-delay buffer, Mars map, formatting.
(function () {
  const RED = ['HELP', 'MANDOWN', 'EVAC'], AMBER = ['PREALARM', 'HAZARD'];
  const V = window.MW = {
    state: { tags: {}, base: null, events: [], units: {}, habitat: null, scale: 1, mode: null },
    delayMs: 0,          // 0 = habitat (live). Earth MCC sees the same feed 4-24 min late.
    listeners: [],
    queue: [],
    on(fn) { this.listeners.push(fn); },
    emit(kind, msg) { this.listeners.forEach(f => f(kind, msg)); },

    connect() {
      const es = new EventSource('/stream');
      es.onmessage = e => {
        const m = JSON.parse(e.data);
        m._rx = Date.now();
        if (m.kind === 'snapshot') { this.applySnapshot(m); return; }
        this.queue.push(m);
      };
      es.onerror = () => this.emit('conn', false);
      es.onopen = () => this.emit('conn', true);
      setInterval(() => this.drain(), 250);
    },
    applySnapshot(m) {
      Object.assign(this.state, { tags: m.tags || {}, base: m.base, events: m.events || [], units: m.units || {},
        habitat: m.habitat, scale: m.scale, mode: m.mode, started: m.started, frame: m.frame || 'mars', earth_origin: m.earth_origin });
      this.emit('snapshot', m);
    },
    drain() {
      const cut = Date.now() - this.delayMs;
      while (this.queue.length && this.queue[0]._rx <= cut) {
        const m = this.queue.shift();
        if (m.kind === 'reload') { location.reload(); return; }      // the site changed (Earth analog <-> Jezero)
        if (m.kind === 'tag') this.state.tags[m.tag.tag] = m.tag;
        if (m.kind === 'base') this.state.base = m.base;
        if (m.event) { this.state.events.push(m.event); this.state.events = this.state.events.slice(-300); }
        this.emit(m.kind, m);
      }
      this.emit('tick');
    },
    pending() { return this.queue.length; },

    async cmd(word, tag, arg) {
      const r = await fetch('/cmd', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ cmd: word, tag, arg }) });
      return r.json();
    },

    // ---- classification and formatting
    level(t) {
      if (!t) return 'mute';
      if (this.ageS(t.last_seen) > 60) return 'stale';
      if (RED.includes(t.state)) return 'bad';
      if (AMBER.includes(t.state)) return 'warn';
      return 'ok';
    },
    ageS(iso) { return iso ? Math.max(0, (Date.now() - this.delayMs - Date.parse(iso)) / 1000) : Infinity; },
    ago(iso) {
      const s = this.ageS(iso);
      if (!isFinite(s)) return 'never';
      return s < 60 ? Math.round(s) + ' s ago' : s < 3600 ? Math.round(s / 60) + ' min ago' : Math.round(s / 3600) + ' h ago';
    },
    loss(t) { if (!t.radio) return 'not measured'; const n = (t.rx || 0) + (t.lost || 0); return (n ? Math.round(100 * (t.lost || 0) / n) : 0) + ' %'; },
    // buddy ring: the buddy is somewhere within the measured separation of the tag (map scale applied)
    buddyRing(L, map, store, t) {
      const b = t.buddy, has = b && t.pos && b.dist_m != null && b.state !== 'unknown';
      if (!has) { if (store[t.tag]) { map.removeLayer(store[t.tag]); delete store[t.tag]; } return; }
      const bad = b.state === 'separated', r = Math.max(1, b.dist_m * (this.state.scale || 1));
      if (!store[t.tag]) store[t.tag] = L.circle([t.pos.lat, t.pos.lon], { radius: r, weight: 2, dashArray: '4 4', fillOpacity: .06 }).addTo(map);
      store[t.tag].setLatLng([t.pos.lat, t.pos.lon]).setRadius(r).setStyle({ color: bad ? '#ef6b6b' : '#7fb3e6' })
        .bindTooltip('Buddy is within ' + b.dist_m + ' m of this walker' + (bad ? ' (over the ' + b.limit_m + ' m limit)' : ''));
    },
    short(id) { return (id || '').replace('LEB10-', ''); },
    distM(a, b) {
      const R = this.state.frame === 'earth' ? 6371000 : 3396190, toR = Math.PI / 180, dLat = (b.lat - a.lat) * toR, dLon = (b.lon - a.lon) * toR;
      const s = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * toR) * Math.cos(b.lat * toR) * Math.sin(dLon / 2) ** 2;
      return 2 * R * Math.asin(Math.sqrt(s));
    },
    // vitals: never invent a number. Missing sensor -> "not fitted", sensor present but no value -> "no reading".
    vital(t, key, sensorKey, fmt) {
      const fitted = t && t.sensors ? t.sensors[sensorKey] : undefined;
      const v = t ? t[key] : null;
      if (v !== null && v !== undefined) return { txt: fmt(v), cls: '' };
      if (fitted === false) return { txt: 'not fitted', cls: 'mute' };
      return { txt: 'no reading', cls: 'mute' };
    },

    // ---- Ground at a point: slope from the CTX terrain grid (same grid as the planner) and mapped units
    //      from the USGS 1:75K Jezero geologic map (SIM 3464). Both are orbital data, so they say
    //      nothing about features smaller than ~30 m (rocks, small pits): that is what Identify is for.
    ground: {
      ready: null, SLOPE_LIM: 15,
      load() {
        if (this.ready) return this.ready;
        const JEZ = [[18.3067994, 77.2229331], [18.669315, 77.583964]], R = 3396190, MPD = R * Math.PI / 180;
        this.lat0 = JEZ[1][0]; this.lon0 = JEZ[0][1]; this.cell = 30; this.mLat = MPD;
        this.mLon = MPD * Math.cos(((JEZ[0][0] + JEZ[1][0]) / 2) * Math.PI / 180);
        this.ready = Promise.all([
          fetch('/data/jez_dtm_30m.json').then(r => r.json()),
          fetch('/data/jez_dtm_30m.i16').then(r => r.arrayBuffer()),
          fetch('/data/sim3464_walk.geojson').then(r => r.json()),
        ]).then(([meta, buf, geo]) => {
          this.nx = meta.nx; this.ny = meta.ny; this.dtm = new Int16Array(buf);
          this.geo = geo;
          this.polys = geo.features.map(f => {          // flatten to rings with a bounding box for fast tests
            const rings = f.geometry.type === 'Polygon' ? [f.geometry.coordinates] : f.geometry.coordinates;
            let b = [180, 90, -180, -90];
            rings.forEach(p => p[0].forEach(([x, y]) => { b = [Math.min(b[0], x), Math.min(b[1], y), Math.max(b[2], x), Math.max(b[3], y)]; }));
            return { u: f.properties.u, rings, b };
          });
          return this;
        });
        return this.ready;
      },
      elev(ix, iy) { if (ix < 0 || iy < 0 || ix >= this.nx || iy >= this.ny) return NaN; const v = this.dtm[iy * this.nx + ix]; return v === -32768 ? NaN : v / 10; },
      cellOf(lat, lon) { return [Math.floor((lon - this.lon0) * this.mLon / this.cell), Math.floor((this.lat0 - lat) * this.mLat / this.cell)]; },
      slopeAt(ix, iy) {                                 // steepest gradient over the 3x3 neighbourhood, degrees
        const e = (x, y) => this.elev(x, y), dx = (e(ix + 1, iy) - e(ix - 1, iy)) / (2 * this.cell), dy = (e(ix, iy + 1) - e(ix, iy - 1)) / (2 * this.cell);
        const s = Math.atan(Math.hypot(dx, dy)) * 180 / Math.PI; return isNaN(s) ? null : s;
      },
      unitAt(lat, lon) {
        const inRing = (ring) => { let c = false; for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) { const [xi, yi] = ring[i], [xj, yj] = ring[j]; if (((yi > lat) !== (yj > lat)) && lon < (xj - xi) * (lat - yi) / (yj - yi) + xi) c = !c; } return c; };
        for (const p of this.polys) {
          if (lon < p.b[0] || lon > p.b[2] || lat < p.b[1] || lat > p.b[3]) continue;
          for (const poly of p.rings) if (inRing(poly[0]) && !poly.slice(1).some(inRing)) return p.u;
        }
        return null;
      },
      // what is around a position: slope here, nearest steep cell within `radius` m (with bearing), mapped unit here and nearby
      around(lat, lon, radius = 90) {
        if (!this.dtm) return null;
        const [cx, cy] = this.cellOf(lat, lon), r = Math.ceil(radius / this.cell);
        const here = this.slopeAt(cx, cy);
        let steep = null;
        for (let dy = -r; dy <= r; dy++) for (let dx = -r; dx <= r; dx++) {
          const d = Math.hypot(dx, dy) * this.cell; if (d > radius || (dx === 0 && dy === 0)) continue;
          const s = this.slopeAt(cx + dx, cy + dy);
          if (s != null && s > this.SLOPE_LIM && (!steep || d < steep.dist)) steep = { dist: d, slope: s, bearing: (Math.atan2(dx, -dy) * 180 / Math.PI + 360) % 360 };
        }
        const unit = this.unitAt(lat, lon);
        let nearSand = null;                            // nearest mapped sand within radius, checked on a 15 m ring grid
        if (unit !== 'Aeb') for (let d = 15; d <= radius && !nearSand; d += 15) for (let a = 0; a < 360; a += 30) {
          const la = lat + d * Math.cos(a * Math.PI / 180) / this.mLat, lo = lon + d * Math.sin(a * Math.PI / 180) / this.mLon;
          if (this.unitAt(la, lo) === 'Aeb') { nearSand = { dist: d, bearing: a }; break; }
        }
        return { slope: here, steep, unit, nearSand, inGrid: here != null };
      },
      compass(b) { return ['north', 'north-east', 'east', 'south-east', 'south', 'south-west', 'west', 'north-west'][Math.round(b / 45) % 8]; },
      layer(L) {                                        // Leaflet layer of the mapped sand and smooth units
        return L.geoJSON(this.geo, { interactive: false, style: f => f.properties.u === 'Aeb'
          ? { color: '#e5b64a', weight: 1, fillColor: '#e5b64a', fillOpacity: 0.28 }
          : { color: '#a3978a', weight: 1, dashArray: '3 3', fillOpacity: 0.08 } });
      },
    },

    // ---- Mars map (same projection and Trek tiles as the planner)
    post(path, body) { return fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(r => r.json()); },
    // phone or laptop location, after the browser's permission prompt
    locate() {
      return new Promise((res, rej) => {
        if (!navigator.geolocation) return rej(new Error('this browser has no location service'));
        navigator.geolocation.getCurrentPosition(p => res({ lat: p.coords.latitude, lon: p.coords.longitude, acc: Math.round(p.coords.accuracy) }),
          e => rej(new Error(e.code === 1 ? 'location permission was refused' : !window.isSecureContext ? 'location needs the https address of the habitat' : 'no location fix')), { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 });
      });
    },
    pinIcon(L, colour) { return L.divIcon({ className: '', html: `<div style="width:14px;height:14px;border-radius:50% 50% 50% 0;transform:rotate(-45deg);background:${colour};border:2px solid #140c08"></div>`, iconSize: [14, 14], iconAnchor: [7, 14] }); },
    map(el, opts) {
      if (this.state.frame === 'earth') {            // Earth analog site: a real map at true scale
        const h = this.state.habitat, m = L.map(el, { center: [h.lat, h.lon], zoom: 20, maxZoom: 22 });
        L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxNativeZoom: 19, maxZoom: 22, attribution: '&copy; OpenStreetMap contributors' }).addTo(m);
        L.control.scale({ imperial: false }).addTo(m);
        return m;
      }
      const MarsCRS = L.extend({}, L.CRS.EPSG4326, { R: 3396190 });
      const h = this.state.habitat || { lat: 18.444627, lon: 77.450886 };
      const map = L.map(el, Object.assign({ crs: MarsCRS, center: [h.lat, h.lon], zoom: 15, minZoom: 8, maxZoom: 19, zoomControl: true }, opts || {}));
      const t = (id, z, ext, b) => L.tileLayer('https://trek.nasa.gov/tiles/Mars/EQ/' + id + '/1.0.0/default/default028mm/{z}/{y}/{x}.' + ext,
        { maxNativeZoom: z, maxZoom: 19, noWrap: true, bounds: b ? L.latLngBounds(b) : undefined });
      t('Mars_MOLA_blend200ppx_HRSC_ClrShade_clon0dd_200mpp_lzw', 8, 'jpg').addTo(map);
      t('JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0', 13, 'png', [[18.2110274, 77.1604655], [18.7211945, 77.6991776]]).addTo(map);
      t('JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first_dd', 17, 'png', [[18.3067994, 77.2229331], [18.669315, 77.583964]]).addTo(map);
      L.control.scale({ imperial: false }).addTo(map);
      map.attributionControl.addAttribution('Tiles: NASA Mars Trek (HiRISE, CTX, MOLA/HRSC)');
      return map;
    },
  };
})();

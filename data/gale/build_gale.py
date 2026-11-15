# Builds the Gale Crater walk-site files around Curiosity's traverse. Nothing here comes from another site.
#   gale_traverse.json     Curiosity's drives (NASA MMGIS MSL_traverse + MSL_waypoints), thinned, with the sol of each drive
#                          and the rover's measured tilt at the end of each drive
#   gale_dtm_30m.i16       planner grid elevation: mean of 1 m HiRISE DTM posts per 30 m cell, decimetres above OFFSET_M,
#                          -32768 = no DTM (not characterized). Three DTMs are mosaicked; where they overlap the first in DTMS wins.
#   gale_fslope_30m.u8     steepest 3 m slope inside each cell (3x3 median first), quarter degrees, 255 = no DTM
#   gale_elev_fill_30m.i16 3D display only: the mosaic, else MOLA 128 px/deg shifted to match
#   gale_ortho.webp        HiRISE orthoimages of the same three DTMs, 4 m, mosaicked on the grid, transparent elsewhere
#   gale_grid.json         bounds, sources, DTM-minus-rover check, method notes
# usage: python build_gale.py <cache-dir>   (about 1.1 GB of DTMs and orthos are cached there, not in the repo)
import json, math, os, re, sys, time, urllib.request
import numpy as np
from PIL import Image
from scipy import ndimage as nd

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
CACHE = sys.argv[1] if len(sys.argv) > 1 else HERE
R_APP = 3396190.0; MPD = R_APP * math.pi / 180; CELL = 30; OFFSET_M = -4000
NORTH, SOUTH, WEST, EAST = -4.565, -4.86, 137.33, 137.47                     # Curiosity's traverse plus about 1.5 km
PDS = 'https://hirise-pds.lpl.arizona.edu/PDS/DTM/ESP/'
DTMS = [  # (folder, DTM, ortho): middle of the route first, then the landing area, then the south end
    ('ORB_040700_040799/ESP_040770_1755_ESP_039280_1755/', 'DTEEC_040770_1755_039280_1755_A01.IMG', 'ESP_040770_1755_RED_C_01_ORTHO.JP2'),
    ('ORB_023900_023999/ESP_023957_1755_ESP_024023_1755/', 'DTEEC_023957_1755_024023_1755_U01.IMG', 'ESP_023957_1755_RED_C_01_ORTHO.JP2'),
    ('ORB_019600_019699/ESP_019698_1750_ESP_019988_1750/', 'DTEEC_019698_1750_019988_1750_U01.IMG', 'ESP_019698_1750_RED_C_01_ORTHO.JP2'),
]
MMGIS = 'https://mars.nasa.gov/mmgis-maps/MSL/Layers/json/'

def get(url, rng=None, tries=6):
    req = urllib.request.Request(url, headers={'User-Agent': 'marswalk-gale-builder'})
    if rng: req.add_header('Range', 'bytes=%d-%d' % rng)
    for n in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=900) as r: return r.read()
        except OSError:
            if n == tries - 1: raise
            time.sleep(3 * (n + 1))
def cached(url, name):
    p = os.path.join(CACHE, name)
    if not os.path.exists(p):
        tmp = p + '.part'; open(tmp, 'wb').write(get(url)); os.replace(tmp, p)
    return p
def label(path=None, text=None):
    t = text if text is not None else open(path, 'rb').read(60000).decode('latin-1')
    def g(k, opt=False):
        m = re.search(r'\n\s*' + k + r'\s*=\s*([-\d.]+)', t)
        return 0 if (m is None and opt) else float(m.group(1))
    return dict(rec=int(g('RECORD_BYTES', True)), img=int(g(r'\^IMAGE', True)), nl=int(g('LINES')), ns=int(g('LINE_SAMPLES')), scale=g('MAP_SCALE'),
                clat=g('CENTER_LATITUDE'), clon=g('CENTER_LONGITUDE'), lpo=g('LINE_PROJECTION_OFFSET'), spo=g('SAMPLE_PROJECTION_OFFSET'), r=g('A_AXIS_RADIUS') * 1000)

latC = (NORTH + SOUTH) / 2; mLon = MPD * math.cos(math.radians(latC)); mLat = MPD
nx = math.ceil((EAST - WEST) * mLon / CELL); ny = math.ceil((NORTH - SOUTH) * mLat / CELL); n = nx * ny
print('grid', nx, 'x', ny)
mean = np.full(n, np.nan); src = np.full(n, -1, np.int8); fs = np.full(n, -1.0)
OW, OH = int(round((EAST - WEST) * mLon / 4)), int(round((NORTH - SOUTH) * mLat / 4)); ortho = np.zeros((OH, OW), np.float32)
used = []
for k, (folder, dname, oname) in enumerate(DTMS):
    dp = cached(PDS + folder + dname, dname); L = label(dp)
    lat_of = lambda l: np.degrees((L['lpo'] - l) * L['scale'] / L['r'])
    lon_of = lambda s: L['clon'] + np.degrees((s - L['spo']) * L['scale'] / (L['r'] * math.cos(math.radians(L['clat']))))
    cy = ((NORTH - lat_of(np.arange(L['nl']))) * mLat / CELL).astype(int); cx = ((lon_of(np.arange(L['ns'])) - WEST) * mLon / CELL).astype(int)
    iny = (cy >= 0) & (cy < ny); inx = (cx >= 0) & (cx < nx)
    dtm = np.memmap(dp, dtype='<f4', mode='r', offset=(L['img'] - 1) * L['rec'], shape=(L['nl'], L['ns']))
    s = np.zeros(n); c = np.zeros(n); B3 = 3; e3 = np.full((L['nl'] // B3, L['ns'] // B3), np.nan, np.float32)
    for r0 in range(0, L['nl'] - L['nl'] % B3, 600):
        blk = np.array(dtm[r0:r0 + 600]); r1 = r0 + blk.shape[0]
        ok = (blk > -1e30) & iny[r0:r1, None] & inx[None, :]
        idx = np.clip(cy[r0:r1, None], 0, ny - 1) * nx + np.clip(cx[None, :], 0, nx - 1)
        s += np.bincount(idx[ok], weights=blk[ok], minlength=n); c += np.bincount(idx[ok], minlength=n)
        h = (blk.shape[0] // B3) * B3; w = (L['ns'] // B3) * B3
        b = np.where(blk > -1e30, blk, np.nan)[:h, :w].reshape(h // B3, B3, w // B3, B3)
        with np.errstate(all='ignore'): e3[r0 // B3:r0 // B3 + h // B3] = np.nanmean(b, axis=(1, 3))
    valid = c > 0.5 * (CELL / L['scale']) ** 2; take = valid & np.isnan(mean)
    mean[take] = (s / np.maximum(c, 1))[take]; src[take] = k
    both = valid & ~take & ~np.isnan(mean)
    off = float(np.median((s / np.maximum(c, 1))[both] - mean[both])) if both.any() else None
    # 3 m slope, maximum per cell, only in cells this DTM supplies
    gy, gx = np.gradient(np.nan_to_num(e3, nan=0.0), B3 * L['scale']); sl = np.degrees(np.arctan(np.hypot(gx, gy)))
    sl[nd.binary_dilation(~np.isfinite(e3), iterations=1)] = np.nan
    slm = nd.median_filter(np.nan_to_num(sl, nan=0.0), size=3); slm[np.isnan(sl)] = np.nan
    yy = cy[np.arange(e3.shape[0]) * B3 + 1]; xx = cx[np.arange(e3.shape[1]) * B3 + 1]
    okc = np.isfinite(slm) & ((yy >= 0) & (yy < ny))[:, None] & ((xx >= 0) & (xx < nx))[None, :]
    idx3 = np.clip(yy, 0, ny - 1)[:, None] * nx + np.clip(xx, 0, nx - 1)[None, :]
    tmp = np.full(n, -1.0); np.maximum.at(tmp, idx3[okc], slm[okc]); fs[take] = tmp[take]
    # ortho at 4 m (JPEG 2000 reduce 2), placed into the grid mosaic where empty
    op = cached(PDS + folder + oname, oname); Image.MAX_IMAGE_PIXELS = None
    OL = label(text=get(PDS + folder + oname[:-4] + '.LBL').decode('latin-1'))               # the ortho has its own grid
    im = Image.open(op); assert im.size == (OL['ns'], OL['nl']), ('ortho label and image differ', oname, im.size); im.reduce = 2
    try: im.load(); o = np.asarray(im.convert('L')).astype(np.float32)
    except OSError:                                                                  # some JP2s fail to decode at 1/4: use 1/2 and box-reduce
        im = Image.open(op); im.reduce = 1; im.load(); o2 = np.asarray(im.convert('L'))
        o = np.asarray(Image.fromarray(o2).resize((o2.shape[1] // 2, o2.shape[0] // 2), Image.BOX)).astype(np.float32)
    f4 = OL['ns'] / o.shape[1]
    oy, ox = np.mgrid[0:OH, 0:OW]; olat = NORTH - (oy + .5) * (NORTH - SOUTH) / OH; olon = WEST + (ox + .5) * (EAST - WEST) / OW
    ll = (OL['lpo'] - np.radians(olat) * OL['r'] / OL['scale']) / f4; ss = (OL['spo'] + np.radians(olon - OL['clon']) * OL['r'] * math.cos(math.radians(OL['clat'])) / OL['scale']) / f4
    v = nd.map_coordinates(o, [ll, ss], order=1, cval=0); put = (ortho == 0) & (v > 0); ortho[put] = v[put]
    used.append(dict(dtm=dname[:-4], ortho=oname[:-4], cells=int(take.sum()), median_offset_vs_mosaic_m=off))
    print(dname, 'cells', int(take.sum()), 'offset in overlap', off)
mean = mean.reshape(ny, nx); fs = fs.reshape(ny, nx)
print('mosaic valid', round(float(np.isfinite(mean).mean()), 3), np.nanmin(mean), np.nanmax(mean))
assert -3276 < np.nanmin(mean) - OFFSET_M and np.nanmax(mean) - OFFSET_M < 3276
np.where(np.isnan(mean), -32768, np.round((mean - OFFSET_M) * 10)).astype('<i2').tofile(os.path.join(HERE, 'gale_dtm_30m.i16'))
np.where(fs < 0, 255, np.clip(np.round(fs * 4), 0, 254)).astype('u1').tofile(os.path.join(HERE, 'gale_fslope_30m.u8'))
lo, hi = np.percentile(ortho[ortho > 0], [0.5, 99.5]); gch = np.clip((ortho - lo) / (hi - lo) * 254 + 1, 1, 255).astype(np.uint8)
Image.fromarray(np.dstack([gch, gch, gch, np.where(ortho > 0, 255, 0).astype(np.uint8)]), 'RGBA').save(os.path.join(HERE, 'gale_ortho.webp'), quality=78, method=6)

# ---- MOLA fill for the 3D display (tile 0..44 S, 90..180 E)
MB = 'https://pds-geosciences.wustl.edu/mgs/mgs-m-mola-5-megdr-l3-v1/mgsl_300x/meg128/'
P = 128; r0 = int(-NORTH * P) - 2; r1 = int(-SOUTH * P) + 3; c0 = int((WEST - 90) * P) - 2; c1 = int((EAST - 90) * P) + 3
topo = np.array([np.frombuffer(get(MB + 'megt00n090hb.img', (r * 23040 + c0 * 2, r * 23040 + c1 * 2 - 1)), '>i2') for r in range(r0, r1)], float)
ys, xs = np.mgrid[0:ny, 0:nx]; glat = NORTH - (ys + .5) * CELL / mLat; glon = WEST + (xs + .5) * CELL / mLon
mola = nd.map_coordinates(topo, [-glat * P - .5 - r0, (glon - 90) * P - .5 - c0], order=1)
shift = float(np.nanmedian(mean - mola)); fill = np.where(np.isnan(mean), mola + shift, mean)
fill = nd.gaussian_filter(fill, 1.0) * np.isnan(mean) + np.nan_to_num(mean) * ~np.isnan(mean)
np.round((fill - OFFSET_M) * 10).astype('<i2').tofile(os.path.join(HERE, 'gale_elev_fill_30m.i16'))

# ---- Curiosity's traverse: drives with sols (from the waypoint nearest each drive's end) and measured tilt
trav = json.loads(get(MMGIS + 'MSL_traverse.json')); wps = json.loads(get(MMGIS + 'MSL_waypoints.json'))['features']
W = np.array([[f['properties']['lon'], f['properties']['lat']] for f in wps]); WS = [f['properties'] for f in wps]
def lines(g): return [g['coordinates']] if g['type'] == 'LineString' else g['coordinates']
segs = []
for f in trav['features']:
    for ln in lines(f['geometry']):
        end = ln[-1]; j = int(np.argmin((W[:, 0] - end[0]) ** 2 + (W[:, 1] - end[1]) ** 2)); w = WS[j]
        pts = [[round(p[0], 6), round(p[1], 6), round(p[2], 1) if len(p) > 2 else None] for p in ln]
        segs.append({'sol': w['sol'], 'len': round(sum(math.hypot((b[0] - a[0]) * mLon, (b[1] - a[1]) * mLat) for a, b in zip(ln, ln[1:])), 1), 'pts': pts})
segs.sort(key=lambda s: s['sol'])
tilts = [[round(w['lon'], 6), round(w['lat'], 6), w['sol'], w['tilt']] for w in WS if w.get('tilt') is not None]
json.dump({'source': MMGIS + 'MSL_traverse.json and MSL_waypoints.json (NASA/JPL-Caltech MMGIS)', 'segments': segs, 'tilts': tilts,
           'last_sol': WS[-1]['sol'], 'total_km': WS[-1]['dist_km']}, open(os.path.join(HERE, 'gale_traverse.json'), 'w'), separators=(',', ':'))
# DTM minus rover elevation (rover elevations are geoid-referenced, as the DTMs are)
rp = np.array([[p[1], p[0], p[2]] for s in segs for p in s['pts'] if p[2] is not None])
ci = ((NORTH - rp[:, 0]) * mLat / CELL).astype(int); cj = ((rp[:, 1] - WEST) * mLon / CELL).astype(int)
okp = (ci >= 0) & (ci < ny) & (cj >= 0) & (cj < nx); dv = mean[ci[okp], cj[okp]] - rp[okp, 2]; dv = dv[np.isfinite(dv)]
check = dict(n=int(dv.size), mean=round(float(dv.mean()), 2), median=round(float(np.median(dv)), 2), std=round(float(dv.std()), 2), p95abs=round(float(np.percentile(np.abs(dv), 95)), 2))
print('DTM minus rover', check, 'segments', len(segs), 'last sol', WS[-1]['sol'])

json.dump(dict(bounds=[[SOUTH, WEST], [NORTH, EAST]], nx=nx, ny=ny, cell=CELL,
    dtm=dict(file='gale_dtm_30m.i16', units='decimetres above offset_m', offset_m=OFFSET_M, nodata=-32768, dtms=used,
             method='mean of 1 m HiRISE posts per 30 m cell; cells with under half coverage are no-data; overlaps: first DTM in the list wins',
             valid_share=round(float(np.isfinite(mean).mean()), 4), dtm_minus_rover_m=check),
    fine_slope=dict(file='gale_fslope_30m.u8', units='quarter degrees', nodata=255),
    fill=dict(file='gale_elev_fill_30m.i16', units='decimetres above offset_m', offset_m=OFFSET_M, use='3D display only; MOLA shifted by %.1f m outside the DTMs' % shift),
    ortho=dict(file='gale_ortho.webp', bounds=[[SOUTH, WEST], [NORTH, EAST]], px=[OW, OH], scale_m=4, credit='NASA/JPL/University of Arizona'),
    traverse=dict(file='gale_traverse.json', last_sol=WS[-1]['sol'], total_km=WS[-1]['dist_km'])), open(os.path.join(HERE, 'gale_grid.json'), 'w'), indent=1)
print('done')

# Builds a HiRISE walk tile for one site: DTM mosaic on the planner's 30 m grid, 3 m fine slope, 4 m ortho mosaic,
# MOLA fill for the 3D view, and (rover sites) the rover traverse. Shared by Olympus Mons, Gusev and Meridiani.
#   <pre>_dtm_30m.i16, <pre>_fslope_30m.u8, <pre>_elev_fill_30m.i16, <pre>_ortho.webp, <pre>_grid.json, [<pre>_traverse.json]
# usage: python build_tile.py <olympus|gusev|meridiani> <cache-dir>
import json, math, os, re, sys, time, urllib.request
import numpy as np
from PIL import Image
from scipy import ndimage as nd

HERE = os.path.dirname(os.path.abspath(__file__)); SITE = sys.argv[1]; CACHE = sys.argv[2] if len(sys.argv) > 2 else HERE
R_APP = 3396190.0; MPD = R_APP * math.pi / 180; CELL = 30
PDS = 'https://hirise-pds.lpl.arizona.edu/PDS/DTM/'
MERT = 'https://an.rsl.wustl.edu/mera/AN/meri/MER/traverse/'
CFG = {
  # Olympus Mons basal scarp, west flank (HiRISE team rationale "Layers in Olympus Mons basal scarp")
  'olympus': dict(pre='oly', offset=6000, bounds=None,
      dtms=[('PSP/ORB_001400_001499/PSP_001432_2015_PSP_001630_2015/', 'DTEEC_001432_2015_001630_2015_U01.IMG', 'PSP_001432_2015_RED_C_01_ORTHO.JP2')], trav=None),
  # Gusev: Spirit's landing site to the Columbia Hills and Home Plate (rationale "Possible location of Spirit Rover in Columbia Hills")
  'gusev': dict(pre='gus', offset=-2000, bounds=None,
      dtms=[('PSP/ORB_001500_001599/PSP_001513_1655_PSP_001777_1650/', 'DTEEC_001513_1655_001777_1650_U01.IMG', 'PSP_001777_1650_RED_C_01_ORTHO.JP2')], trav='mera'),
  # Meridiani: Eagle crater to Victoria crater (rationale "Victoria Crater")
  'meridiani': dict(pre='mer', offset=-1400, bounds=None,
      dtms=[('ESP/ORB_021700_021799/ESP_021747_1780_ESP_022380_1780/', 'DTEEC_021747_1780_022380_1780_U01.IMG', 'ESP_021747_1780_RED_C_01_ORTHO.JP2')], trav='merb',
      # Placing the local track at the published landing point left it about 140 m north-west of Victoria's rim in this DTM.
      # Fitting the rim drive (sols 951-1290) to the rim crest measured in the DTM (radius 416 m) moved it 107 m east and 86 m south
      # (rms distance to the rim 117 m before, 25 m after). The anchor below is that fitted landing point.
      anchor=(-1.947646, -5.524786), anchor_note='placed at the landing point fitted to Victoria crater in this DTM (shift 107 m east, 86 m south of the published landing point; rim fit 25 m rms)'),
}[SITE]
PRE, OFFSET_M, DTMS = CFG['pre'], CFG['offset'], CFG['dtms']
OUT = os.path.join(HERE, SITE); os.makedirs(OUT, exist_ok=True)

def get(url, rng=None, tries=6):
    req = urllib.request.Request(url, headers={'User-Agent': 'marswalk-tile-builder'})
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


# grid bounds: the first DTM's bounding box unless given (map longitudes, -180..180)
if CFG['bounds']: (SOUTH, WEST), (NORTH, EAST) = CFG['bounds']
else:
    L0 = label(cached(PDS + DTMS[0][0] + DTMS[0][1], DTMS[0][1]))
    NORTH = math.degrees(L0['lpo'] * L0['scale'] / L0['r']); SOUTH = math.degrees((L0['lpo'] - L0['nl'] + 1) * L0['scale'] / L0['r'])
    k = L0['r'] * math.cos(math.radians(L0['clat']))
    WEST = L0['clon'] + math.degrees((0 - L0['spo']) * L0['scale'] / k); EAST = L0['clon'] + math.degrees((L0['ns'] - 1 - L0['spo']) * L0['scale'] / k)
    WEST, EAST = (WEST + 180) % 360 - 180, (EAST + 180) % 360 - 180
print(SITE, 'bounds', SOUTH, WEST, NORTH, EAST)
latC = (NORTH + SOUTH) / 2; mLon = MPD * math.cos(math.radians(latC)); mLat = MPD
nx = math.ceil((EAST - WEST) * mLon / CELL); ny = math.ceil((NORTH - SOUTH) * mLat / CELL); n = nx * ny
print('grid', nx, 'x', ny)
mean = np.full(n, np.nan); src = np.full(n, -1, np.int8); fs = np.full(n, -1.0)
OW, OH = int(round((EAST - WEST) * mLon / 4)), int(round((NORTH - SOUTH) * mLat / 4)); ortho = np.zeros((OH, OW), np.float32)
used = []
for k, (folder, dname, oname) in enumerate(DTMS):
    dp = cached(PDS + folder + dname, dname); L = label(dp)
    lat_of = lambda l: np.degrees((L['lpo'] - l) * L['scale'] / L['r'])
    lon_of = lambda s: (L['clon'] + np.degrees((s - L['spo']) * L['scale'] / (L['r'] * math.cos(math.radians(L['clat'])))) + 180) % 360 - 180
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
    ll = (OL['lpo'] - np.radians(olat) * OL['r'] / OL['scale']) / f4; ss = (OL['spo'] + np.radians(((olon - OL['clon']) + 180) % 360 - 180) * OL['r'] * math.cos(math.radians(OL['clat'])) / OL['scale']) / f4
    v = nd.map_coordinates(o, [ll, ss], order=1, cval=0); put = (ortho == 0) & (v > 0); ortho[put] = v[put]
    used.append(dict(dtm=dname[:-4], ortho=oname[:-4], cells=int(take.sum()), median_offset_vs_mosaic_m=off))
    print(dname, 'cells', int(take.sum()), 'offset in overlap', off)
mean = mean.reshape(ny, nx); fs = fs.reshape(ny, nx)
print('mosaic valid', round(float(np.isfinite(mean).mean()), 3), np.nanmin(mean), np.nanmax(mean))
assert -3276 < np.nanmin(mean) - OFFSET_M and np.nanmax(mean) - OFFSET_M < 3276
np.where(np.isnan(mean), -32768, np.round((mean - OFFSET_M) * 10)).astype('<i2').tofile(os.path.join(OUT, PRE + '_dtm_30m.i16'))
np.where(fs < 0, 255, np.clip(np.round(fs * 4), 0, 254)).astype('u1').tofile(os.path.join(OUT, PRE + '_fslope_30m.u8'))
lo, hi = np.percentile(ortho[ortho > 0], [0.5, 99.5]); gch = np.clip((ortho - lo) / (hi - lo) * 254 + 1, 1, 255).astype(np.uint8)
Image.fromarray(np.dstack([gch, gch, gch, np.where(ortho > 0, 255, 0).astype(np.uint8)]), 'RGBA').save(os.path.join(OUT, PRE + '_ortho.webp'), quality=78, method=6)


# ---- MOLA fill for the 3D display (128 px/deg tile containing the grid)
MB = 'https://pds-geosciences.wustl.edu/mgs/mgs-m-mola-5-megdr-l3-v1/mgsl_300x/meg128/'
P = 128; latT = 44 if NORTH > 0 else 0; lon360 = WEST % 360; lonT = int(lon360 // 90) * 90
tile = ('megt44n%03dhb.img' if latT == 44 else 'megt00n%03dhb.img') % lonT
r0 = int((latT - NORTH) * P) - 2; r1 = int((latT - SOUTH) * P) + 3; c0 = int((lon360 - lonT) * P) - 2; c1 = int((EAST % 360 - lonT) * P) + 3
topo = np.array([np.frombuffer(get(MB + tile, (r * 23040 + c0 * 2, r * 23040 + c1 * 2 - 1)), '>i2') for r in range(r0, r1)], float)
ys, xs = np.mgrid[0:ny, 0:nx]; glat = NORTH - (ys + .5) * CELL / mLat; glon = WEST + (xs + .5) * CELL / mLon
mola = nd.map_coordinates(topo, [(latT - glat) * P - .5 - r0, (glon % 360 - lonT) * P - .5 - c0], order=1)
shift = float(np.nanmedian(mean - mola)); fill = np.where(np.isnan(mean), mola + shift, mean)
fill = nd.gaussian_filter(fill, 1.0) * np.isnan(mean) + np.nan_to_num(mean) * ~np.isnan(mean)
fill = np.clip(fill, OFFSET_M - 3276, OFFSET_M + 3276)                       # display only: MOLA outside the DTM may exceed the range
np.round((fill - OFFSET_M) * 10).astype('<i2').tofile(os.path.join(OUT, PRE + '_elev_fill_30m.i16'))
print('MOLA', tile, 'shift', round(shift, 1))

# ---- rover traverse (Tim Parker / PDS Geosciences Node corrected MER traverses, via the Mars Analysis Node at WUSTL)
trav_meta = None
if CFG['trav']:
    rows = [l.split(',') for l in get(MERT + ('MERA_traverse.csv' if CFG['trav'] == 'mera' else 'MERB_traverse_5130.csv')).decode().strip().splitlines()[1:]]
    if CFG['trav'] == 'mera':
        # Plate Carree, sphere 3396190 m, central meridian 175.5 E (label of MERA_traverse and of the HiRISE basemap from PSP_001777_1650)
        ll = [(math.degrees(float(r[8]) / R_APP), 175.5 + math.degrees(float(r[7]) / R_APP), int(r[2]), int(r[3])) for r in rows]
        frame = 'Plate Carree, central meridian 175.5 E, sphere 3396190 m, registered to HiRISE PSP_001777_1650 (an image of this DTM pair)'
    else:
        # local metres from the lander, x east and y north, placed at the published landing point (checked against Victoria crater)
        LAT0, LON0 = CFG.get('anchor', (-1.9462, 354.4734 - 360))
        ll = [(LAT0 + float(r[8]) / mLat, LON0 + float(r[7]) / mLon, int(r[2]), int(r[3])) for r in rows]
        frame = 'local metres from the lander (x east, y north), ' + CFG.get('anchor_note', 'placed at the published landing point 1.9462 S, 354.4734 E')
    segs = []; cur = None
    for la, lo, s0, s1 in ll:
        p = [round(lo, 6), round(la, 6), None]
        if cur is None or s1 != cur['sol']:
            if cur and len(cur['pts']) > 1: segs.append(cur)
            cur = {'sol': s1, 'pts': [cur['pts'][-1]] if cur else []}
        if not cur['pts'] or cur['pts'][-1][:2] != p[:2]: cur['pts'].append(p)
    if cur and len(cur['pts']) > 1: segs.append(cur)
    for sg in segs: sg['len'] = round(sum(math.hypot((b[0] - a[0]) * mLon, (b[1] - a[1]) * mLat) for a, b in zip(sg['pts'], sg['pts'][1:])), 1)
    json.dump({'source': MERT, 'frame': frame, 'segments': segs}, open(os.path.join(OUT, PRE + '_traverse.json'), 'w'), separators=(',', ':'))
    inb = [p for sg in segs for p in sg['pts'] if SOUTH < p[1] < NORTH and WEST < p[0] < EAST]
    trav_meta = dict(file=PRE + '_traverse.json', drives=len(segs), last_sol=segs[-1]['sol'], points_in_grid=len(inb), frame=frame)
    print('traverse', trav_meta)

json.dump(dict(bounds=[[SOUTH, WEST], [NORTH, EAST]], nx=nx, ny=ny, cell=CELL,
    dtm=dict(file=PRE + '_dtm_30m.i16', units='decimetres above offset_m', offset_m=OFFSET_M, nodata=-32768, dtms=used,
             method='mean of 1 m HiRISE posts per 30 m cell; cells with under half coverage are no-data', valid_share=round(float(np.isfinite(mean).mean()), 4),
             min_m=round(float(np.nanmin(mean)), 1), max_m=round(float(np.nanmax(mean)), 1)),
    fine_slope=dict(file=PRE + '_fslope_30m.u8', units='quarter degrees', nodata=255),
    fill=dict(file=PRE + '_elev_fill_30m.i16', offset_m=OFFSET_M, use='3D display only; MOLA %s shifted by %.1f m outside the DTM' % (tile, shift)),
    ortho=dict(file=PRE + '_ortho.webp', bounds=[[SOUTH, WEST], [NORTH, EAST]], px=[OW, OH], scale_m=4, credit='NASA/JPL/University of Arizona'),
    traverse=trav_meta), open(os.path.join(OUT, PRE + '_grid.json'), 'w'), indent=1)
print('done')

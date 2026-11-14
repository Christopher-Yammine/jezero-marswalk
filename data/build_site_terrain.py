# Cuts a MOLA elevation window around each globe site for the 3D view (3d.html?site=<id>).
# Source: MGS MOLA MEGDR (median topography, metres above the areoid), PDS Geosciences Node.
# Only the needed bytes are downloaded: each tile is a fixed-record big-endian int16 grid, so every
# map row is fetched with an HTTP range request.
# usage: python build_site_terrain.py [site ...]      (writes terrain/<id>.i16 and terrain/<id>.json)
import json, math, os, re, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
import numpy as np

BASE = 'https://pds-geosciences.wustl.edu/mgs/mgs-m-mola-5-megdr-l3-v1/mgsl_300x/'
DIRS = {128: 'meg128', 64: 'meg064', 32: 'meg032', 16: 'meg016'}
MAX_ROWS = 520   # rows kept after downsampling; keeps each file well under 1 MB

# id: (centre lat, centre lon east-positive, half-height deg, half-width deg). Windows frame the feature.
SITES = {
    'gale':      (-5.2, 137.6, 1.5, 1.6),
    'gusev':     (-14.6, 175.4, 1.6, 1.7),
    'meridiani': (-2.0, -5.4, 1.0, 1.2),
    'phoenix':   (68.22, -125.0, 1.2, 3.2),
    'arcadia':   (42.4, -148.0, 2.2, 2.0),   # HRSC orbit 26333 scene: walk grid at 41.4 N and the candidate rampart crater at 43.7 N
    'utopia':    (46.7, 117.5, 3.0, 4.4),
    'olympus':   (18.4, -133.8, 6.5, 7.2),
    'valles':    (-10.0, -66.0, 6.0, 14.0),
    'hellas':    (-42.0, 68.0, 22.0, 30.0),
}

def get(url, rng=None, tries=6):
    req = urllib.request.Request(url, headers={'User-Agent': 'marswalk-terrain-builder'})
    if rng: req.add_header('Range', 'bytes=%d-%d' % rng)
    for n in range(tries):  # the archive server drops the odd connection: back off and retry
        try:
            with urllib.request.urlopen(req, timeout=60) as r: return r.read()
        except OSError:
            if n == tries - 1: raise
            time.sleep(2 * (n + 1))

_tiles = {}
def tiles(ppd):
    """Tile list for one resolution, from the directory listing and each label."""
    if ppd in _tiles: return _tiles[ppd]
    d = BASE + DIRS[ppd] + '/'
    names = sorted(set(re.findall(r'(megt\w+?)\.lbl', get(d).decode(), re.I)))
    out = []
    for n in names:
        lbl = get(d + n + '.lbl').decode()
        f = lambda k: float(re.search(k + r'\s*=\s*(-?[\d.]+)', lbl).group(1))
        out.append(dict(url=d + n + '.img', lines=int(f('LINES')), samples=int(f(r'\bLINE_SAMPLES')), rec=int(f('RECORD_BYTES')),
                        north=f('MAXIMUM_LATITUDE'), south=f('MINIMUM_LATITUDE'), west=f('WESTERNMOST_LONGITUDE'), east=f('EASTERNMOST_LONGITUDE')))
    _tiles[ppd] = out; return out

def window(lat_c, lon_c, hlat, hlon):
    # pick the finest resolution that keeps the row count reasonable; downsample the rest
    ppd = next(p for p in (128, 64, 32, 16) if 2 * hlat * p <= MAX_ROWS * 1.5 or p == 16)
    north, south = lat_c + hlat, lat_c - hlat
    west, east = (lon_c - hlon) % 360, (lon_c + hlon) % 360        # MEGDR longitudes are 0..360 east
    r0, r1 = round((90 - north) * ppd), round((90 - south) * ppd)  # global row indices
    ncol = round(2 * hlon * ppd); c0 = round(west * ppd)
    T = tiles(ppd)
    grid = np.zeros((r1 - r0, ncol), np.int16)
    jobs = []
    for gr in range(r0, r1):
        lat = 90 - (gr + .5) / ppd
        c = 0  # split each row at tile edges
        while c < ncol:
            lon = ((c0 + c) % (360 * ppd) + .5) / ppd
            t = next(t for t in T if t['south'] <= lat < t['north'] and t['west'] <= lon < t['east'])
            tr = round((t['north'] - lat) * ppd - .5); tc = round((lon - t['west']) * ppd - .5)
            n = min(ncol - c, t['samples'] - tc)
            jobs.append((gr - r0, c, t, tr, tc, n)); c += n
    def run(j):
        row, c, t, tr, tc, n = j
        off = tr * t['rec'] + tc * 2
        grid[row, c:c + n] = np.frombuffer(get(t['url'], (off, off + 2 * n - 1)), '>i2')
    with ThreadPoolExecutor(4) as ex: list(ex.map(run, jobs))
    k = max(1, math.ceil(grid.shape[0] / MAX_ROWS))
    if k > 1:  # block-average
        h, w = grid.shape[0] // k * k, grid.shape[1] // k * k
        grid = grid[:h, :w].reshape(h // k, k, w // k, k).astype(np.float64).mean((1, 3)).round().astype(np.int16)
    return grid, ppd, k, north, south, lon_c - hlon, lon_c + hlon

os.makedirs(os.path.join(os.path.dirname(__file__), 'terrain'), exist_ok=True)
for sid in (sys.argv[1:] or SITES):
    g, ppd, k, n, s, w, e = window(*SITES[sid])
    out = os.path.join(os.path.dirname(__file__), 'terrain', sid)
    g.astype('<i2').tofile(out + '.i16')
    meta = dict(nx=g.shape[1], ny=g.shape[0], north=n, south=s, west=w, east=e, units='metres', ppd=ppd / k,
                cell_m=round(3396190 * math.pi / 180 / (ppd / k)), min=int(g.min()), max=int(g.max()),
                source='MGS MOLA MEGDR %d px/deg median topography%s, metres above the areoid (PDS Geosciences Node)' % (ppd, ', averaged %dx%d' % (k, k) if k > 1 else ''))
    json.dump(meta, open(out + '.json', 'w'), indent=1)
    print(sid, g.shape, 'ppd', ppd, 'x1/%d' % k, 'elev', meta['min'], meta['max'])

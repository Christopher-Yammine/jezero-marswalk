# Builds the Utopia Planitia walk-site files. Nothing here comes from Jezero or Arcadia.
#   utp_dtm_30m.i16       planner grid elevation: mean of the 1 m HiRISE DTM per 30 m cell, decimetres above OFFSET_M,
#                         -32768 = outside the DTM footprint (not characterized)
#   utp_fslope_30m.u8     fine-scale slope: steepest 3 m slope inside each 30 m cell (3x3 median first, so single-pixel
#                         stereo spikes do not count), quarter degrees; 255 = no DTM
#   utp_elev_fill_30m.i16 3D display surface only: the DTM where it exists, MOLA (shifted to match) elsewhere
#   utp_ortho.webp        HiRISE orthoimage PSP_009467_2225 (co-registered with the DTM), 4 m, transparent outside it
#   sharad_outline.geojson SHARAD ice-rich deposit outline digitised from NASA/JPL PIA21138 (Stuurman et al. 2016)
#   utp_grid.json         bounds, cell size, sources, method notes
# Sources: HiRISE DTEEC_009467_2225_007384_2225_A01 (NASA/JPL/UArizona, PDS), MGS MOLA MEGDR 128 px/deg (PDS),
#          NASA/JPL PIA21138 map image.
# usage: python build_utopia.py <cache-dir>     (the 463 MB DTM and 42 MB ortho are cached there, not in the repo)
import io, json, math, os, sys, time, urllib.request
import numpy as np
from PIL import Image
from scipy import ndimage as nd

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = sys.argv[1] if len(sys.argv) > 1 else HERE
R_APP = 3396190.0; MPD = R_APP * math.pi / 180; CELL = 30; OFFSET_M = -4000
HB = 'https://hirise-pds.lpl.arizona.edu/PDS/DTM/PSP/ORB_009400_009499/PSP_009467_2225_PSP_007384_2225/'
DTM_F, ORTHO_F = 'DTEEC_009467_2225_007384_2225_A01.IMG', 'PSP_009467_2225_RED_C_01_ORTHO.JP2'
# DTM label (equirectangular, centre latitude 40, radius 3387.888 km, 1.00127 m pixels, 18029 x 6414 float32 LSB)
NL, NS, REC, SCALE = 18029, 6414, 25656, 1.0012718310744
R_D = 3387887.658234; CLAT, CLON = 40.0, 86.34; LPO, SPO = 2502724.5, 3033.5000000001
NODATA_BELOW = -1e30

def get(url, rng=None, tries=6):
    req = urllib.request.Request(url, headers={'User-Agent': 'marswalk-utopia-builder'})
    if rng: req.add_header('Range', 'bytes=%d-%d' % rng)
    for n in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=600) as r: return r.read()
        except OSError:
            if n == tries - 1: raise
            time.sleep(3 * (n + 1))
def cached(name):
    p = os.path.join(CACHE, name)
    if not os.path.exists(p): open(p, 'wb').write(get(HB + name))
    return p

# ---- DTM pixel <-> lat/lon (0-based pixel centres)
lat_of_line = lambda l: np.degrees((LPO - l) * SCALE / R_D)
lon_of_samp = lambda s: CLON + np.degrees((s - SPO) * SCALE / (R_D * math.cos(math.radians(CLAT))))
NORTH, SOUTH = float(lat_of_line(0)), float(lat_of_line(NL - 1)); WEST, EAST = float(lon_of_samp(0)), float(lon_of_samp(NS - 1))

# ---- planner grid over the DTM bounding box, same construction as the other sites
latC = (NORTH + SOUTH) / 2; mLon = MPD * math.cos(math.radians(latC)); mLat = MPD
nx = math.ceil((EAST - WEST) * mLon / CELL); ny = math.ceil((NORTH - SOUTH) * mLat / CELL)
print('grid', nx, 'x', ny, 'bounds', SOUTH, WEST, NORTH, EAST)
cell_y_of_line = np.clip(((NORTH - lat_of_line(np.arange(NL))) * mLat / CELL).astype(int), 0, ny - 1)
cell_x_of_samp = np.clip(((lon_of_samp(np.arange(NS)) - WEST) * mLon / CELL).astype(int), 0, nx - 1)

# ---- DTM: mean elevation per cell, and fine-scale slope from a 3 m version
dtm = np.memmap(cached(DTM_F), dtype='<f4', mode='r', offset=REC, shape=(NL, NS))   # ^IMAGE = record 2
s = np.zeros(nx * ny); c = np.zeros(nx * ny)
B3 = 3; e3 = np.full((NL // B3, NS // B3), np.nan, np.float32)
for r0 in range(0, NL - NL % B3, 600):
    blk = np.array(dtm[r0:r0 + 600]); r1 = r0 + blk.shape[0]
    ok = blk > NODATA_BELOW
    idx = (cell_y_of_line[r0:r1, None] * nx + cell_x_of_samp[None, :])
    s += np.bincount(idx[ok], weights=blk[ok], minlength=nx * ny); c += np.bincount(idx[ok], minlength=nx * ny)
    h = (blk.shape[0] // B3) * B3; w = (NS // B3) * B3
    b = np.where(ok, blk, np.nan)[:h, :w].reshape(h // B3, B3, w // B3, B3)
    with np.errstate(all='ignore'): e3[r0 // B3:r0 // B3 + h // B3] = np.nanmean(b, axis=(1, 3))
full = (CELL / SCALE) ** 2
valid = c > 0.5 * full                                                                     # at least half the cell has DTM
mean = np.where(valid, s / np.maximum(c, 1), np.nan).reshape(ny, nx)
print('DTM cells valid', round(float(valid.mean()), 3), 'elev', np.nanmin(mean), np.nanmax(mean))
assert -3276 < np.nanmin(mean) - OFFSET_M and np.nanmax(mean) - OFFSET_M < 3276
np.where(np.isnan(mean), -32768, np.round((mean - OFFSET_M) * 10)).astype('<i2').tofile(os.path.join(HERE, 'utp_dtm_30m.i16'))

gy, gx = np.gradient(np.nan_to_num(e3, nan=0.0), B3 * SCALE)
sl = np.degrees(np.arctan(np.hypot(gx, gy))); sl[~np.isfinite(e3)] = np.nan
edge = nd.binary_dilation(~np.isfinite(e3), iterations=1); sl[edge] = np.nan               # no slope across the footprint edge
slm = nd.median_filter(np.nan_to_num(sl, nan=0.0), size=3); slm[np.isnan(sl)] = np.nan
fs = np.full(nx * ny, -1.0)
cy3 = cell_y_of_line[np.arange(e3.shape[0]) * B3 + 1]; cx3 = cell_x_of_samp[np.arange(e3.shape[1]) * B3 + 1]
idx3 = cy3[:, None] * nx + cx3[None, :]; ok3 = np.isfinite(slm)
np.maximum.at(fs, idx3[ok3], slm[ok3])
fs = fs.reshape(ny, nx); fs[np.isnan(mean)] = -1
np.where(fs < 0, 255, np.clip(np.round(fs * 4), 0, 254)).astype('u1').tofile(os.path.join(HERE, 'utp_fslope_30m.u8'))
print('fine slope p50/p95/max', *np.percentile(fs[fs >= 0], [50, 95, 100]).round(1))

# ---- MOLA 128 px/deg around the grid, for the 3D display surface outside the DTM strip
MB = 'https://pds-geosciences.wustl.edu/mgs/mgs-m-mola-5-megdr-l3-v1/mgsl_300x/meg128/'
P = 128; r0 = int((44 - NORTH) * P) - 2; r1 = int((44 - SOUTH) * P) + 3; c0 = int((WEST - 0) * P) - 2; c1 = int((EAST - 0) * P) + 3
topo = np.array([np.frombuffer(get(MB + 'megt44n000hb.img', (r * 23040 + c0 * 2, r * 23040 + c1 * 2 - 1)), '>i2') for r in range(r0, r1)], float)
ys, xs = np.mgrid[0:ny, 0:nx]; glat = NORTH - (ys + .5) * CELL / mLat; glon = WEST + (xs + .5) * CELL / mLon
mola = nd.map_coordinates(topo, [(44 - glat) * P - .5 - r0, glon * P - .5 - c0], order=1)
shift = float(np.nanmedian(mean - mola)); fill = np.where(np.isnan(mean), mola + shift, mean)
fill = nd.gaussian_filter(fill, 1.0) * np.isnan(mean) + np.nan_to_num(mean) * ~np.isnan(mean)   # soften MOLA only
np.round((fill - OFFSET_M) * 10).astype('<i2').tofile(os.path.join(HERE, 'utp_elev_fill_30m.i16'))
print('MOLA shift to DTM', round(shift, 1), 'm')

# ---- orthoimage: same grid as the DTM; 2 m via JPEG 2000 reduce, then 4 m, transparent outside the footprint
Image.MAX_IMAGE_PIXELS = None
im = Image.open(cached(ORTHO_F)); im.reduce = 1; im.load()
o = np.asarray(im.convert('L')).astype(np.float32)
W4, H4 = o.shape[1] // 2, o.shape[0] // 2
o4 = np.asarray(Image.fromarray(o.astype(np.uint8)).resize((W4, H4), Image.BOX)).astype(np.float32)
lo, hi = np.percentile(o4[o4 > 0], [0.5, 99.5])
g = np.clip((o4 - lo) / (hi - lo) * 254 + 1, 1, 255).astype(np.uint8); a = np.where(o4 > 0, 255, 0).astype(np.uint8)
Image.fromarray(np.dstack([g, g, g, a]), 'RGBA').save(os.path.join(HERE, 'utp_ortho.webp'), quality=78, method=6)
print('ortho', W4, H4)

# ---- SHARAD deposit outline from the PIA21138 map (diagonal hatching = ice-rich deposit)
pia = np.asarray(Image.open(io.BytesIO(get('https://assets.science.nasa.gov/content/dam/science/psd/photojournal/pia/pia21/pia21138/PIA21138.tif'))).convert('RGB')).astype(int)
dark = pia.max(axis=2) < 70
thick = nd.binary_dilation(nd.binary_opening(dark, structure=np.ones((3, 3))), iterations=1)   # drawn outline, 3-4 px
thin = dark & ~thick                                                                               # hatch lines, 1 px
hat = nd.binary_fill_holes(nd.binary_closing(nd.uniform_filter(thin.astype(float), 11) > 0.05, iterations=3))
hat = nd.binary_erosion(hat, iterations=4) & ~thick
lab, n = nd.label(hat); keep = []
for k in range(1, n + 1):
    m = lab == k; yy, xx = np.where(m)
    if m.sum() > 600 and 140 < xx.mean() < 560 and 30 < yy.mean() < 240 and thin[nd.binary_dilation(m, iterations=4)].mean() > 0.05: keep.append(k)
dep = nd.binary_opening(nd.binary_dilation(np.isin(lab, keep), iterations=1) & ~thick, iterations=3)   # opening drops thin false bridges
# graticule read off the map: 40 N at y 223, 50 N at y 12; meridians 70/80/90 E at x 127/287.5/454 (40 N) and 136/274/411 (50 N)
LONS = [70, 80, 90]; X40 = [127, 287.5, 454]; X50 = [136, 274, 411]
def px2ll(px, py):
    lat = 40 + (223 - py) / 21.1; f = (lat - 40) / 10
    xs = [a + (b - a) * f for a, b in zip(X40, X50)]
    lon = np.interp(px, xs, LONS, left=None, right=None)
    if px > xs[-1]: lon = 90 + (px - xs[-1]) / (xs[-1] - xs[-2]) * 10              # beyond 90 E: extend the last spacing
    if px < xs[0]: lon = 70 - (xs[0] - px) / (xs[1] - xs[0]) * 10
    return float(lon), float(lat)
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
cs = plt.contour(dep.astype(float), levels=[0.5]); feats = []
for path in cs.allsegs[0]:
    if len(path) < 20: continue
    ring = [px2ll(x, y) for x, y in path[::2]]; ring.append(ring[0])
    feats.append({'type': 'Feature', 'properties': {'kind': 'sharad_deposit'}, 'geometry': {'type': 'Polygon', 'coordinates': [[[round(a, 3), round(b, 3)] for a, b in ring]]}})
json.dump({'type': 'FeatureCollection', 'properties': {
    'source': 'NASA/JPL-Caltech/Univ. of Rome/ASI/PSI, PIA21138 (22 Nov 2016), from Stuurman et al. 2016, GRL 43, doi:10.1002/2016GL070138',
    'method': 'hatched area segmented from the 596 x 286 px map image and georeferenced on its graticule; about 2.7 km per map pixel, outline accurate to roughly 5 to 10 km',
    'meaning': 'SHARAD radar: subsurface deposit consistent with water ice. Regional, inferred; about 8 m vertical resolution in ice; never a walking hazard by itself, not a confirmed water supply'},
    'features': feats}, open(os.path.join(HERE, 'sharad_outline.geojson'), 'w'))
print('sharad polygons', len(feats), [len(f['geometry']['coordinates'][0]) for f in feats])

json.dump(dict(
    bounds=[[SOUTH, WEST], [NORTH, EAST]], nx=nx, ny=ny, cell=CELL,
    dtm=dict(file='utp_dtm_30m.i16', units='decimetres above offset_m', offset_m=OFFSET_M, nodata=-32768, product=DTM_F[:-4],
             source='HiRISE DTM from stereo pair PSP_009467_2225 / PSP_007384_2225, 1 m posts, NASA/JPL/University of Arizona (PDS)',
             method='mean of 1 m posts per 30 m cell; cells with under half coverage are no-data', valid_share=round(float(valid.mean()), 4)),
    fine_slope=dict(file='utp_fslope_30m.u8', units='quarter degrees', nodata=255,
                    method='DTM averaged to 3 m, slope from central differences, 3 x 3 median, maximum within the 30 m cell'),
    fill=dict(file='utp_elev_fill_30m.i16', units='decimetres above offset_m', offset_m=OFFSET_M, use='3D display only: DTM, else MOLA 128 px/deg shifted by %.1f m' % shift),
    ortho=dict(file='utp_ortho.webp', bounds=[[SOUTH, WEST], [NORTH, EAST]], px=[W4, H4], product=ORTHO_F[:-4], date='2008-08-03', scale_m=4,
               credit='NASA/JPL/University of Arizona'),
    sharad=dict(file='sharad_outline.geojson'),
), open(os.path.join(HERE, 'utp_grid.json'), 'w'), indent=1)
print('done')

# Builds the Hellas Planitia walk-site files: one study tile of banded terrain on the north-west floor of the Hellas basin,
# about 7 km below the Mars datum.
# Nothing here comes from another site.
#   hl_dtm_30m.i16        planner grid elevation: mean of the 1 m HiRISE DTM per 30 m cell, decimetres above OFFSET_M,
#                         -32768 = outside the DTM footprint (not characterized)
#   hl_fslope_30m.u8      fine-scale slope: steepest 3 m slope inside each 30 m cell (3x3 median first, so single-pixel
#                         stereo spikes do not count), quarter degrees; 255 = no DTM
#   hl_elev_fill_30m.i16  3D display, horizon and line of sight: the DTM where it exists, MOLA (shifted to match) elsewhere
#   hl_ortho.webp         HiRISE orthoimage PSP_006133_1410 (co-registered with the DTM), 4 m, transparent outside it
#   hl_grid.json          bounds, cell size, sources, method notes
# Sources: HiRISE DTEEC_006133_1410_007056_1410_A01 (NASA/JPL/UArizona, PDS; HiRISE team rationale: "Complex banded flow
#          terrain on floor of Hellas Basin"), MGS MOLA MEGDR 128 px/deg (PDS Geosciences Node).
# usage: python build_hellas.py <cache-dir>     (the 680 MB DTM and the ortho are cached there, not in the repo)
import json, math, os, sys, time, urllib.request
import numpy as np
from PIL import Image
from scipy import ndimage as nd

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = sys.argv[1] if len(sys.argv) > 1 else HERE
R_APP = 3396190.0; MPD = R_APP * math.pi / 180; CELL = 30; OFFSET_M = -7000
HB = 'https://hirise-pds.lpl.arizona.edu/PDS/DTM/PSP/ORB_006100_006199/PSP_006133_1410_PSP_007056_1410/'
DTM_F, ORTHO_F = 'DTEEC_006133_1410_007056_1410_A01.IMG', 'PSP_006133_1410_RED_C_01_ORTHO.JP2'
# DTM label: equirectangular, centre latitude -35, centre longitude 54.46 E, radius 3389.574 km, 1.00287 m pixels,
# 21216 lines x 8015 samples float32 LSB, one 32060-byte label record. The ortho is assumed on the same grid (checked below).
NL, NS, REC, SCALE = 21216, 8015, 32060, 1.0028720187442
R_D = 3389574.3490888; CLAT, CLON = -35.0, 54.46; LPO, SPO = -2271478.5, 3962.4999999998
NODATA_BELOW = -1e30

def get(url, rng=None, tries=6):
    req = urllib.request.Request(url, headers={'User-Agent': 'marswalk-hellas-builder'})
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
np.where(np.isnan(mean), -32768, np.round((mean - OFFSET_M) * 10)).astype('<i2').tofile(os.path.join(HERE, 'hl_dtm_30m.i16'))

gy, gx = np.gradient(np.nan_to_num(e3, nan=0.0), B3 * SCALE)
sl = np.degrees(np.arctan(np.hypot(gx, gy))); sl[~np.isfinite(e3)] = np.nan
edge = nd.binary_dilation(~np.isfinite(e3), iterations=1); sl[edge] = np.nan               # no slope across the footprint edge
slm = nd.median_filter(np.nan_to_num(sl, nan=0.0), size=3); slm[np.isnan(sl)] = np.nan
fs = np.full(nx * ny, -1.0)
cy3 = cell_y_of_line[np.arange(e3.shape[0]) * B3 + 1]; cx3 = cell_x_of_samp[np.arange(e3.shape[1]) * B3 + 1]
idx3 = cy3[:, None] * nx + cx3[None, :]; ok3 = np.isfinite(slm)
np.maximum.at(fs, idx3[ok3], slm[ok3])
fs = fs.reshape(ny, nx); fs[np.isnan(mean)] = -1
np.where(fs < 0, 255, np.clip(np.round(fs * 4), 0, 254)).astype('u1').tofile(os.path.join(HERE, 'hl_fslope_30m.u8'))
print('fine slope p50/p95/max', *np.percentile(fs[fs >= 0], [50, 95, 100]).round(1))
# 30 m cell-to-cell slope share over 15 degrees, for the metadata only (the app computes its own)
gyc, gxc = np.gradient(mean, CELL); sl30 = np.degrees(np.arctan(np.hypot(gxc, gyc)))
share15 = float(np.nanmean(sl30 > 15)); print('30 m slope over 15 deg share', round(share15, 3))

# ---- MOLA 128 px/deg (tile 0..44 S, 0..90 E) for the display, horizon and line-of-sight surface outside the strip
MB = 'https://pds-geosciences.wustl.edu/mgs/mgs-m-mola-5-megdr-l3-v1/mgsl_300x/meg128/'
P = 128; r0 = int(-NORTH * P) - 2; r1 = int(-SOUTH * P) + 3; c0 = int(WEST * P) - 2; c1 = int(EAST * P) + 3
topo = np.array([np.frombuffer(get(MB + 'megt00n000hb.img', (r * 23040 + c0 * 2, r * 23040 + c1 * 2 - 1)), '>i2') for r in range(r0, r1)], float)
ys, xs = np.mgrid[0:ny, 0:nx]; glat = NORTH - (ys + .5) * CELL / mLat; glon = WEST + (xs + .5) * CELL / mLon
mola = nd.map_coordinates(topo, [-glat * P - .5 - r0, glon * P - .5 - c0], order=1)
shift = float(np.nanmedian(mean - mola)); fill = np.where(np.isnan(mean), mola + shift, mean)
fill = nd.gaussian_filter(fill, 1.0) * np.isnan(mean) + np.nan_to_num(mean) * ~np.isnan(mean)   # soften MOLA only
assert -3276 < fill.min() - OFFSET_M and fill.max() - OFFSET_M < 3276
np.round((fill - OFFSET_M) * 10).astype('<i2').tofile(os.path.join(HERE, 'hl_elev_fill_30m.i16'))
print('MOLA shift to DTM', round(shift, 1), 'm; MOLA range in tile', topo.min(), topo.max())

# ---- orthoimage: same grid as the DTM; 2 m via JPEG 2000 reduce, then 4 m, transparent outside the footprint
Image.MAX_IMAGE_PIXELS = None
im = Image.open(cached(ORTHO_F)); assert im.size == (NS, NL), ('ortho grid differs from DTM', im.size); im.reduce = 1; im.load()
o = np.asarray(im.convert('L')).astype(np.float32)
W4, H4 = o.shape[1] // 2, o.shape[0] // 2
o4 = np.asarray(Image.fromarray(o.astype(np.uint8)).resize((W4, H4), Image.BOX)).astype(np.float32)
lo, hi = np.percentile(o4[o4 > 0], [0.5, 99.5])
g = np.clip((o4 - lo) / (hi - lo) * 254 + 1, 1, 255).astype(np.uint8); a = np.where(o4 > 0, 255, 0).astype(np.uint8)
Image.fromarray(np.dstack([g, g, g, a]), 'RGBA').save(os.path.join(HERE, 'hl_ortho.webp'), quality=78, method=6)
print('ortho', W4, H4)

json.dump(dict(
    bounds=[[SOUTH, WEST], [NORTH, EAST]], nx=nx, ny=ny, cell=CELL,
    dtm=dict(file='hl_dtm_30m.i16', units='decimetres above offset_m', offset_m=OFFSET_M, nodata=-32768, product=DTM_F[:-4],
             source='HiRISE DTM from stereo pair PSP_006133_1410 / PSP_007056_1410, 1 m posts, NASA/JPL/University of Arizona (PDS)',
             rationale='Complex banded flow terrain on floor of Hellas Basin (HiRISE team)', images=dict(PSP_006133_1410='2007-11-17', PSP_007056_1410='2008-01-28'),
             method='mean of 1 m posts per 30 m cell; cells with under half coverage are no-data', valid_share=round(float(valid.mean()), 4),
             min_m=round(float(np.nanmin(mean)), 1), max_m=round(float(np.nanmax(mean)), 1), share_over_15deg_30m=round(share15, 4)),
    fine_slope=dict(file='hl_fslope_30m.u8', units='quarter degrees', nodata=255,
                    method='DTM averaged to 3 m, slope from central differences, 3 x 3 median, maximum within the 30 m cell'),
    fill=dict(file='hl_elev_fill_30m.i16', units='decimetres above offset_m', offset_m=OFFSET_M,
              use='3D display, horizon and line of sight: DTM, else MOLA 128 px/deg shifted by %.1f m' % shift),
    ortho=dict(file='hl_ortho.webp', bounds=[[SOUTH, WEST], [NORTH, EAST]], px=[W4, H4], product=ORTHO_F[:-4], date='2007-11-17', scale_m=4,
               credit='NASA/JPL/University of Arizona'),
), open(os.path.join(HERE, 'hl_grid.json'), 'w'), indent=1)
print('done')

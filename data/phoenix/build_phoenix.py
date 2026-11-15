# Builds the Phoenix landing-site walk files. Nothing here comes from another site.
#   phx_dtm_30m.i16       planner grid elevation: mean of the 1 m HiRISE DTM per 30 m cell, decimetres above OFFSET_M,
#                         -32768 = outside the DTM footprint (not characterized)
#   phx_fslope_30m.u8     steepest 3 m slope inside each 30 m cell (3x3 median first), quarter degrees; 255 = no DTM
#   phx_elev_fill_30m.i16 3D display surface only: the DTM where it exists, MOLA (shifted to match) elsewhere
#   phx_ortho.webp        HiRISE orthoimage PSP_008591_2485 (taken after landing; co-registered with the DTM), 4 m
#   phx_grid.json         bounds, cell size, projection notes, hardware positions found in the image
# Source: HiRISE DTEPC_008591_2485_008644_2485_U01 (NASA/JPL/UArizona, PDS); MGS MOLA MEGDR 128 px/deg (PDS).
# Projection: polar stereographic, north pole, 0.99065 m pixels. Spherical formulas need a scale factor K on the radial
# distance (fitted: the label's valid-data latitude bounds are reproduced to 0.0003 deg); this absorbs the ellipsoidal
# term of the archive's projection. Longitudes match the label bounds without adjustment.
# usage: python build_phoenix.py <cache-dir>
import json, math, os, sys, time, urllib.request
import numpy as np
from PIL import Image
from scipy import ndimage as nd

HERE = os.path.dirname(os.path.abspath(__file__)); CACHE = sys.argv[1] if len(sys.argv) > 1 else HERE
R_APP = 3396190.0; MPD = R_APP * math.pi / 180; CELL = 30; OFFSET_M = -4100
HB = 'https://hirise-pds.lpl.arizona.edu/PDS/DTM/PSP/ORB_008500_008599/PSP_008591_2485_PSP_008644_2485/'
DTM_F, ORTHO_F = 'DTEPC_008591_2485_008644_2485_U01.IMG', 'PSP_008591_2485_RED_C_01_ORTHO.JP2'
NL, NS, REC = 12615, 13203, 52812
R_P = 3396190.0; S = 0.99064948610552; LPO, SPO = 772770.5, 1071649.5; K = 0.99411
NORTH, SOUTH, WEST, EAST = 68.292335140399, 68.121495764396, 234.08574817 - 360, 234.4332309 - 360   # label bounds, east lon -> -180..180

def get(url, rng=None, tries=6):
    req = urllib.request.Request(url, headers={'User-Agent': 'marswalk-phoenix-builder'})
    if rng: req.add_header('Range', 'bytes=%d-%d' % rng)
    for n in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=900) as r: return r.read()
        except OSError:
            if n == tries - 1: raise
            time.sleep(3 * (n + 1))
def cached(name):
    p = os.path.join(CACHE, name)
    if not os.path.exists(p) or os.path.getsize(p) == 0: open(p, 'wb').write(get(HB + name))
    return p
def pix2ll(line, samp):
    x = (samp - SPO) * S; y = (LPO - line) * S; rho = np.hypot(x, y) / K
    return 90 - 2 * np.degrees(np.arctan(rho / (2 * R_P))), (np.degrees(np.arctan2(x, -y)) + 180) % 360 - 180
def ll2pix(lat, lon):
    r = 2 * R_P * K * np.tan(np.radians(45 - lat / 2)); x = r * np.sin(np.radians(lon)); y = -r * np.cos(np.radians(lon))
    return LPO - y / S, SPO + x / S

latC = (NORTH + SOUTH) / 2; mLon = MPD * math.cos(math.radians(latC)); mLat = MPD
nx = math.ceil((EAST - WEST) * mLon / CELL); ny = math.ceil((NORTH - SOUTH) * mLat / CELL)
print('grid', nx, 'x', ny)

# ---- DTM per cell (mean) and the 3 m slope grid in the native projection
dtm = np.memmap(cached(DTM_F), dtype='<f4', mode='r', offset=REC, shape=(NL, NS))
s = np.zeros(nx * ny); c = np.zeros(nx * ny); cols = np.arange(NS)
B3 = 3; e3 = np.full((NL // B3, NS // B3), np.nan, np.float32)
for r0 in range(0, NL - NL % B3, 600):
    blk = np.array(dtm[r0:r0 + 600]); r1 = r0 + blk.shape[0]; ok = blk > -1e30
    la, lo = pix2ll(np.arange(r0, r1)[:, None] + 0.0, cols[None, :] + 0.0)
    cx = np.clip(((lo - WEST) * mLon / CELL).astype(int), 0, nx - 1); cy = np.clip(((NORTH - la) * mLat / CELL).astype(int), 0, ny - 1)
    idx = (cy * nx + cx)[ok]; s += np.bincount(idx, weights=blk[ok], minlength=nx * ny); c += np.bincount(idx, minlength=nx * ny)
    h = (blk.shape[0] // B3) * B3; w = (NS // B3) * B3
    b = np.where(ok, blk, np.nan)[:h, :w].reshape(h // B3, B3, w // B3, B3)
    with np.errstate(all='ignore'): e3[r0 // B3:r0 // B3 + h // B3] = np.nanmean(b, axis=(1, 3))
valid = c > 0.5 * (CELL / S) ** 2
mean = np.where(valid, s / np.maximum(c, 1), np.nan).reshape(ny, nx)
print('valid', round(float(valid.mean()), 3), 'elev', np.nanmin(mean), np.nanmax(mean))
assert -3276 < np.nanmin(mean) - OFFSET_M and np.nanmax(mean) - OFFSET_M < 3276
np.where(np.isnan(mean), -32768, np.round((mean - OFFSET_M) * 10)).astype('<i2').tofile(os.path.join(HERE, 'phx_dtm_30m.i16'))
# ground spacing of a 3 m block: map pixels are stretched by the stereographic scale factor 2K / (1 + sin(lat))
gsp = B3 * S / (2 * K / (1 + math.sin(math.radians(latC))))
gy, gx = np.gradient(np.nan_to_num(e3, nan=0.0), gsp)
sl = np.degrees(np.arctan(np.hypot(gx, gy))); sl[~np.isfinite(e3)] = np.nan
sl[nd.binary_dilation(~np.isfinite(e3), iterations=1)] = np.nan
slm = nd.median_filter(np.nan_to_num(sl, nan=0.0), size=3); slm[np.isnan(sl)] = np.nan
L3, S3 = np.meshgrid(np.arange(e3.shape[0]) * B3 + 1.0, np.arange(e3.shape[1]) * B3 + 1.0, indexing='ij')
la3, lo3 = pix2ll(L3, S3)
idx3 = np.clip(((NORTH - la3) * mLat / CELL).astype(int), 0, ny - 1) * nx + np.clip(((lo3 - WEST) * mLon / CELL).astype(int), 0, nx - 1)
ok3 = np.isfinite(slm); fs = np.full(nx * ny, -1.0); np.maximum.at(fs, idx3[ok3], slm[ok3])
fs = fs.reshape(ny, nx); fs[np.isnan(mean)] = -1
np.where(fs < 0, 255, np.clip(np.round(fs * 4), 0, 254)).astype('u1').tofile(os.path.join(HERE, 'phx_fslope_30m.u8'))
print('fine slope p50/p95/max', *np.percentile(fs[fs >= 0], [50, 95, 100]).round(1))

# ---- MOLA 128 px/deg (tile 88N-44N, 180E-270E) for the 3D display surface outside the strip
MB = 'https://pds-geosciences.wustl.edu/mgs/mgs-m-mola-5-megdr-l3-v1/mgsl_300x/meg128/'
P = 128; WE, EE = WEST + 360, EAST + 360
r0 = int((88 - NORTH) * P) - 2; r1 = int((88 - SOUTH) * P) + 3; c0 = int((WE - 180) * P) - 2; c1 = int((EE - 180) * P) + 3
topo = np.array([np.frombuffer(get(MB + 'megt88n180hb.img', (r * 23040 + c0 * 2, r * 23040 + c1 * 2 - 1)), '>i2') for r in range(r0, r1)], float)
ys, xs = np.mgrid[0:ny, 0:nx]; glat = NORTH - (ys + .5) * CELL / mLat; glon = WE + (xs + .5) * CELL / mLon
mola = nd.map_coordinates(topo, [(88 - glat) * P - .5 - r0, (glon - 180) * P - .5 - c0], order=1)
shift = float(np.nanmedian(mean - mola)); fill = np.where(np.isnan(mean), nd.gaussian_filter(mola + shift, 1.0), mean)
np.round((fill - OFFSET_M) * 10).astype('<i2').tofile(os.path.join(HERE, 'phx_elev_fill_30m.i16'))
print('MOLA shift to DTM', round(shift, 1), 'm')

# ---- orthoimage reprojected to the map grid at 4 m (from the 2 m JPEG 2000 level)
Image.MAX_IMAGE_PIXELS = None
im = Image.open(cached(ORTHO_F)); im.reduce = 1; im.load(); o2 = np.asarray(im.convert('L')).astype(np.float32)
OW = int(round((EAST - WEST) * mLon / 4)); OH = int(round((NORTH - SOUTH) * mLat / 4))
oy, ox = np.mgrid[0:OH, 0:OW]; olat = NORTH - (oy + .5) * (NORTH - SOUTH) / OH; olon = WEST + (ox + .5) * (EAST - WEST) / OW
ln, sm = ll2pix(olat, olon)
o4 = nd.map_coordinates(o2, [ln / 2, sm / 2], order=1, cval=0)
lo_, hi_ = np.percentile(o4[o4 > 0], [0.5, 99.5]); g = np.clip((o4 - lo_) / (hi_ - lo_) * 254 + 1, 1, 255).astype(np.uint8)
Image.fromarray(np.dstack([g, g, g, np.where(o4 > 0, 255, 0).astype(np.uint8)]), 'RGBA').save(os.path.join(HERE, 'phx_ortho.webp'), quality=78, method=6)
print('ortho', OW, OH)

# ---- hardware found in the post-landing orthoimage (full-resolution line, sample), located by eye
HW = {'lander': (6534, 7283), 'backshell_parachute': (6454, 6953), 'heat_shield': (6628, 7093)}
hw = {k: [round(float(v), 6) for v in pix2ll(l, s_)] for k, (l, s_) in HW.items()}
pub = (68.218830, 234.250778 - 360); pl, ps = ll2pix(*pub)
off = math.hypot((pl - HW['lander'][0]) * S, (ps - HW['lander'][1]) * S)
print('hardware', hw, 'published lander position falls', round(off), 'm from the lander seen in the image')
json.dump(dict(
    bounds=[[SOUTH, WEST], [NORTH, EAST]], nx=nx, ny=ny, cell=CELL,
    dtm=dict(file='phx_dtm_30m.i16', units='decimetres above offset_m', offset_m=OFFSET_M, nodata=-32768, product=DTM_F[:-4],
             source='HiRISE DTM from stereo pair PSP_008591_2485 / PSP_008644_2485, 1 m posts, NASA/JPL/University of Arizona (PDS)',
             method='mean of 1 m posts per 30 m cell; polar stereographic to map grid with fitted radial factor K=%.5f' % K, valid_share=round(float(valid.mean()), 4)),
    fine_slope=dict(file='phx_fslope_30m.u8', units='quarter degrees', nodata=255, method='DTM averaged to 3 m, slope on ground spacing, 3 x 3 median, maximum within the cell'),
    fill=dict(file='phx_elev_fill_30m.i16', units='decimetres above offset_m', offset_m=OFFSET_M, use='3D display only: DTM, else MOLA shifted by %.1f m' % shift),
    ortho=dict(file='phx_ortho.webp', bounds=[[SOUTH, WEST], [NORTH, EAST]], px=[OW, OH], product=ORTHO_F[:-4], scale_m=4, credit='NASA/JPL/University of Arizona'),
    hardware=dict(positions=hw, method='located by eye in the post-landing orthoimage at 1 m', published_lander=list(pub), published_offset_m=round(off)),
), open(os.path.join(HERE, 'phx_grid.json'), 'w'), indent=1)
print('done')

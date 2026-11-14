# Builds the Arcadia Planitia walk-site files. Nothing here comes from Jezero.
#   arc_dtm_30m.i16   planner grid elevation, decimetres, -32768 = MOLA bin with no laser shot (not characterized)
#   arc_rough_30m.u8  HRSC image-texture roughness, 0..254 (orbital proxy for yardang ridges), 255 = no HRSC pixel
#   hrsc_walk.jpg     HRSC orbit 26333 nadir image, reprojected to the map grid at 12.5 m       (CC BY-SA 3.0 IGO)
#   hrsc_context.png  HRSC orbit 26333 browse (100 m), reprojected, 40.5-44.2 N, for context     (CC BY-SA 3.0 IGO)
#   arc_grid.json     bounds, cell size, sources, normalisation
# Sources (downloaded with HTTP range requests, only the bytes needed):
#   MGS MOLA MEGDR 128 px/deg topography + shot counts (PDS Geosciences Node)
#   Mars Express HRSC HQ333_0000_ND4, MEX-M-HRSC-4-REFDR-MAPPROJECT-EXT9-V4.0 (PDS Geosciences Node mirror of ESA PSA)
# usage: python build_arcadia.py
import io, json, math, os, time, urllib.request
import numpy as np
from PIL import Image
from scipy.ndimage import uniform_filter, map_coordinates

HERE = os.path.dirname(os.path.abspath(__file__))
R_APP = 3396190.0; MPD = R_APP * math.pi / 180; CELL = 30
# Walk grid: about 15 x 18 km straddling the yardang / dark-terrain boundary in the HRSC scene. East longitudes.
NORTH, SOUTH, WEST_E, EAST_E = 41.52, 41.22, 211.78, 212.12
CONTEXT = (44.2, 40.5, 210.39, 212.6)

def get(url, rng=None, tries=6):
    req = urllib.request.Request(url, headers={'User-Agent': 'marswalk-arcadia-builder'})
    if rng: req.add_header('Range', 'bytes=%d-%d' % rng)
    for n in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=300) as r: return r.read()
        except OSError:
            if n == tries - 1: raise
            time.sleep(3 * (n + 1))

# ---- planner grid, same construction as the Jezero grid (cell centres, equirectangular at the grid's mid latitude)
latC = (NORTH + SOUTH) / 2; mLon = MPD * math.cos(math.radians(latC)); mLat = MPD
nx = math.ceil((EAST_E - WEST_E) * mLon / CELL); ny = math.ceil((NORTH - SOUTH) * mLat / CELL)
ys, xs = np.mgrid[0:ny, 0:nx]
glat = NORTH - (ys + .5) * CELL / mLat; glon = WEST_E + (xs + .5) * CELL / mLon
print('grid', nx, 'x', ny)

# ---- MOLA: tile 44N..0, 180E..270E at 128 px/deg
MB = 'https://pds-geosciences.wustl.edu/mgs/mgs-m-mola-5-megdr-l3-v1/mgsl_300x/meg128/'
P = 128; r0 = int((44 - NORTH) * P) - 2; r1 = int((44 - SOUTH) * P) + 3; c0 = int((WEST_E - 180) * P) - 2; c1 = int((EAST_E - 180) * P) + 3
topo = np.zeros((r1 - r0, c1 - c0)); cnt = np.zeros((r1 - r0, c1 - c0), np.int32)
for i, r in enumerate(range(r0, r1)):
    topo[i] = np.frombuffer(get(MB + 'megt44n180hb.img', (r * 23040 + c0 * 2, r * 23040 + c1 * 2 - 1)), '>i2')
    cnt[i] = np.frombuffer(get(MB + 'megc44n180hb.img', (r * 11520 + c0, r * 11520 + c1 - 1)), 'u1')
fr = (44 - glat) * P - .5 - r0; fc = (glon - 180) * P - .5 - c0          # fractional bin index of each cell centre
elev = map_coordinates(topo, [fr, fc], order=1)
shots = cnt[np.clip(np.round(fr).astype(int), 0, cnt.shape[0] - 1), np.clip(np.round(fc).astype(int), 0, cnt.shape[1] - 1)]
# Heights here are about -3,700 m: in decimetres that overflows int16, so store decimetres above OFFSET_M.
OFFSET_M = -3000
assert -3276 < elev.min() - OFFSET_M and elev.max() - OFFSET_M < 3276
dtm = np.where(shots > 0, np.round((elev - OFFSET_M) * 10), -32768).astype('<i2')
dtm.tofile(os.path.join(HERE, 'arc_dtm_30m.i16'))
# display surface for the 3D view only: every cell, including the archive's interpolated bins. Routing never reads it.
np.round((elev - OFFSET_M) * 10).astype('<i2').tofile(os.path.join(HERE, 'arc_elev_fill_30m.i16'))
nodata = float((shots == 0).mean())
binsWithShots = float((cnt > 0).mean())
print('MOLA elev', elev.min(), elev.max(), 'cells without a shot in their bin', round(nodata, 3))

# ---- HRSC nadir, sinusoidal, centre lon 212 E, sphere 3396 km, 12.5 m/px
HB = 'https://pds-geosciences.wustl.edu/mex/mex-m-hrsc-4-refdr-mapproject-ext9-v4/mexhrs_6009/'
R_H = 3396.0; LPO = 216338.0; SPO = 5516.0; SC = 0.0125; NS = 7870; HOFF = 4 * NS
line = lambda la: LPO - R_H * np.radians(la) / SC + 1                      # 1-based line
samp = lambda la, lo: R_H * np.radians(lo - 212.0) * np.cos(np.radians(la)) / SC + SPO + 1
l1 = int(line(NORTH + .01)); l2 = int(line(SOUTH - .01)) + 1
img = np.frombuffer(get(HB + 'data/q333/hq333_0000_nd4.img', (HOFF + (l1 - 1) * NS, HOFF + l2 * NS - 1)), np.uint8).reshape(-1, NS).astype(np.float64)
valid = img > 0
print('HRSC lines', l1, l2, 'valid', round(float(valid.mean()), 3))

# basemap: 12.5 m equirectangular over the grid bounds, bilinear
W = int(round((EAST_E - WEST_E) * mLon / 12.5)); H = int(round((NORTH - SOUTH) * mLat / 12.5))
oy, ox = np.mgrid[0:H, 0:W]; olat = NORTH - (oy + .5) * (NORTH - SOUTH) / H; olon = WEST_E + (ox + .5) * (EAST_E - WEST_E) / W
base = map_coordinates(img, [line(olat) - l1, samp(olat, olon) - 1], order=1, cval=0)
lo, hi = np.percentile(base[base > 0], [0.5, 99.5])
Image.fromarray(np.clip((base - lo) / (hi - lo) * 255, 0, 255).astype(np.uint8)).save(os.path.join(HERE, 'hrsc_walk.jpg'), quality=82)

# roughness: brightness variance after removing the 110 m local mean, over a 60 m window (5 x 5 px).
# Ridges under about 20 m are near the 16.5 m best ground sampling, so this is a texture proxy, not measured relief.
hp = img - uniform_filter(img, 9)
rough = np.sqrt(np.maximum(uniform_filter(hp * hp, 5), 0))
gr = map_coordinates(rough, [line(glat) - l1, samp(glat, glon) - 1], order=1)
gv = map_coordinates(valid.astype(float), [line(glat) - l1, samp(glat, glon) - 1], order=0) > 0
p5, p95 = np.percentile(gr[gv], [5, 95])
ru8 = np.where(gv, np.clip((gr - p5) / (p95 - p5) * 254, 0, 254), 255).astype(np.uint8)
ru8.tofile(os.path.join(HERE, 'arc_rough_30m.u8'))

# ---- context: PDS browse (8x reduced, 100 m/px), reprojected with transparency outside the strip
br = np.asarray(Image.open(io.BytesIO(get(HB + 'browse/q333/hq333_0000_nd4.jpg'))).convert('L'), np.float64)
cN, cS, cW, cE = CONTEXT; cmLon = MPD * math.cos(math.radians((cN + cS) / 2))
CW = int((cE - cW) * cmLon / 100); CH = int((cN - cS) * mLat / 100)
oy, ox = np.mgrid[0:CH, 0:CW]; clat = cN - (oy + .5) * (cN - cS) / CH; clon = cW + (ox + .5) * (cE - cW) / CW
cv = map_coordinates(br, [(line(clat) - 1) / 8, (samp(clat, clon) - 1) / 8], order=1, cval=0)
Image.fromarray(np.dstack([np.clip(cv, 0, 255), np.where(cv > 2, 255, 0)]).astype(np.uint8), 'LA').save(os.path.join(HERE, 'hrsc_context.png'), optimize=True)

west = WEST_E - 360; east = EAST_E - 360
json.dump(dict(
    bounds=[[SOUTH, west], [NORTH, east]], nx=nx, ny=ny, cell=CELL,
    dtm=dict(file='arc_dtm_30m.i16', units='decimetres above offset_m', offset_m=OFFSET_M, nodata=-32768,
             source='MGS MOLA MEGDR 128 px/deg median topography (about 463 m bins), metres above the areoid, mapping phase 1999-2001, PDS Geosciences Node',
             method='bilinear between MOLA bin centres at 30 m cell centres; a cell is no-data when its nearest bin holds no laser shot (the archive fills those bins by interpolation)',
             cells_without_shot=round(nodata, 4), bins_with_shot=round(binsWithShots, 4), min_m=round(float(elev.min()), 1), max_m=round(float(elev.max()), 1)),
    fill=dict(file='arc_elev_fill_30m.i16', units='decimetres above offset_m', offset_m=OFFSET_M, use='3D display surface only, includes interpolated MOLA bins; routing uses arc_dtm_30m.i16'),
    rough=dict(file='arc_rough_30m.u8', nodata=255, p5=round(float(p5), 2), p95=round(float(p95), 2),
               method='HRSC nadir brightness: subtract 9 x 9 px (110 m) mean, RMS over 5 x 5 px (60 m), sampled at cell centres, scaled 5th..95th percentile to 0..254'),
    hrsc=dict(product='HQ333_0000_ND4', dataset='MEX-M-HRSC-4-REFDR-MAPPROJECT-EXT9-V4.0', orbit=26333, date='2024-11-10',
              map_scale_m=12.5, best_gsd_m=16.5, projection='sinusoidal, centre 212 E, sphere 3396 km',
              walk_image=dict(file='hrsc_walk.jpg', bounds=[[SOUTH, west], [NORTH, east]], px=[W, H], stretch=[round(float(lo), 1), round(float(hi), 1)]),
              context_image=dict(file='hrsc_context.png', bounds=[[cS, cW - 360], [cN, cE - 360]], px=[CW, CH], source='PDS browse, 100 m/px'),
              credit='ESA/DLR/FU Berlin', license='CC BY-SA 3.0 IGO'),
), open(os.path.join(HERE, 'arc_grid.json'), 'w'), indent=1)
print('done', W, H, CW, CH)

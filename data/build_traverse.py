"""Slim NASA's M20 traverse into site/m20_traverse.json.

Source: https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_traverse.json
(FeatureCollection, one LineString per drive, props sol/length, coords [lon,lat,elev]).
Interior points closer than THIN_M metres to the previous kept point are dropped (first and last vertex of every drive are always kept); vertices with elevation >= -1000 m are
bad values in the source and are kept with elev=null. Run: python data/build_traverse.py
"""
import json, math, sys
sys.stdout.reconfigure(encoding='utf-8')
R = 3396190.0
THIN_M = 3.0
def hav(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[1], a[0], b[1], b[0]))
    h = math.sin((la2-la1)/2)**2 + math.cos(la1)*math.cos(la2)*math.sin((lo2-lo1)/2)**2
    return 2*R*math.asin(math.sqrt(h))
src = json.load(open('data/m20_traverse_raw_nasa.json', encoding='utf-8'))
segs = []
for f in src['features']:
    p = f['properties']; c = f['geometry']['coordinates']
    pts = []
    for i, (lon, lat, el) in enumerate(c):
        el = round(el, 1) if el < -1000 else None
        last = i == len(c) - 1
        if pts and not last and hav(pts[-1], (lon, lat)) < THIN_M: continue
        pts.append([round(lon, 6), round(lat, 6), el])
    segs.append({'sol': p['sol'], 'len': p['length'], 'pts': pts})
out = {'radius_m': R, 'source': 'https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_traverse.json', 'segments': segs}
json.dump(out, open('m20_traverse.json', 'w', encoding='utf-8'), separators=(',', ':'))
print(len(segs), 'segments,', sum(len(s['pts']) for s in segs), 'points,', round(sum(s['len'] for s in segs)/1000, 2), 'km NASA')

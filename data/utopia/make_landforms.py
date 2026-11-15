# Ice-related landforms at the Utopia walk site, marked by eye in the HiRISE orthoimage PSP_009467_2225 and checked
# against the HiRISE DTM (every scarp traced here coincides with cells whose 3 m slope exceeds 15 degrees).
# Points were read off gridded crops at 4 m per pixel; positions are good to a few tens of metres.
# Scarps become 100 m wide zones along the traced line; craters become circles; polygonal terrain is an area.
# usage: python make_landforms.py   -> landforms.geojson
import json, math, os
HERE = os.path.dirname(os.path.abspath(__file__))
MPD = 3396190 * math.pi / 180; MLON = MPD * math.cos(math.radians(42.227))

# crop A (scarp view): lon = 86.285 + x * 0.005 / 57, lat = 42.270 - (y - 27) * 0.005 / 74
A = lambda x, y: (86.285 + x * 0.005 / 57, 42.270 - (y - 27) * 0.005 / 74)
# crop B (polygon view): lon = 86.300 + x * 0.005 / 56.8, lat = 42.175 - (y - 40) * 0.005 / 73.3
B = lambda x, y: (86.300 + x * 0.005 / 56.8, 42.175 - (y - 40) * 0.005 / 73.3)

def band(pts, half=50):
    """Polygon around a polyline, half-width in metres (simple offset; fine at 30 m cells)."""
    xy = [((lo - pts[0][0]) * MLON, (la - pts[0][1]) * MPD) for lo, la in pts]
    left, right = [], []
    for i, (x, y) in enumerate(xy):
        a = xy[max(0, i - 1)]; b = xy[min(len(xy) - 1, i + 1)]; dx, dy = b[0] - a[0], b[1] - a[1]; n = math.hypot(dx, dy) or 1
        nx, ny = -dy / n * half, dx / n * half
        left.append((x + nx, y + ny)); right.append((x - nx, y - ny))
    ring = left + right[::-1] + [left[0]]
    return [[round(pts[0][0] + x / MLON, 6), round(pts[0][1] + y / MPD, 6)] for x, y in ring]
def circle(lo, la, r, n=24):
    return [[round(lo + r * math.cos(2 * math.pi * k / n) / MLON, 6), round(la + r * math.sin(2 * math.pi * k / n) / MPD, 6)] for k in range(n)] + [[round(lo + r / MLON, 6), round(la, 6)]]
def area(pts):
    ring = [[round(lo, 6), round(la, 6)] for lo, la in pts]; return ring + [ring[0]]

SCARP_D = 'Terraced, scalloped scarp at a mantle margin: the edge of a depression read as ice loss from the ground beneath (sublimation). Steep 3 m slopes along it in the HiRISE DTM.'
feats = []
def add(name, kind, ring, d):
    feats.append({'type': 'Feature', 'properties': {'name': name, 'kind': kind, 'd': d, 'method': 'marked by eye in HiRISE PSP_009467_2225, checked against the HiRISE DTM'},
                  'geometry': {'type': 'Polygon', 'coordinates': [ring]}})

add('Scalloped scarp, main terraced margin', 'scalloped_scarp', band([A(*p) for p in [(215, 255), (210, 300), (230, 345), (255, 383), (300, 397), (340, 397), (380, 380), (395, 405), (440, 412), (490, 395), (530, 360), (555, 345), (610, 393)]]), SCARP_D)
add('Scalloped scarp, north-west', 'scalloped_scarp', band([A(258, 62), A(262, 155)]), SCARP_D)
add('Scalloped scarp, east arc', 'scalloped_scarp', band([A(*p) for p in [(1000, 375), (1005, 425), (1030, 460), (1050, 495), (1100, 485), (1130, 520), (1180, 510)]]), SCARP_D)
add('Scalloped scarp, south-west', 'scalloped_scarp', band([A(*p) for p in [(240, 665), (200, 700), (165, 725), (150, 770), (155, 820)]]), SCARP_D)
add('Scalloped scarp, south diagonal', 'scalloped_scarp', band([B(*p) for p in [(485, 30), (445, 110), (410, 190), (375, 250), (335, 295), (260, 330), (190, 320), (140, 270)]]), SCARP_D)
add('Scalloped scarp, bright tongue edge', 'scalloped_scarp', band([B(860, 630), B(830, 680), B(800, 730)]), SCARP_D)
add('Scalloped depression', 'scalloped_depression', area([B(*p) for p in [(345, 410), (355, 460), (400, 480), (440, 460), (490, 385), (480, 345), (430, 360), (380, 395)]]),
    'Closed, rimless depression with a scalloped outline: interpreted as ground that sank where ice was lost. Ground strength unverified.')
RIM_D = 'Crater with a raised rim and a central mound or ring (ring-mold type), a form associated with ice-rich ground when it formed.'
add('Rimmed crater, north', 'rimmed_crater', circle(*A(935, 105), 160), RIM_D)
add('Rimmed crater, centre', 'rimmed_crater', circle(*A(612, 648), 130), RIM_D)
add('Ring-mold crater, south-west', 'rimmed_crater', circle(*B(215, 195), 220), RIM_D)
add('Ring-mold crater, south-east', 'rimmed_crater', circle(*B(1060, 945), 190), RIM_D)
add('Polygonal terrain', 'polygonal_terrain', area([B(*p) for p in [(470, 40), (1120, 40), (1140, 350), (1100, 480), (900, 540), (700, 560), (560, 640), (450, 700), (300, 700), (160, 640), (130, 480), (330, 470), (440, 420), (470, 300), (440, 200)]]),
    'Ground cut into polygons tens of metres across by a crack network: thermal-contraction polygons, typical of ice-rich ground. The cracks themselves are below this map\'s routing cell size.')

json.dump({'type': 'FeatureCollection', 'properties': {
    'source': 'HiRISE PSP_009467_2225 orthoimage and DTEEC_009467_2225_007384_2225 DTM (NASA/JPL/UArizona)',
    'method': 'marked by eye on gridded 4 m crops; scarps checked against 3 m slopes over 15 degrees in the DTM; positions good to a few tens of metres',
    'meaning': 'visible ice-related landforms: evidence of past ice loss or ice-rich ground, not a measurement of ice today, not a statement on ground strength'},
    'features': feats}, open(os.path.join(HERE, 'landforms.geojson'), 'w'), indent=0)
print(len(feats), 'features')
for f in feats: print(' ', f['properties']['name'], f['geometry']['coordinates'][0][0])

// Marswalk planner core: walk sites, terrain grid, A* routing and route metrics.
// Shared by the 2D planner (index.html) and the 3D view (3d.html) so both compute the same routes.
// Plain {lat,lng} objects throughout; no Leaflet or three.js here.
(function (root) {
const R = 3396190;                    // Mars mean radius, m (same as NASA MMGIS and the Leaflet CRS)
const CELL = 30;                      // grid cell, m
const M_PER_DEG = R * Math.PI / 180;
const RAD = Math.PI / 180;
const NIGHT_ID = 'THEMIS_NightIR_ControlledMosaics_100m_v2_oct2018';

// Great-circle distance, identical to Leaflet's CRS distance with R.
function dist(a, b) {
  const lat1 = a.lat * RAD, lat2 = b.lat * RAD, sLat = Math.sin((b.lat - a.lat) * RAD / 2), sLon = Math.sin((b.lng - a.lng) * RAD / 2);
  const h = sLat * sLat + Math.cos(lat1) * Math.cos(lat2) * sLon * sLon;
  return R * 2 * Math.atan2(Math.sqrt(h), Math.sqrt(1 - h));
}

// ---- Walk sites. They share no data: each has its own grid, elevation source, targets and habitat.
const JEZ_TARGETS = [
  { n: 'Octavia E. Butler landing site', sol: 14, ll: [18.444627, 77.450886], d: 'Touchdown 18 Feb 2021. Crater floor, Máaz formation basalts.' },
  { n: 'Séítah', sol: 200, ll: [18.432548, 77.440687], d: 'Olivine-rich layered rocks, first cores. Ridged, sandy ground the rover had to drive around.' },
  { n: 'Delta front, Hawksbill Gap', sol: 420, ll: [18.449825, 77.401363], d: 'Sandstone and mudstone of the ancient delta. Clays and carbonates from orbit (CRISM).' },
  { n: 'Three Forks sample depot', sol: 693, ll: [18.454176, 77.408448], d: 'Ten sealed sample tubes left on the surface for Mars Sample Return.' },
  { n: 'Bright Angel', sol: 1182, ll: [18.497182, 77.305358], d: 'Light-toned rock in Neretva Vallis. Cheyava Falls leopard-spot core, July 2024.' },
  { n: 'Crater rim, Witch Hazel Hill', sol: 1400, ll: [18.460553, 77.264745], d: 'Oldest rocks of the mission, 700 m above the floor. Steepest ground driven.' },
  { n: 'Rover now (last published drive)', sol: 2022, ll: [18.435594, 77.233223], d: 'Position at the end of the traverse file.' },
];
// Arcadia targets: positions located by eye in HRSC orbit 26333 (12.5 m), about 100 m accuracy. Each has a fallback.
// alt marks a fallback; ph marks a placeholder with no position.
const ARC_TARGETS = [
  { n: 'Yardang field edge', ll: [41.353, -148.092], ev: 'orb', d: 'Boundary between ridged, wind-carved terrain (west) and darker terrain without ridges (east). The ridges are just under 20 m across, near the image limit, so individual ridges are not resolved.' },
  { n: 'Yardang field edge, fallback', alt: 1, ll: [41.470, -148.080], ev: 'orb', d: 'Same boundary about 13 km to the north, where a tongue of ridged terrain meets the dark plain.' },
  { n: 'Dark deposit against the ridge', ll: [41.410, -147.962], ev: 'orb', d: 'Dark material on the north-east (lee) side of a bright knob, read as dark volcanic sand piled against a rock ridge that blocks the wind. Composition not measured. HiRISE ESP_046912_2215 covers it but is not loaded here.' },
  { n: 'Dark deposit, fallback', alt: 1, ll: [41.454, -147.970], ev: 'orb', d: 'A second, smaller dark patch north of the knob. Same interpretation, lower confidence.' },
  { n: 'Rampart crater ejecta (candidate)', ll: [43.47, -147.75], ev: 'orb', d: 'South edge of the lobate ejecta apron of a crater about 20 km wide at 43.70°N 212.27°E. The release describes a rampart crater of about 15 km; this is the best match found in the scene, not confirmed. About 125 km from the habitat: outside the walk grid, so no routes.' },
  { n: 'Rampart crater ejecta, fallback', alt: 1, ph: 1, ev: 'ph', d: 'Placeholder: no second crater with fluidized ejecta was found in the HRSC scene.' },
  { n: 'Ice-related landform', ph: 1, ev: 'ph', d: 'Placeholder: no ice-related landform (scalloped pits, polygons, ice-exposing scarp) was located in the walk area at 12.5 m. Ice is likely near the surface regionally, not measured here.' },
  { n: 'Ice-related landform, fallback', alt: 1, ph: 1, ev: 'ph', d: 'Placeholder: candidate is the rampart crater ejecta above, whose shape suggests volatile-rich ground at impact.' },
];
// Utopia targets: located by eye in the HiRISE orthoimage PSP_009467_2225 (1 m), checked against the HiRISE DTM; good to tens of metres.
const UTP_TARGETS = [
  { n: 'Scalloped scarp, main wall', ll: [42.2455, 86.315], ev: 'orb', loc: 'HiRISE', d: 'Terraced wall of a large scalloped depression, about 35 m high: the floor to the north is lower than the mantle to the south. Read as ice loss from the ground beneath. 3 m slopes here reach about 20 degrees in the HiRISE DTM. Ground strength unverified.' },
  { n: 'Scalloped scarp, east arc (fallback)', alt: 1, ll: [42.2408, 86.3755], ev: 'orb', loc: 'HiRISE', d: 'A second terraced scarp on the east side of the same depression.' },
  { n: 'Mantle surface above the scarp', ll: [42.2405, 86.322], ev: 'orb', loc: 'HiRISE', d: 'Dark, textured mantle south of the scarp, about 35 m above the depression floor: the surface the depression was cut into. Regionally, SHARAD radar places ice-rich material beneath this mantle (inferred, not measured here).' },
  { n: 'Mantle surface (fallback)', alt: 1, ll: [42.236, 86.355], ev: 'orb', loc: 'HiRISE', d: 'Same mantle unit about 2.5 km further east.' },
  { n: 'Rimmed crater, north', ll: [42.2647, 86.3633], ev: 'orb', loc: 'HiRISE', d: 'West rim of a crater about 320 m across with a raised rim and central mound (ring-mold type), a form associated with ice-rich ground when it formed.' },
  { n: 'Rimmed crater, centre (fallback)', alt: 1, ll: [42.228, 86.3364], ev: 'orb', loc: 'HiRISE', d: 'A smaller rimmed crater south of the main scarp.' },
  { n: 'Polygonal terrain', ll: [42.158, 86.36], ev: 'orb', loc: 'HiRISE', d: 'Ground cut into polygons tens of metres across by a crack network, typical of ice-rich ground. About 11 km south of the habitat: far beyond the walk-back circle.' },
  { n: 'Polygonal terrain (fallback)', alt: 1, ll: [42.15, 86.39], ev: 'orb', loc: 'HiRISE', d: 'The same crack network further east.' },
  { n: 'Scalloped depression', ll: [42.149, 86.333], ev: 'orb', loc: 'HiRISE', d: 'A small closed depression with a scalloped outline in the south of the strip, read as ground that sank where ice was lost.' },
  { n: 'Ring-mold crater, south-west (fallback)', alt: 1, ll: [42.1644, 86.3195], ev: 'orb', loc: 'HiRISE', d: 'Crater with a concentric inner ring, a second ice-related form near the scalloped depression.' },
];
// Phoenix targets: spacecraft hardware located by eye in the post-landing HiRISE orthoimage PSP_008591_2485 (1 m).
// The published lander position (68.218830 N, 234.250778 E) falls about 70 m from the lander seen in this DTM's image frame;
// positions here are in the DTM frame so they line up with its terrain.
const PHX_TARGETS = [
  { n: 'Phoenix lander and its trenches', ll: [68.217666, -125.75008], ev: 'obs', loc: 'HiRISE', d: 'The lander (2008), at the centre of the ground its descent engines darkened. Its arm dug trenches here and exposed water ice 5 to 18 cm down (Smith et al. 2009). Hardware on Mars: approach only as a heritage site.' },
  { n: 'Backshell and parachute', ll: [68.212566, -125.744495], ev: 'obs', loc: 'HiRISE', d: 'Dark impact spot with a bright object beside it, about 330 m from the lander: the backshell and parachute, identified by eye in the HiRISE image.' },
  { n: 'Heat shield impact', ll: [68.216056, -125.741898], ev: 'obs', loc: 'HiRISE', d: 'Dark spot about 200 m from the lander, where the heat shield struck: identified by eye in the HiRISE image.' },
];
// Valles Marineris targets: located by eye in the HiRISE orthoimage ESP_036307_1665 (shown at 4 m) and checked against the
// HiRISE DTM; good to tens of metres. Landforms mapped from orbit, never measured ground.
const VM_TARGETS = [
  { n: 'Hummocky ground, west', ll: [-13.084886, -69.363642], ev: 'orb', loc: 'HiRISE', d: 'Knobs and hollows tens to hundreds of metres across, about 300 m below the habitat and inside the same walkable patch under a 15 degree limit. Ground like this can form from landslide debris; that is a reading of the image, not verified. About 1.4 km from the habitat.' },
  { n: 'Foot of the scarp', ll: [-13.123857, -69.353768], ev: 'orb', loc: 'HiRISE', d: 'Darker, smoother ground along the base of the slope that rises about 2 km to the south: the scarp the HiRISE team named "East Melas Chasma landslide scarp". Material that comes off the slope would end up here; whether any is moving today is not characterized. A separate patch from the habitat under a 15 degree limit.' },
  { n: 'Scarp face, streaked slope', ll: [-13.146126, -69.33402], ev: 'orb', loc: 'HiRISE', d: 'On the slope itself: 30 m slopes near 28 degrees in the HiRISE DTM, far over the draft limit, with light and dark streaks running downslope. Kept as a target to show what the planner does when no way stays under the limit.' },
  { n: 'Lineated ground east of the ridge', ll: [-13.084886, -69.329343], ev: 'orb', loc: 'HiRISE', d: 'Ground scored by grooves and ridges running roughly north-north-west. Read by eye as possible landslide debris; not a mapped unit. Under a 15 degree limit it is a separate patch: no way from the habitat stays under the limit.' },
  { n: 'Light-toned outcrop', ll: [-13.073751, -69.316351], ev: 'orb', loc: 'HiRISE', d: 'Bright material in the north-east corner of the tile. Composition not characterized: no mineral map was opened for this page, so it is a landform target only. About 2.9 km from the habitat, beyond the walk-back circle.' },
  { n: 'Bench below the shadowed cliff', ll: [-13.115253, -69.369878], ev: 'orb', loc: 'HiRISE', d: 'A low, flat bench at the foot of a south-east-facing cliff, in shadow in the image because the Sun stood low in the north-west. Its own patch under a 15 degree limit.' },
];
// Hellas targets: located by eye in the HiRISE orthoimage PSP_006133_1410 (shown at 4 m) and checked against the HiRISE DTM;
// good to tens of metres. Landforms mapped from orbit, never measured ground.
const HL_TARGETS = [
  { n: 'Small impact crater', ll: [-38.549557, 54.441863], ev: 'orb', loc: 'HiRISE', d: 'A crater roughly 100 m across and about 10 m deep in the DTM, on the banded surface. About 1.65 km from the habitat, near the edge of the walk-back circle.' },
  { n: 'Edge of a band', ll: [-38.563223, 54.42306], ev: 'orb', loc: 'HiRISE', d: 'A narrow, steeper edge where one band of the banded terrain meets the next: 30 m slopes reach about 10 degrees here, and 3 m slopes about 20. About 1.25 km from the habitat.' },
  { n: 'Tightly folded bands', ll: [-38.60523, 54.467799], ev: 'orb', loc: 'HiRISE', d: 'Bands bent into tight curves, the pattern that gives banded terrain its name. Whether they formed by flow of ice-rich material is an interpretation, not verified here. About 2 km from the habitat, beyond the walk-back circle.' },
  { n: 'Rough, broken band', ll: [-38.613834, 54.491789], ev: 'orb', loc: 'HiRISE', d: 'A strip where the banded surface is broken into blocks and pits. Footing not characterized. About 3.1 km from the habitat.' },
  { n: 'Top of the raised knobby ground', ll: [-38.746943, 54.488547], ev: 'orb', loc: 'HiRISE', d: 'A rise about 800 m above the habitat in the middle of the tile, with knobby, rougher ground on top and flanks near 15 degrees at 30 m. About 10 km away: far beyond the walk-back circle.' },
];
// Targets for Gale, Gusev and Meridiani: the rover's position at the end of the drive on that sol. Olympus: located by eye in HiRISE.
const GALE_TARGETS = [{"n": "Bradbury Landing", "sol": 0, "ll": [-4.589467, 137.441633], "d": "Touchdown 6 Aug 2012 (UTC), on the gravelly plains of Aeolis Palus. First position in NASA's waypoint file."}, {"n": "John Klein drill site, Yellowknife Bay", "sol": 182, "ll": [-4.589485, 137.44913], "d": "First rock drilled by Curiosity (sol 182), in mudstone about 20 m below the landing site. CheMin found clay minerals; the bay was read as an ancient lake that could have supported microbial life (Grotzinger et al. 2014; Vaniman et al. 2014). Position: where the rover parked from sol 166."}, {"n": "Pahrump Hills, base of Mount Sharp", "sol": 753, "ll": [-4.662699, 137.377464], "d": "Curiosity's arrival at the base of Mount Sharp in September 2014, about 9 km of driving from the landing site."}, {"n": "Steepest rover tilt recorded", "sol": 2692, "ll": [-4.736736, 137.380778], "d": "At the end of this drive the rover logged a tilt of 29 degrees, the steepest in NASA's waypoint file on this map. A measured attitude of a six-wheeled rover, not a limit for a walker."}, {"n": "Rover now (last published drive)", "sol": 5073, "ll": [-4.826023, 137.388886], "d": "Position at the end of the waypoint file, about 1 km above the landing site (−3,472 m)."}];
const OLYMPUS_TARGETS = [{"n": "Rim of a small crater on the plateau", "ll": [21.457446, -137.635508], "ev": "orb", "loc": "HiRISE", "d": "The walkable rim of a crater roughly 100 m across, on the cratered plateau above the scarp, about 1.3 km from the habitat. The crater walls themselves are steeper than the limit: no-go cells."}, {"n": "Smooth lobate surface", "ll": [21.511095, -137.625715], "ev": "orb", "loc": "HiRISE", "d": "Smoother ground with lobed edges in a lower trough north of the habitat. Read by eye as possibly a lava flow or a later deposit; not verified. About 2 km from the habitat."}, {"n": "Gullied scarp face", "ll": [21.556645, -137.680118], "ev": "orb", "loc": "HiRISE", "d": "The scarp itself, dropping to the west, scored by gullies and streaks. 30 m slopes near 30 degrees in the HiRISE DTM: far over the draft limit. Shown to demonstrate a target the planner cannot reach under the limit."}, {"n": "Crater cluster at the scarp edge", "ll": [21.523748, -137.675766], "ev": "orb", "loc": "HiRISE", "d": "Small craters crowded near the top edge of the scarp. About 3.5 km from the habitat."}, {"n": "Rough ridged ground", "ll": [21.566768, -137.625715], "ev": "orb", "loc": "HiRISE", "d": "Ridged, rougher ground in the north-east of the tile. About 5 km from the habitat, beyond the walk-back circle."}];
const GUSEV_TARGETS = [{"n": "Columbia Memorial Station (landing site)", "sol": 0, "ll": [-14.565828, 175.475837], "d": "Spirit landed here on 4 Jan 2004 (UTC). First position in the corrected traverse file. The plains around it are basalt, lava rock rich in olivine (McSween et al. 2004)."}, {"n": "Husband Hill crest", "sol": 581, "ll": [-14.587346, 175.523007], "d": "Spirit reached the crest of Husband Hill in the Columbia Hills on sol 581 (21 Aug 2005), about 70 m above the landing site in this DTM. Position at the end of the drive on sol 582."}, {"n": "Troy, west of Home Plate", "sol": 1892, "ll": [-14.600364, 175.525375], "d": "Spirit broke through a firm-looking crust into soft sand here on sol 1892 (1 May 2009) and never got out; last contact was on sol 2208 (22 Mar 2010). Home Plate, read as an explosive volcanic deposit (Squyres et al. 2007), lies just east."}];
const MERIDIANI_TARGETS = [{"n": "Eagle crater (landing site)", "sol": 0, "ll": [-1.947646, -5.524786], "d": "Opportunity rolled to a stop inside this crater, about 22 m across, on 25 Jan 2004 (UTC). Its first outcrop held hematite spherules and jarosite (Squyres et al. 2004; Klingelhöfer et al. 2004). Position: the landing point fitted to this DTM."}, {"n": "Duck Bay, Victoria crater", "sol": 951, "ll": [-2.052065, -5.505928], "d": "Opportunity reached Victoria's rim here on sol 951, about six metres from the lip of the Duck Bay alcove, drove in on sol 1293 and climbed out on sol 1634."}, {"n": "Victoria crater floor", "ll": [-2.05416, -5.49862], "ev": "orb", "loc": "HiRISE", "d": "The dune-covered floor, about 75 m below the rim in this DTM. Opportunity never drove here; the walls are far over the slope limit. Located in the HiRISE DTM."}];
const SITES = {
  jezero: { id: 'jezero', bounds: [[18.3067994, 77.2229331], [18.669315, 77.583964]], hab: [18.444627, 77.450886],
    dtm: 'data/jez_dtm_30m.i16', rough: null, track: 'm20_traverse.json', targets: JEZ_TARGETS },
  // Arcadia walk grid sits inside HRSC orbit 26333 (data/arcadia/build_arcadia.py). Draft habitat on the smoother dark terrain.
  arcadia: { id: 'arcadia', bounds: [[41.22, -148.22], [41.52, -147.88]], hab: [41.36, -148.05],
    dtm: 'data/arcadia/arc_dtm_30m.i16', dtmOffset: -3000, rough: 'data/arcadia/arc_rough_30m.u8', fill: 'data/arcadia/arc_elev_fill_30m.i16', track: null, targets: ARC_TARGETS },
  // Utopia walk grid = HiRISE DTM DTEEC_009467_2225_007384_2225 bounding box (data/utopia/build_utopia.py), inside the SHARAD ice deposit.
  // Draft habitat on the flat floor of a large scalloped depression (3 m slope about 4 degrees); ground strength unverified.
  utopia: { id: 'utopia', bounds: [[42.07450140267274, 86.27294430584746], [42.37977776591766, 86.41470404430147]], hab: [42.2585, 86.325],
    dtm: 'data/utopia/utp_dtm_30m.i16', dtmOffset: -4000, fine: 'data/utopia/utp_fslope_30m.u8', fill: 'data/utopia/utp_elev_fill_30m.i16',
    landforms: 'data/utopia/landforms.geojson', sharad: 'data/utopia/sharad_outline.geojson', rough: null, track: null, targets: UTP_TARGETS },
  // Phoenix walk grid = HiRISE DTM DTEPC_008591_2485_008644_2485 bounds (data/phoenix/build_phoenix.py). Patterned ground throughout.
  // Draft habitat about 430 m from the lander, clear of the hardware.
  phoenix: { id: 'phoenix', bounds: [[68.121495764396, -125.91425183], [68.292335140399, -125.5667691]], hab: [68.215135, -125.731895],
    dtm: 'data/phoenix/phx_dtm_30m.i16', dtmOffset: -4100, fine: 'data/phoenix/phx_fslope_30m.u8', fill: 'data/phoenix/phx_elev_fill_30m.i16',
    rough: null, track: null, targets: PHX_TARGETS },
  // Valles Marineris: one study tile = HiRISE DTM DTEEC_036307_1665_035951_1665 bounds (data/valles/build_valles.py), east Melas Chasma.
  // Draft habitat on a smooth floor patch (30 m slope about 1.4 degrees). cellNoGo: a cell whose own 30 m slope exceeds the limit
  // is a hard no-go for the careful routes and for return feasibility, not only a steep step between cells.
  valles: { id: 'valles', bounds: [[-13.180712040681811, -69.3872872672593], [-13.054265755012386, -69.2974232753865]], hab: [-13.098045, -69.342855],
    dtm: 'data/valles/vm_dtm_30m.i16', dtmOffset: -2000, fine: 'data/valles/vm_fslope_30m.u8', fill: 'data/valles/vm_elev_fill_30m.i16', cellNoGo: true,
    rough: null, track: null, targets: VM_TARGETS },
  // Hellas: one study tile = HiRISE DTM DTEEC_006133_1410_007056_1410 bounds (data/hellas/build_hellas.py), north-west basin floor.
  // Draft habitat on smooth banded floor (30 m slope about 2 degrees). Same steep-cell rule as Valles.
  // Rover sites: HiRISE DTM tiles along the rover's route; the track is proven ground (data/gale/build_gale.py, data/build_tile.py)
  gale: { id: 'gale', bounds: [[-4.86, 137.33], [-4.565, 137.47]], hab: [-4.588534, 137.450611], dtm: 'data/gale/gale_dtm_30m.i16', dtmOffset: -4000, fine: 'data/gale/gale_fslope_30m.u8', fill: 'data/gale/gale_elev_fill_30m.i16',
    rough: null, track: 'data/gale/gale_traverse.json', meta: 'data/gale/gale_grid.json', ortho: 'data/gale/gale_ortho.webp', targets: GALE_TARGETS,
    imgLabel: 'HiRISE orthoimages ESP_040770_1755, ESP_023957_1755, ESP_019698_1750 (shown at 4 m; 2010 to 2015)', dtmLabel: 'three HiRISE stereo DTMs mosaicked (DTEEC_040770_1755_039280_1755, DTEEC_023957_1755_024023_1755, DTEEC_019698_1750_019988_1750)', trackLabel: 'NASA/JPL-Caltech MMGIS MSL traverse and waypoints' },
  gusev: { id: 'gusev', bounds: [[-14.677500369592092, 175.44184907854878], [-14.492559750407155, 175.5547918984464]], hab: [-14.567718, 175.479241], dtm: 'data/gusev/gus_dtm_30m.i16', dtmOffset: -2000, fine: 'data/gusev/gus_fslope_30m.u8', fill: 'data/gusev/gus_elev_fill_30m.i16',
    rough: null, track: 'data/gusev/gus_traverse.json', meta: 'data/gusev/gus_grid.json', ortho: 'data/gusev/gus_ortho.webp', targets: GUSEV_TARGETS,
    imgLabel: 'HiRISE orthoimage PSP_001777_1650 (shown at 4 m; 12 Dec 2006)', dtmLabel: 'HiRISE stereo DTM DTEEC_001513_1655_001777_1650', trackLabel: 'Spirit corrected traverse (T. Parker, PDS Geosciences Node)' },
  meridiani: { id: 'meridiani', bounds: [[-2.160511037901313, -5.536853532114151], [-1.9329432743181303, -5.42152476377214]], hab: [-1.947874, -5.529004], dtm: 'data/meridiani/mer_dtm_30m.i16', dtmOffset: -1400, fine: 'data/meridiani/mer_fslope_30m.u8', fill: 'data/meridiani/mer_elev_fill_30m.i16',
    rough: null, track: 'data/meridiani/mer_traverse.json', meta: 'data/meridiani/mer_grid.json', ortho: 'data/meridiani/mer_ortho.webp', targets: MERIDIANI_TARGETS, travNote: "Opportunity's corrected traverse is in metres from the lander. Placed at the published landing point it ran about 140 m north-west of Victoria crater's rim in this DTM; it is shifted 107 m east and 86 m south to fit the rim (25 m rms).",
    imgLabel: 'HiRISE orthoimage ESP_021747_1780 (shown at 4 m; 18 Mar 2011)', dtmLabel: 'HiRISE stereo DTM DTEEC_021747_1780_022380_1780', trackLabel: 'Opportunity corrected traverse (T. Parker, PDS Geosciences Node), placed at the published landing point' },
  // Olympus Mons: one tile of the basal scarp (data/build_tile.py). Same steep-cell rule as Valles and Hellas.
  olympus: { id: 'olympus', bounds: [[21.446974781961124, -137.7021515549102], [21.587265453850808, -137.58765278718232]], hab: [21.475666, -137.621363], dtm: 'data/olympus/oly_dtm_30m.i16', dtmOffset: 6000, fine: 'data/olympus/oly_fslope_30m.u8', fill: 'data/olympus/oly_elev_fill_30m.i16', cellNoGo: true,
    rough: null, track: null, meta: 'data/olympus/oly_grid.json', ortho: 'data/olympus/oly_ortho.webp', targets: OLYMPUS_TARGETS,
    imgLabel: 'HiRISE orthoimage PSP_001432_2015 (shown at 4 m; 16 Nov 2006)', dtmLabel: 'HiRISE stereo DTM DTEEC_001432_2015_001630_2015' },
  hellas: { id: 'hellas', bounds: [[-38.865922635955734, 54.377997378197804], [-38.5062842679306, 54.54384444725089]], hab: [-38.577394, 54.44316],
    dtm: 'data/hellas/hl_dtm_30m.i16', dtmOffset: -7000, fine: 'data/hellas/hl_fslope_30m.u8', fill: 'data/hellas/hl_elev_fill_30m.i16', cellNoGo: true,
    rough: null, track: null, targets: HL_TARGETS },
};

// ---- Grid geometry: cell centres, equirectangular at the grid's mid latitude
function geom(b) {
  const lat0 = b[1][0], lat1 = b[0][0], lon0 = b[0][1], lon1 = b[1][1];
  const latC = (lat0 + lat1) / 2, mLon = M_PER_DEG * Math.cos(latC * RAD), mLat = M_PER_DEG;
  return { lat0, lat1, lon0, lon1, mLon, mLat, nx: Math.ceil((lon1 - lon0) * mLon / CELL), ny: Math.ceil((lat0 - lat1) * mLat / CELL) };
}
// THEMIS night IR tiles at Trek zoom 9 covering the grid (Jezero: rows 202-203, cols 731-732)
function themisTiles(b) {
  const td = 180 / 512;
  return { td, c0: Math.floor((b[0][1] + 180) / td), c1: Math.floor((b[1][1] + 180) / td), r0: Math.floor((90 - b[1][0]) / td), r1: Math.floor((90 - b[0][0]) / td) };
}
function loadThemis(b) {
  const NT = themisTiles(b), c = document.createElement('canvas'); c.width = (NT.c1 - NT.c0 + 1) * 256; c.height = (NT.r1 - NT.r0 + 1) * 256;
  const ctx = c.getContext('2d'), jobs = [];
  for (let r = NT.r0; r <= NT.r1; r++) for (let col = NT.c0; col <= NT.c1; col++) jobs.push(new Promise((res, rej) => {
    const im = new Image(); im.crossOrigin = 'anonymous';
    // a missing tile (the controlled mosaic stops short of the poles) stays transparent: no data, not dark sand
    im.onload = () => { ctx.drawImage(im, (col - NT.c0) * 256, (r - NT.r0) * 256); res(); }; im.onerror = () => { c.missing = (c.missing || 0) + 1; res(); };
    im.src = 'https://trek.nasa.gov/tiles/Mars/EQ/' + NIGHT_ID + '/1.0.0/default/default028mm/9/' + r + '/' + col + '.png';
  }));
  return Promise.all(jobs).then(() => { c.tiles = jobs.length; return c; });
}

// Terrain grid for routing. Inputs are real: THEMIS night IR pixels (orbital proxy for sand), rover track points
// [lat, lon, el] (proven ground, Jezero only), the site's elevation grid, and on Arcadia the HRSC texture grid.
function buildGrid({ site, nirCanvas, dtmBuf, roughBuf, fineBuf, pts = [] }) {
  const b = site.bounds, { lat0, lon0, mLon, mLat, nx, ny } = geom(b), n = nx * ny, arc = site.id === 'arcadia';
  const sand = new Float32Array(n), driven = new Uint8Array(n), elev = new Float32Array(n).fill(NaN), ecount = new Uint16Array(n);
  const NT = themisTiles(b), W = nirCanvas.width, H = nirCanvas.height, pxDeg = NT.td / 256, tLon0 = -180 + NT.c0 * NT.td, tLat0 = 90 - NT.r0 * NT.td;
  const img = nirCanvas.getContext('2d').getImageData(0, 0, W, H).data, raw = new Float32Array(n);
  for (let y = 0; y < ny; y++) for (let x = 0; x < nx; x++) {
    const lon = lon0 + (x + .5) * CELL / mLon, lat = lat0 - (y + .5) * CELL / mLat;
    const px = Math.min(W - 1, Math.max(0, Math.floor((lon - tLon0) / pxDeg))), py = Math.min(H - 1, Math.max(0, Math.floor((tLat0 - lat) / pxDeg))), o = (py * W + px) * 4;
    raw[y * nx + x] = img[o + 3] === 0 ? NaN : img[o];          // transparent pixel = no THEMIS data, not dark sand
  }
  // data-driven normalisation: 15th and 65th percentile of night brightness over the grid (cells with data)
  const sorted = raw.filter(v => !isNaN(v)).sort(), m = sorted.length || 1, p15 = sorted[Math.floor(m * .15)], p65 = sorted[Math.floor(m * .65)];
  for (let i = 0; i < n; i++) sand[i] = isNaN(raw[i]) ? NaN : Math.min(1, Math.max(0, (p65 - raw[i]) / Math.max(1, p65 - p15)));
  const toCell = (lat, lon) => { const x = Math.floor((lon - lon0) * mLon / CELL), y = Math.floor((lat0 - lat) * mLat / CELL); return (x < 0 || y < 0 || x >= nx || y >= ny) ? -1 : y * nx + x; };
  for (const p of pts) {
    const i = toCell(p[0], p[1]); if (i < 0) continue;
    const x = i % nx, y = (i / nx) | 0;
    for (let dy = -2; dy <= 2; dy++) for (let dx = -2; dx <= 2; dx++) { const xx = x + dx, yy = y + dy; if (xx >= 0 && yy >= 0 && xx < nx && yy < ny && dx * dx + dy * dy <= 4) driven[yy * nx + xx] = 1; }
    if (p[2] != null) { elev[i] = (isNaN(elev[i]) ? 0 : elev[i] * ecount[i]) / (ecount[i] + 1) + p[2] / (ecount[i] + 1); ecount[i]++; }
  }
  // Elevation grid, same nx x ny: Int16 decimetres above site.dtmOffset (m), -32768 = no data
  // (Jezero: CTX DTM, offset 0; Arcadia: MOLA, offset -3000 m because -3,700 m in decimetres overflows Int16; no data = bin without a laser shot)
  let dtm = false, shotN = 0, cnt = 0, mean = 0, sd = 0;
  const off = site.dtmOffset || 0;
  if (dtmBuf && dtmBuf.byteLength === n * 2) {
    const d = new Int16Array(dtmBuf); let sum = 0, sum2 = 0;
    for (let i = 0; i < n; i++) { if (d[i] !== -32768) { const v = d[i] / 10 + off; shotN++; if (!isNaN(elev[i])) { const df = v - elev[i]; sum += df; sum2 += df * df; cnt++; } elev[i] = v; } }
    mean = cnt ? sum / cnt : 0; sd = cnt ? Math.sqrt(Math.max(0, sum2 / cnt - mean * mean)) : 0; dtm = true;
  }
  // Arcadia: HRSC image-texture roughness 0..1, NaN where no HRSC pixel
  let rough = null;
  if (roughBuf && roughBuf.byteLength === n) { const r = new Uint8Array(roughBuf); rough = new Float32Array(n); for (let i = 0; i < n; i++) rough[i] = r[i] === 255 ? NaN : r[i] / 254; }
  // Utopia: steepest 3 m slope inside each 30 m cell from the 1 m HiRISE DTM (quarter degrees), NaN where no DTM
  let fine = null;
  if (fineBuf && fineBuf.byteLength === n) { const f = new Uint8Array(fineBuf); fine = new Float32Array(n); for (let i = 0; i < n; i++) fine[i] = f[i] === 255 ? NaN : f[i] / 4; }
  // Valles: each cell's own 30 m slope (central differences); NaN where a neighbour has no elevation
  let cslope = null;
  if (site.cellNoGo && dtm) { cslope = new Float32Array(n).fill(NaN);
    for (let y = 1; y < ny - 1; y++) for (let x = 1; x < nx - 1; x++) { const i = y * nx + x, gx = (elev[i + 1] - elev[i - 1]) / (2 * CELL), gy = (elev[i + nx] - elev[i - nx]) / (2 * CELL);
      cslope[i] = Math.atan(Math.hypot(gx, gy)) * 180 / Math.PI; } }
  let drv = 0; for (let i = 0; i < n; i++) drv += driven[i];
  const sandNone = sorted.length === 0;                                               // no THEMIS night IR over this grid
  return { ready: true, site: site.id, arc, sandNone, nx, ny, n, sand, driven, elev, dtm, rough, fine, cslope, lat0, lon0, mLon, mLat, toCell, p15, p65, shotN, drv,
    dtmCheck: { cnt, mean, sd }, cellLL: i => ({ lat: lat0 - ((i / nx | 0) + .5) * CELL / mLat, lng: lon0 + ((i % nx) + .5) * CELL / mLon }) };
}

// USGS 1:75K Jezero geologic map (SIM 3464): mapped sand ridges (unit Aeb), rasterised onto the routing grid.
// Sets G.usgs: 1 = mapped sand, 2 = margin cell next to it, so routes keep a cell (30 m) of clearance and the drawn,
// straightened route (12 m tolerance) cannot clip the edge of a sand field. Returns the number of mapped cells.
function rasterAeb(G, geo) { const r = rasterPolys(G, geo, f => f.properties.u === 'Aeb'); if (r) G.usgs = r.u; return r ? r.cnt : 0; }
// Utopia: ice-related landforms marked by eye in HiRISE (data/utopia/landforms.geojson). G.ice: 1 = inside, 2 = margin.
function rasterIce(G, geo) { const r = rasterPolys(G, geo, f => f.geometry.type !== 'Point' && f.properties.route !== false); if (r) G.ice = r.u; return r ? r.cnt : 0; }
// Polygons onto the grid: 1 = inside, 2 = one-cell margin around it. Returns {u, cnt} with cnt = inside cells.
function rasterPolys(G, geo, keep) {
  if (!geo || !G || !G.ready) return null;
  const { nx, ny, lat0, lon0, mLon, mLat } = G, c = document.createElement('canvas'); c.width = nx; c.height = ny;
  const g = c.getContext('2d'); g.fillStyle = '#fff';
  for (const f of geo.features) { if (!keep(f) || !f.geometry || f.geometry.type === 'Point') continue;
    const polys = f.geometry.type === 'Polygon' ? [f.geometry.coordinates] : f.geometry.coordinates;
    for (const poly of polys) { g.beginPath(); for (const ring of poly) ring.forEach(([lo, la], k) => { const x = (lo - lon0) * mLon / CELL, y = (lat0 - la) * mLat / CELL; k ? g.lineTo(x, y) : g.moveTo(x, y); }); g.fill('evenodd'); } }
  const d = g.getImageData(0, 0, nx, ny).data, u = new Uint8Array(nx * ny); let cnt = 0;
  for (let i = 0; i < nx * ny; i++) if (d[4 * i + 3] > 127) { u[i] = 1; cnt++; }
  for (let y = 0; y < ny; y++) for (let x = 0; x < nx; x++) { const i = y * nx + x; if (u[i]) continue;
    for (let dy = -1; dy <= 1 && !u[i]; dy++) for (let dx = -1; dx <= 1; dx++) { const xx = x + dx, yy = y + dy; if (xx >= 0 && yy >= 0 && xx < nx && yy < ny && u[yy * nx + xx] === 1) { u[i] = 2; break; } } }
  return { u, cnt };
}

// Elevation at a point: bilinear in the grid; null where any corner has no data.
function elevAt(G, ll) {
  if (!G || !G.ready || !G.dtm) return null;
  const fx = (ll.lng - G.lon0) * G.mLon / CELL - .5, fy = (G.lat0 - ll.lat) * G.mLat / CELL - .5, x0 = Math.floor(fx), y0 = Math.floor(fy);
  if (x0 < 0 || y0 < 0 || x0 >= G.nx - 1 || y0 >= G.ny - 1) return null;
  const tx = fx - x0, ty = fy - y0, e = G.elev, i = y0 * G.nx + x0;
  const v = e[i] * (1 - tx) * (1 - ty) + e[i + 1] * tx * (1 - ty) + e[i + G.nx] * (1 - tx) * ty + e[i + G.nx + 1] * tx * ty;
  return isNaN(v) ? null : v;
}
const cellVal = (G, arr, ll) => { if (!G || !G.ready || !arr) return null; const i = G.toCell(ll.lat, ll.lng); return i < 0 || isNaN(arr[i]) ? null : arr[i]; };
const sandAt = (G, ll) => cellVal(G, G && G.sand, ll);
const roughAt = (G, ll) => cellVal(G, G && G.rough, ll);
const drivenAt = (G, ll) => { if (!G || !G.ready) return null; const i = G.toCell(ll.lat, ll.lng); return i < 0 ? null : G.driven[i]; };

// A* over the 8-neighbour grid. mode: 'terrain' | 'best' | 'soft'. Returns the path after `from`, ending at `to`.
function astar(G, from, to, mode, slopeLim, opts = {}) {
  if (!G || !G.ready) return null;
  const s0 = G.toCell(from.lat, from.lng), t0 = G.toCell(to.lat, to.lng); if (s0 < 0 || t0 < 0) return null;
  const { nx, ny, n, sand, driven, elev, rough, arc } = G;
  const g = new Float32Array(n).fill(Infinity), par = new Int32Array(n).fill(-1), done = new Uint8Array(n);
  const hp = []; const push = (f, i) => { hp.push([f, i]); let k = hp.length - 1; while (k) { const p = (k - 1) >> 1; if (hp[p][0] <= hp[k][0]) break; [hp[p], hp[k]] = [hp[k], hp[p]]; k = p; } };
  const pop = () => { const t = hp[0], l = hp.pop(); if (hp.length) { hp[0] = l; let k = 0; for (;;) { const a = 2 * k + 1, b = a + 1; let s = k; if (a < hp.length && hp[a][0] < hp[s][0]) s = a; if (b < hp.length && hp[b][0] < hp[s][0]) s = b; if (s === k) break; [hp[s], hp[k]] = [hp[k], hp[s]]; k = s; } } return t; };
  const tx = t0 % nx, ty = (t0 / nx) | 0;
  const h = i => { const dx = Math.abs(i % nx - tx), dy = Math.abs(((i / nx) | 0) - ty); return (Math.max(dx, dy) + (Math.SQRT2 - 1) * Math.min(dx, dy)) * CELL * 0.6; };
  const usgs = G.usgs, fine = G.fine, ice = G.ice, cs = G.cslope, avoid = opts.avoid, careful = mode === 'best' || mode === 'soft' || mode === 'direct';
  // Costs per metre. All penalties are team assumptions (draft), not measured traverse difficulty.
  const mu = mode === 'direct'                                                         // emergency: distance only, slope limit still enforced
    ? j => 1 + (avoid && avoid[j] ? 2 : 0)
    : j => { let m = 1 + 2.5 * (isNaN(sand[j]) ? 0 : sand[j]);
    if (usgs) m += usgs[j] === 1 ? 3 : usgs[j] === 2 ? 1 : 0;                         // Jezero: mapped sand ridges (USGS Aeb) and their margin
    if (rough && !isNaN(rough[j])) m += 1.5 * rough[j];                                // Arcadia: HRSC texture, yardang proxy
    if (fine && !isNaN(fine[j])) m += fine[j] > slopeLim ? 2 : fine[j] > slopeLim - 5 ? 0.7 : 0;   // Utopia: steep 3 m slopes inside the cell
    if (ice) m += ice[j] === 1 ? 2 : ice[j] === 2 ? 1 : 0;                              // Utopia: ice-related landforms and their margin
    if (avoid && avoid[j]) m += 2;                                                     // alternate return: stay off the primary corridor
    if (driven[j]) m *= 0.6; else if (mode === 'best' || mode === 'soft') m += 1.0;
    if (arc && (mode === 'best' || mode === 'soft') && isNaN(elev[j])) m += 0.5;          // Arcadia: prefer cells where MOLA has a shot
    return m; };
  g[s0] = 0; push(h(s0), s0); let expanded = 0;
  while (hp.length) {
    const [, i] = pop(); if (done[i]) continue; done[i] = 1; if (i === t0) break; if (++expanded > 400000) return null;
    const x = i % nx, y = (i / nx) | 0;
    for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
      if (!dx && !dy) continue; const xx = x + dx, yy = y + dy; if (xx < 0 || yy < 0 || xx >= nx || yy >= ny) continue;
      const j = yy * nx + xx; if (done[j]) continue;
      const d = Math.hypot(dx, dy) * CELL;
      let steep = 0;
      if (careful && j !== t0 && !isNaN(elev[i]) && !isNaN(elev[j])) { const sl = Math.atan2(Math.abs(elev[j] - elev[i]), d) * 180 / Math.PI; if (sl > slopeLim) { if (mode !== 'soft') continue; steep = sl / slopeLim; } }
      // sites with cellNoGo (Valles, Hellas, Olympus): a cell steeper than the limit is a hard no-go in every routed mode, the target cell included
      if (cs && cs[j] > slopeLim) { if (mode !== 'soft') continue; steep = Math.max(steep, cs[j] / slopeLim); }
      const c = g[i] + d * mu(j) * (1 + 8 * steep);
      if (c < g[j]) { g[j] = c; par[j] = i; push(c + h(j), j); }
    }
  }
  if (!done[t0]) return null;
  const cells = []; for (let i = t0; i !== -1; i = par[i]) cells.push(i); cells.reverse();
  return simplify(G, cells.map(i => G.cellLL(i)), 12).slice(1, -1).concat([to]);
}
// Route under the slope limit; if no such path exists (a point inside a crater), take the least steep one and say so.
// On sites with hard no-go cells there is no fallback: { path: null, nofeas: true } = no feasible path under stated assumptions.
function routeTo(G, from, to, lim) {
  let path = astar(G, from, to, 'best', lim); if (path) return { path, soft: false };
  if (G.cslope) return { path: null, nofeas: true };
  path = astar(G, from, to, 'soft', lim); return path ? { path, soft: true } : null;
}
function simplify(G, ll, tol) { // Douglas-Peucker on metres
  if (ll.length < 3) return ll;
  const perp = (p, a, b) => { const ax = (p.lng - a.lng) * G.mLon, ay = (p.lat - a.lat) * G.mLat, bx = (b.lng - a.lng) * G.mLon, by = (b.lat - a.lat) * G.mLat; const l2 = bx * bx + by * by || 1; const t = Math.max(0, Math.min(1, (ax * bx + ay * by) / l2)); return Math.hypot(ax - t * bx, ay - t * by); };
  let idx = 0, md = 0; for (let i = 1; i < ll.length - 1; i++) { const d = perp(ll[i], ll[0], ll[ll.length - 1]); if (d > md) { md = d; idx = i; } }
  if (md > tol) { const a = simplify(G, ll.slice(0, idx + 1), tol), b = simplify(G, ll.slice(idx), tol); return a.slice(0, -1).concat(b); }
  return [ll[0], ll[ll.length - 1]];
}
// walk a leg in 30 m steps so long straight legs are judged on every cell they cross, not their midpoint
function samples(a, b, step) { const d = dist(a, b), n = Math.max(1, Math.ceil(d / step)), out = []; for (let k = 0; k <= n; k++) { const f = k / n; out.push({ lat: a.lat + (b.lat - a.lat) * f, lng: a.lng + (b.lng - a.lng) * f }); } return out; }
// Length, sandy / proven / rough shares, share with known slope, breaks (steps over the limit + leaving the walk-back circle)
function routeMetrics(G, path, from, { slopeLim, radius, hab, elevFn }) {
  const full = [from, ...path], el = elevFn || (ll => elevAt(G, ll)); let len = 0, sandy = 0, drv = 0, known = 0, breaks = 0, far = 0, rgh = 0, aeb = 0, icez = 0, fst = 0;
  const cellOf = ll => G && G.ready ? G.toCell(ll.lat, ll.lng) : -1;
  for (let i = 1; i < full.length; i++) {
    const sp = samples(full[i - 1], full[i], CELL); let ePrev = el(sp[0]);
    for (let k = 1; k < sp.length; k++) {
      const d = dist(sp[k - 1], sp[k]); len += d;
      const mid = { lat: (sp[k - 1].lat + sp[k].lat) / 2, lng: (sp[k - 1].lng + sp[k].lng) / 2 };
      const s = sandAt(G, mid); if (s != null && s > 0.5) sandy += d;
      if (drivenAt(G, mid)) drv += d;
      const rg = roughAt(G, mid); if (rg != null && rg > 0.5) rgh += d;
      const ci = cellOf(mid);
      if (ci >= 0) { if (G.usgs && G.usgs[ci] === 1) aeb += d; if (G.ice && G.ice[ci]) icez += d; if (G.fine && G.fine[ci] > slopeLim) fst += d; }
      const e1 = el(sp[k]);
      if (ePrev != null && e1 != null) { known += d; if (Math.atan2(Math.abs(e1 - ePrev), d) * 180 / Math.PI > slopeLim) breaks++; }
      ePrev = e1;
      far = Math.max(far, dist(hab, sp[k]));
    }
  }
  if (far > radius) breaks++;
  const L = len || 1;
  return { len, sandy: sandy / L, drv: drv / L, rough: rgh / L, aeb: aeb / L, ice: icez / L, fineSteep: fst / L, known: known / L, breaks, far };
}

// ---- Route explainability: why a candidate differs from the shortest line, in metres actually computed
const HAZ = [['aeb', 'mapped sand ridges (USGS)'], ['sandy', 'night-IR sandy ground'], ['rough', 'yardang-textured ground (HRSC proxy)'],
  ['fineSteep', 'ground with 3 m slopes over the limit (HiRISE DTM)'], ['ice', 'ice-related landform zones']];
function explain(m, base) {
  if (!m || !base) return [];
  const out = [], dl = m.len - base.len, fm = v => v >= 1000 ? (v / 1000).toFixed(1) + ' km' : Math.round(v) + ' m';
  for (const [k, label] of HAZ) { const a = (base[k] || 0) * base.len, b = (m[k] || 0) * m.len;
    if (a - b >= 30) out.push('avoids ' + fm(a - b) + ' of ' + label + ' that the shortest crosses');
    else if (b - a >= 30) out.push('crosses ' + fm(b - a) + ' more ' + label); }
  if (m.breaks < base.breaks) out.push('fewer steps over the slope limit (' + m.breaks + ' vs ' + base.breaks + ')');
  const dd = m.drv * m.len - base.drv * base.len; if (dd >= 30) out.push('+' + fm(dd) + ' on ground the rover drove');
  if (m.known - base.known >= 0.05) out.push('slope characterized on ' + Math.round(m.known * 100) + '% of it vs ' + Math.round(base.known * 100) + '%');
  const nHaz = out.length;
  out.push(Math.abs(dl) < 30 ? 'about the same length as the shortest' : (dl > 0 ? fm(dl) + ' longer' : fm(-dl) + ' shorter') + ' than the shortest');
  if (!nHaz) out.unshift('no mapped hazard differs from the shortest line by 30 m or more');
  return out;
}

// ---- Confidence as plain categories (high, medium, low, not characterized), never percentages
function confidence(siteId, m) {
  const k = m ? m.known : 0, c = {};
  if (siteId === 'gale') c.terrain = k >= .9 ? ['High', "HiRISE stereo DTMs, 1 m posts, on every step, checked against Curiosity's track elevations"] : k >= .3 ? ['Medium', 'part of the route is outside the HiRISE DTMs'] : ['Not characterized', 'route is mostly outside the HiRISE DTMs'];
  else if (siteId === 'gusev' || siteId === 'meridiani') c.terrain = k >= .9 ? ['Medium', 'HiRISE stereo DTM, 1 m posts, on every step; the rover track has no elevations to check it against'] : k >= .3 ? ['Low', 'part of the route is outside the HiRISE DTM'] : ['Not characterized', 'route is mostly outside the HiRISE DTM'];
  else if (siteId === 'jezero') c.terrain = k >= .9 ? ['High', 'CTX stereo DTM 20 m on every step, checked against rover-track elevations'] : ['Medium', 'CTX DTM, part of the route lacks elevation'];
  else if (siteId === 'utopia' || siteId === 'phoenix' || siteId === 'valles' || siteId === 'hellas' || siteId === 'olympus') c.terrain = k >= .9 ? ['Medium', 'HiRISE stereo DTM, 1 m posts, on every step; no ground check here'] : k >= .3 ? ['Low', 'part of the route is outside the HiRISE DTM strip'] : ['Not characterized', 'route is mostly outside the HiRISE DTM strip'];
  else c.terrain = k >= .3 ? ['Low', 'MOLA slope in 463 m bins; walk-sized ground not resolved'] : ['Not characterized', 'most steps fall in MOLA bins with no laser shot'];
  c.weather = siteId === 'gale' ? ['Medium', 'Curiosity REMS measures the weather at the rover (latest sols in the outlook); not along your route'] : siteId === 'gusev' || siteId === 'meridiani' ? ['Not characterized', 'the rover carried no weather station; it measured dust in the air early in the mission only'] : siteId === 'olympus' ? ['Not characterized', 'no weather has ever been measured on Olympus Mons'] : siteId === 'jezero' ? ['Low', 'Jezero reference ranges (MEDA) exist, but no live local weather feed'] : siteId === 'phoenix' ? ['Low', 'Phoenix MET measured here for 5 months in 2008 (reference only); no live feed'] : siteId === 'valles' ? ['Not characterized', 'no weather has ever been measured in the canyon; canyon winds and inversions come from models only'] : siteId === 'hellas' ? ['Not characterized', 'no weather, dust or pressure has ever been measured in Hellas'] : ['Not characterized', 'no local weather data; Gale and Jezero values are reference ranges only'];
  c.position = ['Not characterized', 'crew position is simulated; no suit tag is connected'];
  return c;
}

// ---- Return options from a point: primary (recommended cost), alternate (off the primary corridor), emergency (shortest under the slope limit)
function pathCells(G, from, path) {
  const u = new Uint8Array(G.n), full = [from, ...path];
  for (let i = 1; i < full.length; i++) for (const p of samples(full[i - 1], full[i], CELL / 2)) {
    const c = G.toCell(p.lat, p.lng); if (c < 0) continue; const x = c % G.nx, y = (c / G.nx) | 0;
    for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) { const xx = x + dx, yy = y + dy; if (xx >= 0 && yy >= 0 && xx < G.nx && yy < G.ny) u[yy * G.nx + xx] = 1; }
  }
  return u;
}
function returnOptions(G, from, hab, lim, walkbackM) {
  const len = p => { let s = 0, a = from; for (const q of p) { s += dist(a, q); a = q; } return s; };
  const pack = (p, soft) => p ? { path: p, len: len(p), soft: !!soft, ok: len(p) <= walkbackM } : null;
  const hard = !!G.cslope, pr = routeTo(G, from, hab, lim), primary = pr && pr.path ? pack(pr.path, pr.soft) : null;
  let alternate = null;
  if (primary) { const av = pathCells(G, from, primary.path); const p = astar(G, from, hab, 'best', lim, { avoid: av }); alternate = p ? pack(p) : hard ? null : pack(astar(G, from, hab, 'soft', lim, { avoid: av }), true); }
  const e = astar(G, from, hab, 'direct', lim), emergency = e ? pack(e) : hard ? null : pack(astar(G, from, hab, 'soft', lim), true);
  return { primary, alternate, emergency };
}

// ---- Return feasibility (Valles Marineris, usable anywhere): from every cell, the shortest walk back to the habitat that
// never takes a 30 m step over the slope limit, never enters a cell whose own 30 m slope exceeds it (sites with cellNoGo)
// and never enters a cell without elevation. Dijkstra outward from the habitat: steps are symmetric, so the distance out
// equals the distance back. Calculated from orbital data; it can miss anything smaller than the DTM resolves.
// cls: 1 back within walkbackM, 2 a path exists but is longer, 3 the cell itself is steep (wall or scarp),
//      4 no elevation (not characterized), 5 cut off: every way back crosses steep or uncharacterized ground.
const RF_REASON = { 1: 'back within the walk-back limit', 2: 'a way back exists but is longer than the walk-back limit', 3: 'steep cell: wall or scarp over the slope limit',
  4: 'no elevation: not characterized', 5: 'cut off: every way back crosses steep or uncharacterized ground' };
function returnField(G, hab, lim, walkbackM) {
  if (!G || !G.ready || !G.dtm) return null;
  const { nx, ny, n, elev, cslope } = G, d = new Float32Array(n).fill(Infinity), cls = new Uint8Array(n), done = new Uint8Array(n);
  const steepCell = i => cslope ? cslope[i] > lim : false, bad = i => isNaN(elev[i]) || steepCell(i);
  const s0 = G.toCell(hab.lat, hab.lng);
  const hp = []; const push = (f, i) => { hp.push([f, i]); let k = hp.length - 1; while (k) { const p = (k - 1) >> 1; if (hp[p][0] <= hp[k][0]) break; [hp[p], hp[k]] = [hp[k], hp[p]]; k = p; } };
  const pop = () => { const t = hp[0], l = hp.pop(); if (hp.length) { hp[0] = l; let k = 0; for (;;) { const a = 2 * k + 1, b = a + 1; let s = k; if (a < hp.length && hp[a][0] < hp[s][0]) s = a; if (b < hp.length && hp[b][0] < hp[s][0]) s = b; if (s === k) break; [hp[s], hp[k]] = [hp[k], hp[s]]; k = s; } } return t; };
  if (s0 >= 0 && !isNaN(elev[s0])) { d[s0] = 0; push(0, s0); }                       // the habitat cell itself is always the start
  while (hp.length) {
    const [, i] = pop(); if (done[i]) continue; done[i] = 1;
    const x = i % nx, y = (i / nx) | 0;
    for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
      if (!dx && !dy) continue; const xx = x + dx, yy = y + dy; if (xx < 0 || yy < 0 || xx >= nx || yy >= ny) continue;
      const j = yy * nx + xx; if (done[j] || bad(j)) continue;
      const st = Math.hypot(dx, dy) * CELL; if (Math.atan2(Math.abs(elev[j] - elev[i]), st) * 180 / Math.PI > lim) continue;
      const c = d[i] + st; if (c < d[j]) { d[j] = c; push(c, j); }
    }
  }
  const cnt = [0, 0, 0, 0, 0, 0];
  for (let i = 0; i < n; i++) { cls[i] = isNaN(elev[i]) ? 4 : d[i] <= walkbackM ? 1 : d[i] < Infinity ? 2 : steepCell(i) ? 3 : 5; cnt[cls[i]]++; }
  return { d, cls, cnt, habOk: s0 >= 0 && !isNaN(elev[s0]) };
}

// ---- Line of sight from an antenna (mast antH metres above the ground at `ant`) to a receiver recH metres above each cell.
// Uses the elevation array given (DTM, or the display fill) and Mars curvature. A calculation from orbital terrain, not a
// signal measurement. vis: 1 clear, 2 blocked, 3 not characterized (no elevation at either end or along the line),
// 0 not computed (farther than maxD metres from the antenna).
function viewshed(G, ant, antH, recH, elevArr, maxD = Infinity) {
  if (!G || !G.ready) return null;
  const e = elevArr || G.elev, { nx, ny, n } = G, vis = new Uint8Array(n), a0 = G.toCell(ant.lat, ant.lng);
  if (a0 < 0 || isNaN(e[a0])) { vis.fill(3); return { vis, cnt: [0, 0, 0, n] }; }
  const ax = (ant.lng - G.lon0) * G.mLon / CELL, ay = (G.lat0 - ant.lat) * G.mLat / CELL, z0 = e[a0] + antH, cnt = [0, 0, 0, 0];
  for (let t = 0; t < n; t++) {
    const tx = t % nx + .5, ty = ((t / nx) | 0) + .5, Dc = Math.hypot(tx - ax, ty - ay), D = Dc * CELL;
    if (D > maxD) { cnt[0]++; continue; }
    if (isNaN(e[t])) { vis[t] = 3; cnt[3]++; continue; }
    if (D < CELL) { vis[t] = 1; cnt[1]++; continue; }
    const tgt = (e[t] + recH - D * D / (2 * R) - z0) / D; let res = 1;
    const N = Math.ceil(Dc * 2);
    for (let k = 1; k < N; k++) {
      const f = k / N, sx = Math.floor(ax + (tx - ax) * f), sy = Math.floor(ay + (ty - ay) * f), s = sy * nx + sx, v = e[s];
      if (isNaN(v)) { res = 3; continue; }
      const dk = D * f; if ((v - dk * dk / (2 * R) - z0) / dk > tgt) { res = 2; break; }
    }
    vis[t] = res; cnt[res]++;
  }
  return { vis, cnt };
}

// ---- Sky view at a point: horizon elevation angle in nAz directions over the given elevation array (the tile only:
// walls beyond its edge are not seen, so the open share is an upper bound), and the share of the sky's solid angle above
// that horizon, mean(1 - sin h). An input to a radiation estimate, not a dose.
function skyView(G, ll, elevArr, nAz = 36) {
  if (!G || !G.ready) return null;
  const e = elevArr || G.elev, i0 = G.toCell(ll.lat, ll.lng); if (i0 < 0 || isNaN(e[i0])) return null;
  const x0 = (ll.lng - G.lon0) * G.mLon / CELL, y0 = (G.lat0 - ll.lat) * G.mLat / CELL, z0 = e[i0] + 1.5, hor = []; let open = 0;
  for (let a = 0; a < nAz; a++) {
    const th = a * 2 * Math.PI / nAz, sx = Math.sin(th), sy = -Math.cos(th); let best = 0;   // azimuth from north, clockwise
    for (let k = 1; ; k++) { const x = Math.floor(x0 + sx * k * .7), y = Math.floor(y0 + sy * k * .7); if (x < 0 || y < 0 || x >= G.nx || y >= G.ny) break;
      const v = e[y * G.nx + x]; if (isNaN(v)) continue; const dd = k * .7 * CELL, ang = Math.atan2(v - dd * dd / (2 * R) - z0, dd); if (ang > best) best = ang; }
    hor.push(best * 180 / Math.PI); open += 1 - Math.sin(best);
  }
  return { horizon: hor, open: open / nAz, maxH: Math.max(...hor), nAz };
}

root.MarswalkCore = { R, CELL, M_PER_DEG, NIGHT_ID, dist, SITES, geom, themisTiles, loadThemis, buildGrid, rasterAeb, rasterIce, rasterPolys, explain, confidence, returnOptions, pathCells, elevAt, sandAt, roughAt, drivenAt, astar, routeTo, simplify, samples, routeMetrics,
  returnField, RF_REASON, viewshed, skyView };
})(window);

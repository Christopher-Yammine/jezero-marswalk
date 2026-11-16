# Findings: data and references behind the Marswalk planner

HackAthlone 2026 (NASA Space Apps, 13 to 15 Nov 2026, Athlone). Challenge: Interplanetary Survival Guide, Martian Map.
Team: Chris Yammine, Mariam Hamdan, Helena Mansour. First site: Jezero crater (Perseverance landing site); the planner has since grown to ten walk sites across Mars.

Everything below was tested on 6 and 7 Nov 2026. "Verified" means the URL returned tiles or data in a browser or curl.

## 1. Why Jezero

- Densest public data stack on Mars: 25 cm HiRISE and 6 m CTX controlled mosaics, THEMIS thermal day/night, MOLA/HRSC relief, all served as plain web map tiles by NASA Mars Trek.
- Perseverance's full traverse is public with elevation at every vertex (559 drives, sols 14 to 2022, 46.05 km). A rover actually drove this ground, so our route maths can be checked against NASA odometry.
- Weather and radiation have citable in-situ numbers (MEDA on Perseverance, RAD on Curiosity).
- Honest negative: Jezero at 18 N is outside the mid-latitude subsurface ice belt (SWIM 2.0, https://swim.psi.edu). Shown as a finding, not hidden.

## 2. NASA Mars Trek tiles (verified)

Tile URL pattern (WMTS, equirectangular, 2x1 tiles at zoom 0, row origin top):

    https://trek.nasa.gov/tiles/Mars/EQ/{LAYER}/1.0.0/default/default028mm/{z}/{row}/{col}.{png|jpg}

CORS header is `Access-Control-Allow-Origin: *`, so tiles load straight into Leaflet. Jezero sits at zoom 10, row 407, col 1464.
Layer catalogue: `https://trek.nasa.gov/mars/TrekServices/ws/index/eq/searchItems?proj=eq&start=0&rows=200&intersects=77.45,18.44,77.46,18.45` (2038 records).

| Layer id | What | Max zoom | Bounds (lon E, lat N) |
|---|---|---|---|
| `JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first_dd` | MRO HiRISE 25 cm controlled mosaic | 17 | 77.223 to 77.584, 18.307 to 18.669 |
| `JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0` | MRO CTX 6 m controlled mosaic | 13 | 77.16 to 77.70, 18.21 to 18.72 |
| `NES_JEZ_MID_Visible_Mosaic_HiRISE_CTX_HRSC_GCS_MARS_07-10-2018` | Regional HiRISE+CTX+HRSC blend | 17 | 76.79 to 77.73, 17.58 to 18.69 |
| `THEMIS_DayIR_ControlledMosaics_100m_v2_oct2018` | Odyssey THEMIS day IR 100 m | 9 | global |
| `THEMIS_NightIR_ControlledMosaics_100m_v2_oct2018` | Odyssey THEMIS night IR 100 m (rock vs sand) | 9 | global |
| `Mars_MOLA_blend200ppx_HRSC_ClrShade_clon0dd_200mpp_lzw` | MOLA + HRSC colour shaded relief (jpg) | 8 | global |
| `Mars_Viking_MDIM21_ClrMosaic_global_232m` | Viking MDIM 2.1 colour (jpg) | 7 | global |

Catalogued but NOT served as tiles (404): Jezero HiRISE and CTX DTMs, CTX beta01 Caltech mosaic, HiRISE_Global, TES thermal inertia, TES dust, MOLA roughness, CRISM hydrous mineral detections, CRISM `frt_*_mtr3` cubes, SIM3292 global geology. These need the USGS GeoTIFFs and a tiling step.

## 3. Perseverance traverse (verified)

- Source: `https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_traverse.json`. GeoJSON FeatureCollection, one LineString per drive, properties sol, fromRMC, toRMC, length, SCLK; coordinates [lon, lat, elev].
- No CORS header, so the file is served from this repo (`m20_traverse.json`, thinned to 3 m by `data/build_traverse.py`; raw copy in `data/m20_traverse_raw_nasa.json`).
- Haversine on R = 3,396,190 m (the radius NASA MMGIS uses) reproduces NASA's per-drive lengths exactly: 46.05 km total.
- Some vertices carry elevation near 0, which is a bad value at Jezero (floor is about -2,600 m). Those are kept as null and excluded from slope.

## 4. Ground truth check

The "Load Perseverance sols 1170 to 1200" button loads the real drive to Bright Angel as a route. NASA lists 798 m for those sols. The planner recomputes the distance independently from the thinned points and lands within 2 percent (785 m vs 798 m; the gap is the 3 m thinning). Screenshot: `screenshots/ground-truth.png`.

## 5. Safety rules and their sources

| Rule | Value in app | Source |
|---|---|---|
| Walk-back limit | 30 min at 3.5 km/h = 1.8 km radius | NASA JSC, ICES 2026 Mars suit mass presentation, https://ntrs.nasa.gov/api/citations/20260005410/downloads/Mars_Mass_ICES2026_Presentation_Final.pdf |
| Radiation dose | 0.21 mGy/day surface GCR (0.67 mSv/day equivalent) | Hassler et al. 2014, Science, https://doi.org/10.1126/science.1244797 |
| Daylight window | 07:00 to 17:00 LMST | Working assumption from the diurnal temperature swing; MEDA data to refine |
| Slope limit | 15 deg, adjustable, labelled DRAFT | No published Mars suit figure found |
| Subsurface ice | None at Jezero | SWIM 2.0, https://swim.psi.edu |

## 6. Science targets (anchored to rover position at that sol)

| Target | Sol | Lat, Lon | Note |
|---|---|---|---|
| Octavia E. Butler landing site | 14 | 18.444627, 77.450886 | Máaz formation basalts |
| Séítah | 200 | 18.432548, 77.440687 | Olivine-rich layered rocks, first cores |
| Delta front, Hawksbill Gap | 420 | 18.449825, 77.401363 | Delta sandstone and mudstone, clays and carbonates from CRISM |
| Three Forks sample depot | 693 | 18.454176, 77.408448 | Ten sealed sample tubes |
| Bright Angel | 1182 | 18.497182, 77.305358 | Cheyava Falls leopard-spot core, July 2024 |
| Crater rim, Witch Hazel Hill | 1400 | 18.460553, 77.264745 | Oldest rocks, 700 m above floor |
| Rover now | 2022 | 18.435594, 77.233223 | End of traverse file |

Raw images per sol: `https://mars.nasa.gov/mars2020/multimedia/raw-images/?begin_sol=N&end_sol=N`.

## 7. Hardware (carry-out half of the challenge)

Existing ESP32-S3 safety tag from a previous project: MPU-6500 fall detection, MAX30102 heart rate and SpO2, DHT11, NEO-6M GPS, E32-900T20D LoRa 868 MHz, plus base and repeater boards with Wi-Fi FTM ranging. Minimum demo is tag + base (two ESP32-S3); a third board as FTM anchor gives indoor position. Not wired into the web app yet; the crew panel is labelled SIMULATED and vitals read "awaiting tag". The tag is the first thing to cut if time runs short.

## 8. Team split (from Slack, 6 Nov)

- Mariam: picked Jezero; rover research share.
- Helena: make the map interactive; Notion page with the four "what we know" asides (habitability, water ice and ISRU, subsurface ice hazards, temperature monitoring).
- Chris: map base, route engine and safety rules, wearable tag, Perseverance research.
- Every rover failure found in research becomes a rule or hazard layer in the planner.

## 9. Not done yet

- 1 m HiRISE Jezero DTM (GeoTIFF, several GB); the 20 m CTX DTM is in (section 11).
- CRISM mineral layers (same).
- MEDA temperature series for the daylight window.
- Real ESP32 tag feed into the crew panel.

## 10. Auto-router (added 10 Nov)

- 30 m grid over the HiRISE mosaic bbox (677 x 717 cells). Cost per cell = 1 + 2.5 x sand, where sand is the THEMIS night-IR brightness scaled between the grid's 15th percentile (56, sandy) and 65th percentile (121, rock); cells within 60 m of the Perseverance track cost x0.6 (proven ground). "Recommended" adds +1.0 off proven ground and refuses steps steeper than the slope limit where both cells have rover elevation.
- Check against the rover: Seitah (which Perseverance detoured around for sand) reads 85 in night IR; Bright Angel 164; crater rim 182; Neretva Vallis shows as a dark sand-filled channel. Habitat-to-delta-front: shortest route 24 percent sandy, terrain-aware 5 percent, recommended stays 43 percent on proven ground.
- Night-IR tiles are read as pixels in the browser (CORS allowed on trek.nasa.gov): z9 rows 202-203, cols 731-732, 81 m per pixel at Jezero.
- Spoken warnings use the browser speech API; track back replans from the live simulated position on the recommended cost.
- Reference for thermal inertia as a sand proxy: Christensen et al. 2004, THEMIS on Mars Odyssey.

## 11. CTX stereo DTM for slope everywhere (added 11 Nov)

- Source: USGS Mars 2020 TRN product `JEZ_ctx_B_soc_008_DTM_MOLAtopography_DeltaGeoid_20m_Eqc_latTs0_lon0.tif` (https://planetarymaps.usgs.gov/mosaic/mars2020_trn/CTX/), 9.7 MB GeoTIFF, 1512 x 1596 px, equirectangular on the Mars 2000 sphere (R = 3,396,190 m), 20 m per pixel, elevations -2,711 to -1,516 m, no nodata inside the file.
- `data/build_dtm.py` samples it bilinearly at the centres of the planner's 30 m cells and writes `data/jez_dtm_30m.i16` (677 x 717 Int16 decimetres, 971 KB) plus `data/jez_dtm_30m.json` (metadata and the check below). The page loads the binary next to the THEMIS tiles.
- Check against Perseverance: at the 11,044 traverse vertices that carry an elevation, DTM minus rover is -0.40 m mean, -0.27 m median, 3.1 m standard deviation, 95 percent within 6.1 m. The page repeats the check per grid cell at load time and prints it under Route comparison.
- Effect: slope is now known on every cell, so the "Recommended" router refuses steps over the slope limit everywhere, not only within 60 m of the track. Map clicks route over the terrain by default (untick "Route clicks over terrain" for straight lines). Every leg is walked in 30 m steps; the leg's slope is its steepest step, and the climb, drop and elevation profile come from the same samples.
- Test: habitat at the landing site, click 4.2 km north-west across the 15 m deep crater at 18.4727 N, 77.4281 E. Straight line: max step 22.5 deg, flagged as a slope breach. Routed: 5.59 km, no step over 15 deg. Bright Angel comparison now reports slope known on 100 percent of all three routes.
- Chris found two ways to still get a straight leg through a crater: editing a waypoint after routing (drag, right-click remove, Remove last) and the return leg, which was always drawn straight to the habitat. Fix: the planner keeps the astronaut's chosen points as anchors and rebuilds every leg, including the return, from the anchors on any edit, slider change or habitat move. Routing uses the hard slope limit first; if a chosen point cannot be reached under the limit at all, it takes the least steep approach, says so, and the leg is flagged. A flood fill of the 30 m grid under the 15 degree rule found no cell within 3 km of the landing site that is unreachable, so that fallback is rare. Straight legs now exist only with "Route clicks over terrain" unticked.
- Also fixed: the landing-site target marker sat on top of the habitat marker, so dragging the habitat panned the map instead.
- "Steep ground" layer (11 Nov): the steepest 30 m step out of every cell, painted from the DTM grid; red over the slope limit, amber within 5 degrees of it. It shows exactly what the router refuses. Resolution limit, stated honestly: the DTM is 20 m and the grid 30 m, so craters and scarps narrower than about 100 m, or shallower than about 8 m over 30 m, are not steep in the grid and the router walks through them. Example: Kodiak butte (18.442 N, 77.4085 E) stands 45 m above the floor with 18 to 25 degree walls in the grid and is ringed red; the 60 m craters just west of the landing site are not. The 1 m HiRISE DTM would close that gap.

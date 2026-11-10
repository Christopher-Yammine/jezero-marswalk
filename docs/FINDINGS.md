# Findings: data and references behind the Jezero Marswalk planner

HackAthlone 2026 (NASA Space Apps, 13 to 15 Nov 2026, Athlone). Challenge: Interplanetary Survival Guide, Martian Map.
Team: Chris Yammine, Mariam Hamdan, Helena Mansour. Site chosen: Jezero crater (Perseverance landing site).

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

- 1 m Jezero DTM for slope off the rover track (GeoTIFF, needs tiling).
- CRISM mineral layers (same).
- MEDA temperature series for the daylight window.
- Real ESP32 tag feed into the crew panel.

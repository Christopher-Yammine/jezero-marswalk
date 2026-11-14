# Challenge resources: full crawl (2026-11-14)

Every resource on the NASA Space Apps 2026 challenge "Interplanetary Survival Guide: Martian Map" (Resources tab), crawled with headless Chromium plus direct REST/JSON calls.
- Read-only: no logins, no forms, no bulk downloads.
- One test tile and one 7 KB thumbnail were fetched to confirm the endpoints work and allow cross-origin requests.
- Jezero reference point: 18.45N, 77.45E (landing site about 77.4509E, 18.4446N).

## Priority shortlist for the planner

1. **Trek imagery tiles**, loadable directly in Leaflet's `EPSG4326` scheme:
   - HiRISE 25 cm, zoom ≤ 17
   - CTX 6 m, zoom ≤ 13
   - Viking and MOLA global layers
2. **Elevation models** from `https://trek.nasa.gov/mars/TrekWS/rest/cat/data/stream?label=<label>`:
   - CTX 20 m, 9.7 MB (what we use now)
   - HiRISE 1 m, 1.84 GB, for routing at walking scale
   - Trek has **no Jezero slope product**, so we compute our own.
3. **Jezero geology, USGS SIM 3464 (1:75K)**, a live feature service that returns GeoJSON and allows cross-origin requests:
   - `https://services.arcgis.com/v01gqwM5QqNysAAi/arcgis/rest/services/Jezero_FeatureServiceFromPro/FeatureServer/8`: 1308 unit polygons in 14 units, including the delta (NHjf2) and **Aeb, eolian bedforms/TARs, i.e. sand: a walking hazard**.
   - `/6`: linear features (delta fronts, rim crests, channels)
   - `/4`: 341 small craters
   - `/2`: landing ellipse
4. **Rover context:**
   - `https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_waypoints.json`: 708 stops to sol 2022, 45.25 km in total. Each stop has RMC, site, drive, lat/lon, elevation, roll/pitch/yaw and Navcam panoramas.
   - Raw images join to these stops on `site` + `drive` = `RMC`.
5. **Thermal and spectral layers:** THEMIS day/night IR, TES thermal inertia, CRISM, plus MOLA roughness. Together these meet the "3+ data types" ask.
6. **Point-of-view media:** Trek's 8 Jezero points of interest (`mars2020_waypoints`) and 9 narrated Mastcam-Z 360° videos (`mastcam_z_waypoints`).
7. **UI patterns from Worldview** (Earth only): layer-picker modal, timeline, swipe/opacity/spy compare, events feed, permalink and snapshot.

## 0. Challenge page

- **Details tab:**
  - The ask: a layered map, tool or interface for an astronaut's Marswalk, built from data from several NASA missions.
  - At least three data types: optical, thermal, spectral, topographic, geophysical, atmospheric, radiation or chemical.
  - Safety first: radiation and space weather, suit mobility, and a route that avoids obstacles such as large rocks.
  - Possible formats: habitat display, tablet or helmet HUD. Static, interactive or a map generator.
  - Include point-of-view surface imagery.
  - Consider robots and astronauts working in pairs.
- **Teams tab:** 1249 teams on this challenge. Data comes from `POST api.spaceappschallenge.org/graphql`.

## 1. JPL Mars Trek (https://trek.nasa.gov/mars/)

Dojo/Esri 3.x app with a Cesium 3D globe, version 3.4.123-Mars.

### Interface
- **Search sidebar:** three tabs, Search / Layers / Downloads.
  - 2038 items; "Jezero" returns 14.
  - Facets: Mission, Instrument, Product Type.
  - Spatial search by view, point, place name or polygon.
- **Layer panel:** view or download metadata (FGDC), Download (GeoTIFF or zip), Add to Downloads, Fly To, legend.
- **Basemap:** Viking 232 m. Overlays: nomenclature and graticule.
- **Auto Layers:** CTX mosaics appear from zoom 7, HiRISE from zoom 11.
- **Projections:** 3D globe, north pole, equirectangular, south pole.
- **Tools that work without a login:**
  - Distance, via `TrekServices/ws/elevationProfile/distance`
  - Elevation profile, via `elevationProfile/calculate` and `multiDEM`
  - Sun angle, via `trek.nasa.gov/getAzElfromT1?LTD002=Mars`
  - 3D print file, via `TrekServices/ws/model/mars/trekSTL.stl` or `trekOBJ.zip`
    - parameters: `imageServiceURL`, `demServiceURL`, `bbox`, `width`, `height`, `exag`, `target`
  - VR path, Country Mover, share/embed, screen capture
- **Tools that need a login**, which run as jobs that email the result:
  - Slope: `TrekWS/rest/slope`
  - Subset: `TrekWS/rest/transform/latlon/subset/stream/tiff`
  - Crater detection: `crater/detect`
  - Rock detection: `rock/detect`
  - Lighting
- **None of the tool backends send cross-origin headers**, so a browser app needs a proxy to call them.
  - Point elevation at 77.45E, 18.45N returned −2562 m, from a global DEM, not a Jezero one.

### Catalog API
- **Search:** `https://trek.nasa.gov/mars/TrekServices/ws/index/eq/searchItems?proj=urn:ogc:def:crs:EPSG::104905&start=0&rows=2100`
  - 225 products, 18 CRISM datasets, 12 bookmarks, 1783 place names.
- **Other endpoints:**
  - `index/getLayerServices?uuid=`
  - `index/eq/searchDEM?bbox=`
  - `TrekWS/rest/cat/{data/stream,metadata/fgdc/html,abstract,legend/stream}?label=`
- **ArcGIS server:** `https://trek.nasa.gov/mars/trekarcgis/rest/services?f=json`, 76 services.
- **Slope products** exist only for Apollinaris, Coprates, Deuteronilus and East Melas.
- **HiRISE elevation models** also exist for Gale, Columbia Hills, Endeavour, Victoria, Phoenix and InSight.

### Products covering Jezero

| Product | Label | Resolution / size | Service |
|---|---|---|---|
| HiRISE mosaic, controlled | `JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first_dd` | 25 cm, 9.8 GB | Tiles, zoom 0–17 |
| HiRISE elevation model, controlled | `JEZ_hirise_soc_006_DTM_MOLAtopography_DeltaGeoid_1m_Eqc_latTs0_lon0_blend40` | 1 m, 1.84 GB | Download only |
| CTX mosaic, controlled | `JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0` | 6 m, 36 MB | Tiles, zoom 0–13 |
| CTX elevation model, controlled | `JEZ_ctx_B_soc_008_DTM_MOLAtopography_DeltaGeoid_20m_Eqc_latTs0_lon0` | 20 m, 9.7 MB | Download only |
| CTX preliminary mosaic | `Jezero_CTX_BlockAdj_dd` | 1.6 GB | Tiles, zoom 0–12 |
| NE Syrtis/Jezero/Midway visible mosaic and DEM | `NES_JEZ_MID_*` | 25 GB and 10 GB | Tiles / download |
| Perseverance traverse | `Perseverance_Traverse_Path` | Sol 14–1176 only (stale) | Map service |
| Jezero points of interest | `mars2020_waypoints` | 8 points, each with an HTML story | Map service |
| Mastcam-Z tour | `mastcam_z_waypoints` | 9 points with narrated 360° `.mp4` videos | Map service |

- **Tile URL:** `https://trek.nasa.gov/tiles/Mars/EQ/<label>/1.0.0/default/default028mm/{z}/{y}/{x}.png` (some layers use `.jpg`).
  - Zoom level z has 2^(z+1) × 2^z tiles of 256 px.
  - Cross-origin requests are allowed.
- **3D terrain:** `marshub.s3.amazonaws.com/mars_v14/layer.json` (Cesium).

## 2. USGS–NASA Planetary Geologic Mapping hub

- **Apps:** the hub page `eecdba26…` embeds Experience app `0b734570…`, which has three views:
  - Map View: footprints of every USGS Mars map.
  - List View.
  - Global Maps.
- **Map database feature service:** `PGM_Map_Database_MARS_INTERACTIVE2/FeatureServer/1`
  - 148 Mars maps: 116 published, 32 in progress.
  - Fields include DOI and links to each map's interactive version.
- **Maps covering Jezero:** SIM 3464 (1:75K), SIM 3292 (1:20M, too coarse for a walk), I-1802B, I-2461, SIM 2888, I-995, I-1083.
- **SIM 3464 downloads:**
  - Map PDF, 36.4 MB
  - Pamphlet
  - GIS database, 349 MB: `pubs.usgs.gov/sim/3464/sim3464_database.zip`
  - Viewer: `usgs.maps.arcgis.com/apps/webappviewer/index.html?id=a0ae4b521f7a4a6ca2cf0f0c551d5293`
  - Flyover video: youtube.com/watch?v=grYWH92hte4
- **SIM 3464 feature service:** use `f=geojson&outSR=4326`.
  - Layers 0–8: boundary, figures, landing ellipse, cross sections, small craters (341), contacts (2497), linear features (382), surface features (285), geologic units (1308).
  - The raster tiles use the MTM projection, so use the vector layers instead.
- **Data sources listed on the hub:**
  - PDS Imaging and Geosciences nodes, ODE, PILOT, Astropedia, Map-a-Planet
  - Lunaserv WMS
  - GeoSTAC
  - JHU-APL CRISM map
  - Caltech global CTX mosaic

## 3. Curiosity proposed path (PIA23179)

- Annotated map: `assets.science.nasa.gov/dynamicimage/assets/science/psd/photojournal/pia/pia23/pia23179/figures/PIA23179_fig1.jpg`
- Other downloads: JPG, TIFF (13 MB), GIF (2.9 MB).
- Useful as a design pattern only: a route line over HiRISE with labelled science regions.
- The "flyover video" the challenge mentions isn't linked anywhere we could find.

## 4. NASA Worldview (Earth only)

- 1346 layers, mostly WMTS tiles via GIBS.
- Features: Natural Events from EONET, data download, comparison modes (swipe, opacity, spy), time-series charts, timeline animation, snapshot, about 25 guided tours.
- Use it for UI ideas only.

## 5. Perseverance raw images

- **API:** `https://mars.nasa.gov/rss/api/?feed=raw_images&category=mars2020&feedtype=json&ver=1.2&num=100&page=N&order=sol+desc`
  - Works without a login and allows cross-origin requests.
  - Camera: `&search=%7CNAVCAM_LEFT`
  - Sol range: `&condition_2=100:sol:gte`
  - Frame type: `&extended=sample_type::full,`
  - Latest: `&latest=true`
  - One image: `&id=<imageid>`
- **Size:** 1,055,868 images in total, including thumbnails; latest sol 2031.
- **Cameras:**
  - Engineering: NAVCAM L/R, FRONT_HAZCAM L/R A/B, REAR_HAZCAM L/R, CACHECAM
  - Science: MCZ L/R, SKYCAM, PIXL_MCC, SHERLOC_WATSON, SHERLOC_ACI, SUPERCAM_RMI
  - Entry, descent and landing: the EDL cameras and LCAM
  - Ingenuity helicopter: HELI_NAV, HELI_RTE
- **Files:** `.../sol/<sol5>/ids/edr/browse/<cam>/<ID>_{320,800,1200}.jpg` plus a full-resolution `.png`.
- **The gallery page itself returns a 404 to a headless browser**, so the API is the way in.

## Not accessed or not verified

- Trek tools that need a login.
- Trek's Layers and Downloads tabs in headless mode.
- The raw-images gallery interface.
- The USGS Experience Builder cards.
- Worldview's dropdowns.
- The Curiosity flyover video.
- Large files: listed with their catalog sizes, not downloaded.

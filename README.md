# Jezero Marswalk Planner

HackAthlone 2026 (NASA Space Apps), challenge "Interplanetary Survival Guide: Martian Map".
An astronaut's crew tablet for planning and carrying out a Marswalk in Jezero crater.

Live: https://jezero-marswalk-ashy.vercel.app

## What it does

- Streams NASA Mars Trek tiles live: HiRISE 25 cm and CTX 6 m Jezero mosaics, THEMIS day/night thermal, MOLA+HRSC relief, Viking global.
- Draws Perseverance's full traverse (559 drives, 46.05 km, elevation at every point) coloured by sol.
- Lets the astronaut click waypoints, drag the habitat, and get out/return distance, round trip time, farthest point from base, return time, radiation dose, climb/drop, per-leg slope and an elevation profile.
- Enforces safety rules from NASA sources: 30 min walk-back (1.8 km at 3.5 km/h), slope limit (draft), daylight window, running dose.
- Ground truth: loads Perseverance sols 1170 to 1200 and compares the planner's distance with NASA odometry (within 2 percent).
- Crew tag panel, labelled SIMULATED, ready for the ESP32 LoRa suit tag feed.

## Repo layout

- `index.html` - the whole app (Leaflet 1.9.4, custom Mars CRS, no build step)
- `m20_traverse.json` - NASA traverse thinned to 3 m, served with the page
- `data/m20_traverse_raw_nasa.json` - untouched NASA source file
- `data/build_traverse.py` - regenerates `m20_traverse.json` from the raw file
- `docs/FINDINGS.md` - every dataset, layer id, reference and decision, with what was verified
- `docs/brief.html` - the team brief
- `docs/slack-team-plan.txt` - the plan as posted to the team
- `docs/screenshots/` - desktop, mobile and ground-truth captures

## Run locally

    python -m http.server 8787

then open http://localhost:8787/. Deploys to Vercel production on every push to `main`.

## Sources

NASA Mars Trek (https://trek.nasa.gov/mars/), Mars 2020 traverse JSON (https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_traverse.json), NASA JSC ICES 2026 Mars suit paper (walk-back), Hassler et al. 2014 Science (radiation), SWIM 2.0 (subsurface ice). Full list in `docs/FINDINGS.md`.

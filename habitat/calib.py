"""Read the tag's raw Wi-Fi distances to one unit for ~35 s. Usage: calib.py B1 [true_m]"""
import json, sys, time, urllib.request, statistics
unit=sys.argv[1]; true=float(sys.argv[2]) if len(sys.argv)>2 else 1.0
seen=[]; last=None; t0=time.time()
while time.time()-t0<(float(sys.argv[3]) if len(sys.argv)>3 else 35):
    d=json.load(urllib.request.urlopen('http://127.0.0.1:8770/state'))
    t=next((x for x in d['tags'].values() if x.get('ftm_hist')),None)
    if t:
        for ts,v in t['ftm_hist'].get(unit,[]):
            if ts>t0-3 and (ts,v) not in seen: seen.append((ts,v))
        last=t.get('last_seen','')[11:19]
    time.sleep(2)
vals=[v for _,v in seen]
print(f'{unit}: {len(vals)} readings {vals} | tag last heard {last}')
if vals:
    med=statistics.median(vals); print(f'median {med:.2f} m at true {true} m -> offset {med-true:+.2f} m, spread {max(vals)-min(vals):.2f} m')

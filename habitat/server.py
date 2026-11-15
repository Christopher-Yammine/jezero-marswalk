"""Habitat server: the bridge between the LEB-10 suit tag hardware and the Marswalk views.

    tag (ESP32-S3 + E32) --LoRa--> [relay R1] --LoRa--> base (E32, USB) --JSON lines--> this server
                                                                                      |
                     command view (/command)  <------ live stream (SSE) ---------------+
                     astronaut view (/crew)   <------ live stream (SSE) ---------------+
                     command buttons  ------- POST /cmd -------> "PING LEB10-T01\n" -> base -> LoRa -> tag

The base firmware (bench/base_bridge) already expands the radio format into one JSON object per
line at 9600 baud, so this server never touches the radio protocol. Line shapes it understands,
taken from real bench output:
  tele/event  {"tag":"LEB10-5vvu","seq":1236,"type":"tele","state":"OK","event":null,"temp_c":24.1,
               "hum_pct":31,"still_s":174,"md":false,"hr":null,"spo2":null,"lat":null,"lon":null,"sats":0,
               "sensors":{"motion":true,"gps":true,"heart":true,"temp":true,"contact":false},
               "via":"direct","site":"W1","proto":4}
  obs         {"tag":"LEB10-5vvu","seq":2,"type":"obs","ftm":{"B1":480},"ble":{},"via":"direct","site":"W1"}
              (ftm distances in cm to fixed units, measured on the tag)
  base        {"tag":"BASE","type":"tele",...,"rx_lines":32,"rx_bad":2,"rx_dup":21,"acks":47,"radio":true}

Usage:
  .venv/bin/python server.py --sim                 # simulated tags, same line format
  .venv/bin/python server.py --port /dev/cu.usbmodem1101
  .venv/bin/python server.py --replay logs/x.jsonl # replay a recorded session
Open http://localhost:8770/command and http://<this-laptop-ip>:8770/crew?tag=LEB10-T01
"""
import argparse, json, math, os, queue, random, re, subprocess, threading, time, uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
ALLOWED = {"ACK", "PING", "LOCATE", "EVAC", "STANDDOWN", "MD"}   # same set as the bench console
R_MARS = 3396190.0

cfg = json.loads((HERE / "units.json").read_text())
lock = threading.Lock()
state = {"tags": {}, "base": None, "events": [], "units": {}, "mode": None, "started": None}
subscribers = []          # one queue per connected browser
writer = None             # function(str) that sends a line to the base (or the simulator)
logf = None


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def publish(msg):
    data = json.dumps(msg)
    for q in list(subscribers):
        try:
            q.put_nowait(data)
        except queue.Full:
            pass


# ------------------------------------------------------------------ positions
EARTH_FILE = HERE / "earth_origin.json"
EARTH = json.loads(EARTH_FILE.read_text()) if EARTH_FILE.exists() else None   # {"lat","lon","acc","ts"}: where the base really is
FRAME = {"name": "earth" if EARTH else "mars"}


def bench_to_mars(x, y):
    """Bench metres (east, north from the base) -> map lat/lon.
    Earth analog site: real location of the base, true 1:1 scale.
    Mars: Jezero habitat, bench metres multiplied by cfg scale (a placement, not a measurement)."""
    if FRAME["name"] == "earth" and EARTH:
        lat = EARTH["lat"] + math.degrees(y / 6371000.0)
        lon = EARTH["lon"] + math.degrees(x / (6371000.0 * math.cos(math.radians(EARTH["lat"]))))
        return lat, lon
    s, h = cfg["scale"], cfg["habitat"]
    lat = h["lat"] + math.degrees(y * s / R_MARS)
    lon = h["lon"] + math.degrees(x * s / (R_MARS * math.cos(math.radians(h["lat"]))))
    return lat, lon


def gps_to_mars(lat, lon):
    """Earth GPS fix -> offset from the first fix (or gps_origin) -> same offset from the habitat."""
    if FRAME["name"] == "earth":
        return lat, lon                      # on the Earth analog site a GPS fix is simply where the tag is
    o = cfg.get("gps_origin")
    if not o:
        o = cfg["gps_origin"] = {"lat": lat, "lon": lon}
    dy = math.radians(lat - o["lat"]) * 6371000.0
    dx = math.radians(lon - o["lon"]) * 6371000.0 * math.cos(math.radians(o["lat"]))
    return bench_to_mars(dx / cfg["scale"], dy / cfg["scale"])   # true metres, not scaled again


def trilaterate(dists, prev=None):
    """dists: {unit: metres}. Position on the bench plane: least squares from >= 3 fixed units; from 2 units the
    circle crossing nearest the previous position (first time: the side away from the origin)."""
    # subtract each unit's calibrated ranging offset (ESP32 FTM reads long by a fixed amount per chip)
    pts = [(cfg["units"][k]["x"], cfg["units"][k]["y"], max(0.2, d - cfg["units"][k].get("ftm_offset_m", 0.0)))
           for k, d in dists.items() if k in cfg["units"] and cfg["units"][k].get("role") != "buddy"]
    if len(pts) == 1:                                    # one unit: distance only, along the last known direction
        (xa, ya, ra) = pts[0]
        dx, dy = ((prev[0] - xa), (prev[1] - ya)) if prev else (1.0, 0.0)
        n = math.hypot(dx, dy) or 1.0
        if n < 0.3: dx, dy, n = 1.0, 0.0, 1.0
        return xa + ra * dx / n, ya + ra * dy / n, 0.0
    if len(pts) == 2:
        (xa, ya, ra), (xb, yb, rb) = pts
        D = math.hypot(xb - xa, yb - ya)
        if D < 0.5:
            return None
        a = (ra * ra - rb * rb + D * D) / (2 * D)
        h = math.sqrt(max(0.0, ra * ra - a * a))         # circles that do not meet: take the closest point on the line
        mx, my = xa + a * (xb - xa) / D, ya + a * (yb - ya) / D
        cands = [(mx + h * (yb - ya) / D, my - h * (xb - xa) / D), (mx - h * (yb - ya) / D, my + h * (xb - xa) / D)]
        ref = prev or (max(c[0] for c in cands), max(c[1] for c in cands))
        x, y = min(cands, key=lambda c: math.hypot(c[0] - ref[0], c[1] - ref[1]))
        return x, y, abs(ra + rb - D) / 2 if h == 0 else 0.0
    if len(pts) < 3:
        return None
    (x0, y0, d0) = pts[0]
    a11 = a12 = a22 = b1 = b2 = 0.0
    for (xi, yi, di) in pts[1:]:                 # linearise against the first unit
        ax, ay = 2 * (xi - x0), 2 * (yi - y0)
        b = d0 * d0 - di * di + xi * xi - x0 * x0 + yi * yi - y0 * y0
        a11 += ax * ax; a12 += ax * ay; a22 += ay * ay; b1 += ax * b; b2 += ay * b
    det = a11 * a22 - a12 * a12
    if abs(det) < 1e-6:
        return None
    x = (a22 * b1 - a12 * b2) / det
    y = (a11 * b2 - a12 * b1) / det
    resid = sum(abs(math.hypot(x - xi, y - yi) - di) for (xi, yi, di) in pts) / len(pts)
    return x, y, resid


# ------------------------------------------------------------------ line handling
def handle_line(raw):
    raw = raw.strip()
    if not raw.startswith("{"):
        return
    try:
        m = json.loads(raw)
    except json.JSONDecodeError:
        return
    ts = now_iso()
    if isinstance(m.get("sensors"), int):      # newer tag firmware sends a bitmask (tag_bench.ino sensorBits)
        b = m["sensors"]
        m["sensors"] = {"motion": bool(b & 1), "gps": bool(b & 2), "heart": bool(b & 4), "temp": bool(b & 8), "contact": bool(b & 16)}
    if logf:
        logf.write(json.dumps({"ts": ts, "line": m}) + "\n"); logf.flush()
    tag = m.get("tag") or m.get("anchor")
    # repeaters (LEB10-R1) and beacons (LEB10-A1) report in the same format as tags, but they are fixed
    # units, not people: keep them out of the crew list and remember their latest report instead
    if isinstance(tag, str) and re.match(r"^LEB10-[RA]\d$", tag):
        with lock:
            state["units"][tag.replace("LEB10-", "")] = {**m, "last_seen": ts}
        publish({"kind": "unit", "unit": {**m, "last_seen": ts}})
        return
    with lock:
        if tag == "BASE" or "anchor" in m:
            if tag == "BASE":
                state["base"] = {**(state["base"] or {}), **m, "last_seen": ts}
                msg = {"kind": "base", "base": state["base"]}
                if m.get("type") == "event":
                    ev = {"ts": ts, "tag": "BASE", "event": m.get("event"), "state": m.get("state")}
                    state["events"].append(ev); del state["events"][:-300]
                    publish({"kind": "event", "event": ev})
            else:
                msg = {"kind": "unit", "unit": m}
            publish(msg)
            return
        t = state["tags"].setdefault(tag, {"tag": tag, "first_seen": ts, "rx": 0, "lost": 0,
                                            "last_seq": None, "trail": [], "ftm": {}, "ble": {}})
        seq = m.get("seq")
        t["radio"] = "via" in m                      # lines relayed by the base carry "via"; a tag on USB does not
        if isinstance(seq, int) and t["radio"]:      # packet loss from sequence gaps (E32 has no RSSI); meaningless over USB
            if t["last_seq"] is not None and seq > t["last_seq"] + 1 and seq - t["last_seq"] < 500:
                t["lost"] += seq - t["last_seq"] - 1
            if t["last_seq"] is None or seq > t["last_seq"] or t["last_seq"] - seq > 500:
                t["last_seq"] = seq
        t["rx"] += 1
        t["last_seen"] = ts
        t["via"] = m.get("via", t.get("via"))
        if m.get("type") == "obs":
            # the tag sends only its freshest reading(s) per report, so keep a short history per unit and use
            # the median of the last few minutes: three units with recent readings give a position
            now_s = time.time(); hist = t.setdefault("ftm_hist", {})
            for k, v in (m.get("ftm") or {}).items():
                if isinstance(v, (int, float)) and v > 15:      # 0 cm is a known false reading from the responders
                    hist.setdefault(k, []).append((now_s, v / 100.0)); hist[k] = hist[k][-3:]
            fresh = {}
            for k, rs in hist.items():
                vals = sorted(d for (tt, d) in rs if now_s - tt < 25)
                if vals:
                    fresh[k] = round(vals[len(vals) // 2], 2)
            t["ftm"] = fresh
            buddy_check(tag, t, fresh, now_s)
            t["ble"] = m.get("ble") or {}
            t["ftm_at"] = ts
        else:
            for k, v in m.items():
                if k not in ("ftm", "ble"):
                    t[k] = v
            if m.get("type") == "tele":
                t["tele_at"] = time.time()
        # position: Earth GPS fix mapped to Jezero, else Wi-Fi distances to the fixed units
        pos = None
        if isinstance(m.get("lat"), (int, float)) and isinstance(m.get("lon"), (int, float)) and (m.get("sats") or 0) >= 4:
            la, lo = gps_to_mars(m["lat"], m["lon"]); pos = {"lat": la, "lon": lo, "src": "gps", "err_m": None}
        elif m.get("type") == "obs":
            fixed = {k: v for k, v in t["ftm"].items() if cfg["units"].get(k, {}).get("role") != "buddy"}
            r = trilaterate(fixed, t.get("bench_s")) if len(fixed) >= 1 else None
            # Hold still: the tag's motion sensor says whether the wearer is moving. While it reports stillness
            # the dot stays put, because indoor ranging wobbles by metres even when nothing moves. Telemetry
            # arrives every 45 s, so a clear jump in the distances (> 4 m on any unit) releases the hold early.
            still_now = (t.get("still_s") or 0) + (time.time() - t.get("tele_at", time.time()))
            if r and t.get("pos") and t.get("still_s") is not None and still_now >= 15:
                ref = t.setdefault("hold_ref", dict(fixed))
                if all(abs(fixed.get(k, v) - v) <= 4.0 for k, v in ref.items()):
                    r = None
                else:
                    t["still_s"] = 0; t["tele_at"] = time.time()      # treat as moving until the next telemetry
            if r:
                t.pop("hold_ref", None)
                # smooth: indoor ranging jumps by metres between rounds, so follow it at 35 % per report
                px, py = t.get("bench_s") or (r[0], r[1])
                sx, sy = px + 0.35 * (r[0] - px), py + 0.35 * (r[1] - py)
                t["bench_s"] = (sx, sy)
                la, lo = bench_to_mars(sx, sy)
                pos = {"lat": la, "lon": lo, "src": "ftm", "err_m": None, "units": len(fixed),
                       "bench": [round(sx, 2), round(sy, 2)]}
        if pos:
            t["pos"] = {**pos, "ts": ts}
            last = t["trail"][-1] if t["trail"] else None
            step = math.hypot((pos["lat"] - last[0]) * 59274, (pos["lon"] - last[1]) * 56200) if last else 99
            if step > (1.0 if FRAME["name"] == "earth" else 1.0 * cfg["scale"] / 4):   # skip sub-metre jitter in the trail
                t["trail"].append([round(pos["lat"], 7), round(pos["lon"], 7)]); del t["trail"][:-400]
        if m.get("event") == "HAZARD" and state["mode"] == "live":
            threading.Thread(target=hazard_photo, args=(tag,), daemon=True).start()
        if m.get("event") == "SEARCH_ON": t["searching"] = True
        if m.get("event") == "SEARCH_OFF": t["searching"] = False
        ev = None
        if m.get("type") == "event":
            ev = {"ts": ts, "tag": tag, "event": m.get("event"), "state": m.get("state"), "seq": seq}
            state["events"].append(ev); del state["events"][:-300]
        publish({"kind": "tag", "tag": t, "event": ev})


def buddy_check(tag, t, fresh, now_s):
    """Buddy separation: the second walker carries a beacon; the tag ranges it directly.
    Alarm after two readings over the limit, or when the beacon has not been heard for 30 s."""
    for k, u in cfg["units"].items():
        if u.get("role") != "buddy":
            continue
        b = t.setdefault("buddy", {"unit": k, "limit_m": u.get("limit_m", 10), "state": "unknown", "over": 0,
                                   "calibrated": u.get("calibrated", False)})
        new = b["state"]
        if k in fresh:
            b["dist_m"] = round(max(0.0, fresh[k] - u.get("ftm_offset_m", 0.0)), 1); b["heard"] = now_s; b["ts"] = now_iso()
            b["over"] = b["over"] + 1 if b["dist_m"] > b["limit_m"] else 0
            new = "separated" if b["over"] >= 2 else "together" if b["over"] == 0 else b["state"]
        elif b.get("heard") and now_s - b["heard"] > 30:
            new = "lost"; b["dist_m"] = None
        if new != b["state"]:
            was, b["state"] = b["state"], new
            name = {"separated": "BUDDY_SEPARATED", "lost": "BUDDY_OUT_OF_RANGE", "together": "BUDDY_TOGETHER"}.get(new)
            if name and not (new == "together" and was == "unknown"):
                ev = {"ts": now_iso(), "tag": tag, "event": name, "state": None, "dist_m": b.get("dist_m")}
                state["events"].append(ev); del state["events"][:-300]
                publish({"kind": "event", "event": ev})
                if new in ("separated", "lost") and writer:
                    try: writer(f"LOCATE {tag}")          # buzz the tag so the walker looks up
                    except Exception: pass


def send_cmd(word, tag, arg=None):
    word = (word or "").upper().strip()
    if not tag or not tag.startswith("LEB10-") or " " in tag:
        return False, "command not allowed"
    if word == "SEARCH":                         # "SEARCH A1 LEB10-5vvu": tag homes in on a unit by Bluetooth; "OFF" stops
        arg = str(arg or "").strip()
        if arg != "OFF" and arg not in cfg["units"]:
            return False, "search target must be a known unit or OFF"
        line = f"SEARCH {arg} {tag}"
    elif word in ALLOWED:
        line = f"{word} {tag}"
    else:
        return False, "command not allowed"
    ev = {"ts": now_iso(), "tag": tag, "event": "CMD_" + word, "state": None, "dir": "tx"}
    with lock:
        state["events"].append(ev); del state["events"][:-300]
    publish({"kind": "event", "event": ev})
    if logf:
        logf.write(json.dumps({"ts": ev["ts"], "tx": line}) + "\n"); logf.flush()
    writer(line)
    return True, line


# ------------------------------------------------------------------ detection (uploaded photos)
DETECTOR_PY = None          # python with torch + transformers; set in main()
_det = {"proc": None, "lock": threading.Lock(), "model": None}
UPLOADS = HERE / "logs" / "uploads"


def detector():
    """Start the detection worker once and keep it warm (the model takes ~20 s to load)."""
    p = _det["proc"]
    if p and p.poll() is None:
        return p
    if not DETECTOR_PY or not Path(DETECTOR_PY).exists():
        raise RuntimeError("no detector python configured (--detector-python)")
    p = subprocess.Popen([DETECTOR_PY, "-I", str(HERE / "detect_worker.py")], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
    first = json.loads(p.stdout.readline() or "{}")
    if not first.get("ready"):
        raise RuntimeError("detector failed to start")
    _det.update(proc=p, model=first.get("model"))
    return p


def detect(img_bytes, ext):
    UPLOADS.mkdir(parents=True, exist_ok=True)
    name = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6] + ext
    path = UPLOADS / name
    path.write_bytes(img_bytes)
    with _det["lock"]:                       # one image at a time; the CPU is the bottleneck
        p = detector()
        p.stdin.write(json.dumps({"path": str(path)}) + "\n"); p.stdin.flush()
        res = json.loads(p.stdout.readline() or '{"ok":false,"error":"detector died"}')
    res["upload"] = name
    return res


def set_frame(name, origin=None):
    """Switch between the Earth analog site and Jezero. Positions and trails restart in the new frame."""
    global EARTH
    if origin:
        EARTH = {"lat": float(origin["lat"]), "lon": float(origin["lon"]), "acc": origin.get("acc"), "ts": now_iso()}
        EARTH_FILE.write_text(json.dumps(EARTH))
    if name == "earth" and not EARTH:
        return False
    FRAME["name"] = name
    with lock:
        for t in state["tags"].values():
            t.pop("pos", None); t["trail"] = []
        state["events"] = [e for e in state["events"] if not e.get("pos")]
    publish({"kind": "reload"})
    return True


def drop_pin(body):
    """A walker's phone reports its own location (browser geolocation). Earth analog site only."""
    ev = {"ts": now_iso(), "tag": str(body.get("tag") or "PHONE")[:24], "event": "DROP_PIN", "state": None,
          "note": str(body.get("note", ""))[:80],
          "pos": {"lat": float(body["lat"]), "lon": float(body["lon"]), "src": "phone", "acc_m": body.get("acc")}}
    with lock:
        state["events"].append(ev); del state["events"][:-300]
    if logf:
        logf.write(json.dumps({"ts": ev["ts"], "pin": ev}) + "\n"); logf.flush()
    publish({"kind": "event", "event": ev})
    return ev


HAZARD_SCENARIOS = ("sand", "boulders", "ledge", "sharp_rocks")
_last_photo = {}


def hazard_photo(tag):
    """The tag has no camera. When its hazard button is pressed, stand in a real Perseverance hazard photo
    (picked at random from the sample library), analyse it and post it as that walker's hazard report."""
    now_s = time.time()
    if now_s - _last_photo.get(tag, 0) < 4:      # the tag repeats events until acknowledged
        return
    _last_photo[tag] = now_s
    try:
        samples = [x for x in json.loads((HERE / "web" / "samples" / "samples.json").read_text()) if x["scenario"] in HAZARD_SCENARIOS]
        smp = random.choice(samples)
        data = (HERE / "web" / "samples" / smp["file"]).read_bytes()
        try:
            res = detect(data, ".jpg")
        except Exception as e:                   # detector not available: still post the photo
            UPLOADS.mkdir(parents=True, exist_ok=True)
            name = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6] + ".jpg"
            (UPLOADS / name).write_bytes(data)
            res = {"ok": False, "error": str(e), "upload": name, "detections": []}
        haz = json.loads((HERE / "web" / "hazards.json").read_text())
        top = next((d for d in res.get("detections", []) if haz.get(d["class"], {}).get("level") in ("high", "medium")), None)
        cls = top["class"] if top else smp["scenario"]
        ev = report({"tag": tag, "class": cls, "label": haz.get(cls, {}).get("name", smp["label"]),
                     "score": top["score"] if top else None, "upload": res["upload"],
                     "sample": {"label": smp["label"], "sol": smp.get("sol"), "source": smp.get("source"), "credit": smp.get("credit")}})
        publish({"kind": "photo", "tag": tag, "upload": res["upload"], "sample": smp, "result": res, "event": None, "report_ts": ev["ts"]})
    except Exception as e:
        print("[hazard_photo]", e, flush=True)


def report(body):
    """An astronaut reports a detected hazard: becomes an event and a pin at their last position."""
    tag = body.get("tag")
    with lock:
        t = state["tags"].get(tag) or {}
        pos = t.get("pos")
    ev = {"ts": now_iso(), "tag": tag or "UI", "event": "HAZARD_REPORT", "state": None,
          "hazard": str(body.get("class", ""))[:32], "label": str(body.get("label", ""))[:64],
          "score": body.get("score"), "upload": str(body.get("upload", ""))[:64], "sample": body.get("sample"),
          "pos": {"lat": pos["lat"], "lon": pos["lon"], "src": pos["src"]} if pos else None}
    with lock:
        state["events"].append(ev); del state["events"][:-300]
    if logf:
        logf.write(json.dumps({"ts": ev["ts"], "report": ev}) + "\n"); logf.flush()
    publish({"kind": "event", "event": ev})
    return ev


# ------------------------------------------------------------------ inputs
def run_serial(port):
    """Read the base over USB. If the cable is nudged or the board resets, keep retrying the same port
    so the views come back on their own; the command view's log shows when the link dropped and returned."""
    import serial
    global writer
    holder = {"ser": None}
    def write(line):
        if holder["ser"]:
            holder["ser"].write((line + "\n").encode())
    writer = write
    first = True
    while True:
        try:
            # open without toggling DTR/RTS: on ESP32-S3 USB that toggle can reset the board into download mode
            ser = serial.Serial(); ser.port = port; ser.baudrate = 9600; ser.timeout = 1
            ser.dtr = False; ser.rts = False
            ser.open()
            holder["ser"] = ser
            if not first:
                link_event("BASE_USB_RECONNECTED")
            first = False
            buf = b""
            while True:
                chunk = ser.read(256)
                if not chunk:
                    continue
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    handle_line(line.decode("utf-8", "replace"))
        except Exception as e:                       # serial.SerialException, OSError when the port vanishes
            if holder["ser"] is not None:
                link_event("BASE_USB_LOST")
                try:
                    holder["ser"].close()
                except Exception:
                    pass
            holder["ser"] = None
            print(f"[serial] {port}: {e}; retrying in 2 s", flush=True)
            time.sleep(2)


def link_event(name):
    ev = {"ts": now_iso(), "tag": "BASE", "event": name, "state": None}
    with lock:
        state["events"].append(ev); del state["events"][:-300]
    publish({"kind": "event", "event": ev})


def run_replay(path, speed):
    global writer
    writer = lambda line: print("[replay] would send:", line)
    rows = [json.loads(l) for l in open(path) if l.strip()]
    prev = None
    for r in rows:
        if "line" not in r:
            continue
        t = datetime.fromisoformat(r["ts"]).timestamp()
        if prev is not None:
            time.sleep(max(0, min(5, (t - prev) / speed)))
        prev = t
        handle_line(json.dumps(r["line"]))


class Sim:
    """Simulated fleet speaking the base's exact JSON line format. Everything it says is SIMULATED."""
    def __init__(self):
        self.tags = {
            "LEB10-T01": {"seq": 0, "phase": 0.0, "r": 7.0, "state": "OK", "still": 0, "speed": 0.05},
            "LEB10-T02": {"seq": 0, "phase": 2.5, "r": 4.5, "state": "OK", "still": 0, "speed": 0.07},
        }
        self.inbox = queue.Queue()

    def write(self, line):
        self.inbox.put(line)

    def emit(self, d):
        handle_line(json.dumps(d))

    def line(self, tag, s, typ, event=None):
        s["seq"] += 1
        return {"tag": tag, "seq": s["seq"], "ms": None, "type": typ, "state": s["state"], "event": event,
                "temp_c": round(21 + random.uniform(-0.4, 0.4), 1), "hum_pct": 38, "still_s": s["still"],
                "md": s["state"] in ("MANDOWN", "PREALARM"), "dht_err": 0,
                "hr": None, "spo2": None, "lat": None, "lon": None, "sats": 0,
                "sensors": {"motion": True, "gps": False, "heart": False, "temp": True, "contact": False},
                "via": "R1" if s["r"] > 6 else "direct", "site": "W1", "proto": 4}

    def run(self):
        global writer
        writer = self.write
        base_n, t0 = 0, time.time()
        self.emit({"tag": "BASE", "seq": None, "type": "event", "state": "OK", "event": "BASE_RADIO_OK",
                   "rx_lines": 0, "rx_bad": 0, "rx_dup": 0, "acks": 0, "tx_cmds": 0, "radio": True, "site": "W1"})
        for tag, s in self.tags.items():
            self.emit(self.line(tag, s, "event", "BOOT"))
        k = 0
        while True:
            time.sleep(1.0); k += 1
            while not self.inbox.empty():                     # answer commands like the real tag would
                word, tag = (self.inbox.get().split() + [""])[:2]
                s = self.tags.get(tag)
                if not s:
                    continue
                reply = {"PING": "PONG", "LOCATE": "LOCATE_ACK", "EVAC": "EVAC_RECEIVED",
                         "STANDDOWN": "STANDDOWN_ACK", "ACK": "ACK_FROM_BASE"}.get(word)
                if word == "EVAC": s["state"] = "EVAC"
                if word in ("STANDDOWN", "ACK"): s["state"] = "OK"; s["still"] = 0
                if reply:
                    self.emit(self.line(tag, s, "event", reply))
            for tag, s in self.tags.items():
                if s["state"] not in ("MANDOWN", "PREALARM"):
                    s["phase"] += s["speed"]
                    s["still"] = 0
                else:
                    s["still"] += 1
                x, y = s["r"] * math.cos(s["phase"]) + 1.5, s["r"] * math.sin(s["phase"]) + 1.5
                if k % 3 == 0 and random.random() > 0.06:      # ~6 % simulated radio loss
                    d = {u: int(math.hypot(x - c["x"], y - c["y"]) * 100 + random.gauss(0, 25))
                         for u, c in cfg["units"].items() if "x" in c}
                    s["seq"] += 1
                    self.emit({"tag": tag, "seq": s["seq"], "type": "obs", "ftm": d, "ble": {},
                               "via": "R1" if s["r"] > 6 else "direct", "site": "W1"})
                if k % 10 == 0 and random.random() > 0.06:
                    self.emit(self.line(tag, s, "tele"))
            if k == 70:                                       # a scripted incident to exercise the views
                s = self.tags["LEB10-T02"]; s["state"] = "PREALARM"
                self.emit(self.line("LEB10-T02", s, "event", "PREALARM"))
            if k == 85 and self.tags["LEB10-T02"]["state"] == "PREALARM":
                s = self.tags["LEB10-T02"]; s["state"] = "MANDOWN"
                self.emit(self.line("LEB10-T02", s, "event", "MANDOWN"))
            if k % 30 == 0:
                base_n += 1
                self.emit({"tag": "BASE", "seq": None, "ms": int((time.time() - t0) * 1000), "type": "tele",
                           "state": "OK", "event": None, "rx_lines": k * 2, "rx_bad": base_n, "rx_dup": 0,
                           "acks": 0, "tx_cmds": 0, "radio": True, "site": "W1", "channel": 6, "mhz": 868})


# ------------------------------------------------------------------ HTTP
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/command"):
            return self._send(200, (HERE / "web" / "command.html").read_bytes(), "text/html; charset=utf-8")
        if path == "/crew":
            return self._send(200, (HERE / "web" / "crew.html").read_bytes(), "text/html; charset=utf-8")
        if path == "/view.js":
            return self._send(200, (HERE / "web" / "view.js").read_bytes(), "text/javascript; charset=utf-8")
        if path == "/data/jez_dtm_30m.i16" or path == "/data/jez_dtm_30m.json":
            f = HERE.parent / "data" / Path(path).name      # the planner's CTX terrain grid
            return self._send(200, f.read_bytes(), "application/octet-stream" if f.suffix == ".i16" else "application/json")
        if path == "/data/pov_index.json":
            return self._send(200, (HERE / "web" / "data" / "pov_index.json").read_bytes())
        if path == "/data/sim3464_walk.geojson":
            return self._send(200, (HERE / "web" / "data" / "sim3464_walk.geojson").read_bytes(), "application/geo+json")
        if path.startswith("/models/"):
            f = HERE / "models" / Path(path).name
            if f.exists() and f.suffix in (".onnx", ".json"):
                return self._send(200, f.read_bytes(), "application/octet-stream" if f.suffix == ".onnx" else "application/json")
            return self._send(404, '{"error":"not found"}')
        if path == "/samples.json":
            return self._send(200, (HERE / "web" / "samples" / "samples.json").read_bytes())
        if path.startswith("/samples/"):
            f = HERE / "web" / "samples" / Path(path).name
            if f.exists() and f.suffix == ".jpg":
                return self._send(200, f.read_bytes(), "image/jpeg")
            return self._send(404, '{"error":"not found"}')
        if path == "/hazards.json":
            return self._send(200, (HERE / "web" / "hazards.json").read_bytes())
        if path.startswith("/uploads/"):
            f = UPLOADS / Path(path).name          # name only: no directory walking
            if f.exists() and f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                return self._send(200, f.read_bytes(), "image/jpeg" if f.suffix.lower() in (".jpg", ".jpeg") else "image/" + f.suffix[1:].lower())
            return self._send(404, '{"error":"not found"}')
        if path == "/state":
            with lock:
                return self._send(200, json.dumps(snapshot()))
        if path == "/stream":
            q = queue.Queue(maxsize=500)
            subscribers.append(q)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                with lock:
                    first = json.dumps({"kind": "snapshot", **snapshot()})
                self.wfile.write(f"data: {first}\n\n".encode()); self.wfile.flush()
                while True:
                    try:
                        data = q.get(timeout=15)
                        self.wfile.write(f"data: {data}\n\n".encode())
                    except queue.Empty:
                        self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                subscribers.remove(q)
            return
        self._send(404, '{"error":"not found"}')

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        if self.path.startswith("/detect"):
            ctype = (self.headers.get("Content-Type") or "").split(";")[0]
            ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}.get(ctype)
            if not ext or n <= 0 or n > 25_000_000:
                return self._send(400, '{"ok":false,"error":"send a JPEG, PNG or WebP under 25 MB"}')
            try:
                return self._send(200, json.dumps(detect(self.rfile.read(n), ext)))
            except Exception as e:
                return self._send(503, json.dumps({"ok": False, "error": str(e)}))
        if self.path == "/report":
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
            except json.JSONDecodeError:
                return self._send(400, '{"error":"bad json"}')
            return self._send(200, json.dumps({"ok": True, "event": report(body)}))
        if self.path in ("/origin", "/frame", "/pin"):
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
                if self.path == "/origin":
                    ok = set_frame("earth", {"lat": body["lat"], "lon": body["lon"], "acc": body.get("acc")})
                    return self._send(200, json.dumps({"ok": ok, "origin": EARTH}))
                if self.path == "/frame":
                    ok = body.get("frame") in ("earth", "mars") and set_frame(body["frame"])
                    return self._send(200 if ok else 400, json.dumps({"ok": bool(ok), "error": None if ok else "set the habitat location first"}))
                if FRAME["name"] != "earth":
                    return self._send(400, json.dumps({"ok": False, "error": "phone location only makes sense on the Earth analog site"}))
                return self._send(200, json.dumps({"ok": True, "event": drop_pin(body)}))
            except (KeyError, ValueError, TypeError, json.JSONDecodeError):
                return self._send(400, '{"ok":false,"error":"bad request"}')
        if self.path != "/cmd":
            return self._send(404, '{"error":"not found"}')
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return self._send(400, '{"error":"bad json"}')
        ok, info = send_cmd(body.get("cmd"), body.get("tag"), body.get("arg"))
        self._send(200 if ok else 400, json.dumps({"ok": ok, "sent" if ok else "error": info}))


def snapshot():
    units = {k: {**u, "lat": bench_to_mars(u["x"], u["y"])[0], "lon": bench_to_mars(u["x"], u["y"])[1]}
             for k, u in cfg["units"].items() if "x" in u}
    return {"tags": state["tags"], "base": state["base"], "events": state["events"][-100:], "units": units,
            "habitat": ({"lat": EARTH["lat"], "lon": EARTH["lon"]} if FRAME["name"] == "earth" and EARTH else cfg["habitat"]),
            "scale": 1 if FRAME["name"] == "earth" else cfg["scale"], "frame": FRAME["name"], "earth_origin": EARTH,
            "mode": state["mode"], "started": state["started"]}


def main():
    global logf
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--sim", action="store_true", help="simulated tags (labelled SIMULATED in the views)")
    g.add_argument("--port", help="serial port of the base board, e.g. /dev/cu.usbmodem1101")
    g.add_argument("--replay", help="replay a recorded logs/*.jsonl session")
    ap.add_argument("--speed", type=float, default=1.0, help="replay speed")
    ap.add_argument("--http", type=int, default=8770)
    ap.add_argument("--detector-python", default=str(HERE.parent.parent / "mars-walk-dataset" / ".venv" / "bin" / "python"),
                    help="python with torch + transformers for photo detection")
    a = ap.parse_args()
    global DETECTOR_PY
    DETECTOR_PY = a.detector_python
    state["mode"] = "sim" if a.sim else "replay" if a.replay else "live"
    state["started"] = now_iso()
    if not a.replay:
        (HERE / "logs").mkdir(exist_ok=True)
        logf = open(HERE / "logs" / f"{state['mode']}-{datetime.now():%Y%m%d-%H%M%S}.jsonl", "a")
    src = (lambda: Sim().run()) if a.sim else (lambda: run_serial(a.port)) if a.port else (lambda: run_replay(a.replay, a.speed))
    threading.Thread(target=src, daemon=True).start()
    cert, key = HERE / "certs" / "habitat.crt", HERE / "certs" / "habitat.key"
    if cert.exists() and key.exists():
        import ssl
        tls = ThreadingHTTPServer(("0.0.0.0", a.http + 1), Handler)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); ctx.load_cert_chain(str(cert), str(key))
        tls.socket = ctx.wrap_socket(tls.socket, server_side=True)
        threading.Thread(target=tls.serve_forever, daemon=True).start()
        print(f"https on port {a.http + 1} (self-signed: accept the warning once on each phone)", flush=True)
    srv = ThreadingHTTPServer(("0.0.0.0", a.http), Handler)
    print(f"habitat server ({state['mode']}) on http://localhost:{a.http}/command  and  /crew?tag=LEB10-T01", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()

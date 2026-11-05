import os, re, math, time, sqlite3, threading
import requests
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__, static_folder="static", static_url_path="/static")
DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports.db")
UA = {"User-Agent": "LiveFloodMap/1.0 (learning project)"}
COUNTRY = os.environ.get("COUNTRY", "in")          # limit search to one country ("" = worldwide)
REPORT_TTL = 6 * 3600                               # a report never lives longer than 6 hours
CHECK_EVERY = 600                                   # re-verify every report against the weather every 10 minutes
FLOOD_NOW_MM, FLOOD_3H_MM = 4.0, 10.0              # rain (mm/h now, or mm in the last 3 h) that makes a flood plausible
ROUTERS = {"car": "routed-car", "bike": "routed-bike", "walk": "routed-foot"}

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

with db() as c:
    c.execute("CREATE TABLE IF NOT EXISTS reports(id INTEGER PRIMARY KEY, lat REAL, lon REAL, ts REAL)")
    cols = {r[1] for r in c.execute("PRAGMA table_info(reports)")}
    if "next_check" not in cols:
        c.execute("ALTER TABLE reports ADD COLUMN next_check REAL DEFAULT 0")
    if "mm" not in cols:
        c.execute("ALTER TABLE reports ADD COLUMN mm REAL DEFAULT 0")

def hav(a, b):  # km between (lat, lon) pairs
    R = 6371.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))

def rain_supports_flood(lat, lon):
    """Cross-check with live weather: did it rain enough here (now or in the last 3 hours) to flood a road?"""
    r = requests.get("https://api.open-meteo.com/v1/forecast", timeout=10, params={
        "latitude": f"{lat:.4f}", "longitude": f"{lon:.4f}", "current": "precipitation",
        "hourly": "precipitation", "past_hours": 3, "forecast_hours": 1, "timezone": "auto"})
    r.raise_for_status()
    j = r.json()
    now = j.get("current", {}).get("precipitation") or 0
    total = sum(v or 0 for v in j.get("hourly", {}).get("precipitation", []))
    return (now >= FLOOD_NOW_MM or total >= FLOOD_3H_MM), round(now, 1), round(total, 1)

SWEEP_LOCK, last_sweep = threading.Lock(), [0.0]

def sweep():
    """Re-check due reports against the weather every 10 min; remove any the rain no longer supports."""
    if not SWEEP_LOCK.acquire(blocking=False):
        return
    try:
        last_sweep[0] = time.time()
        now = time.time()
        with db() as c:
            c.execute("DELETE FROM reports WHERE ts < ?", (now - REPORT_TTL,))
            due = c.execute("SELECT id, lat, lon FROM reports WHERE next_check <= ? LIMIT 8", (now,)).fetchall()
        for r in due:
            try:
                ok, _, mm = rain_supports_flood(r["lat"], r["lon"])
            except Exception:                      # weather service unreachable: keep the report, retry soon
                with db() as c:
                    c.execute("UPDATE reports SET next_check=? WHERE id=?", (time.time() + 120, r["id"]))
                continue
            with db() as c:
                if ok:
                    c.execute("UPDATE reports SET next_check=?, mm=? WHERE id=?", (time.time() + CHECK_EVERY, mm, r["id"]))
                else:
                    c.execute("DELETE FROM reports WHERE id=?", (r["id"],))
    finally:
        SWEEP_LOCK.release()

def recent_reports():
    if time.time() - last_sweep[0] >= 60:
        threading.Thread(target=sweep, daemon=True).start()
    with db() as c:
        rows = c.execute("SELECT lat, lon, ts, mm FROM reports WHERE ts > ?", (time.time() - REPORT_TTL,)).fetchall()
    return [dict(r) for r in rows]

def get_weather(points):
    """Live rain + temperature from Open-Meteo (free, no API key)."""
    r = requests.get("https://api.open-meteo.com/v1/forecast", timeout=12, params={
        "latitude": ",".join(f"{p[0]:.4f}" for p in points),
        "longitude": ",".join(f"{p[1]:.4f}" for p in points),
        "current": "temperature_2m,precipitation,weather_code",
        "hourly": "precipitation", "forecast_hours": 2, "timezone": "auto"})
    r.raise_for_status()
    j = r.json()
    j = j if isinstance(j, list) else [j]
    out = []
    for x in j:
        cur = x.get("current", {})
        hourly = x.get("hourly", {}).get("precipitation", []) or [0]
        mm = max([cur.get("precipitation") or 0] + [v or 0 for v in hourly[:2]])  # now or next hour
        out.append({"mm": round(mm, 1), "temp": cur.get("temperature_2m"), "code": cur.get("weather_code")})
    return out

def rain_level(mm):
    return 3 if mm >= 10 else 2 if mm >= 4 else 1 if mm >= 0.5 else 0

@app.get("/")
def index():
    return send_from_directory("static", "index.html")

def photon(q, lat, lon):
    """General place search biased to the map view."""
    base = {"q": q, "limit": 8, "lang": "en"}
    if lat is not None:
        base.update(lat=lat, lon=lon)
    attempts = [dict(base, bbox="68,6,98,36"), base] if COUNTRY == "in" else [base]
    for p in attempts:
        try:
            r = requests.get("https://photon.komoot.io/api/", params=p, headers=UA, timeout=8)
            r.raise_for_status()
            out = []
            for f in r.json().get("features", []):
                pr, (lo, la) = f["properties"], f["geometry"]["coordinates"]
                parts = [pr.get("name"), pr.get("street"), pr.get("district") or pr.get("locality"), pr.get("city"), pr.get("state")]
                out.append({"name": ", ".join(dict.fromkeys(x for x in parts if x)), "lat": la, "lon": lo, "kind": pr.get("osm_value", "")})
            if out:
                return out
        except Exception:
            continue
    return []

def nominatim(q):
    p = {"format": "json", "q": q, "limit": 6}
    if COUNTRY:
        p["countrycodes"] = COUNTRY
    r = requests.get("https://nominatim.openstreetmap.org/search", params=p, headers=UA, timeout=8)
    return [{"name": x["display_name"], "lat": float(x["lat"]), "lon": float(x["lon"]), "kind": x.get("type", "")} for x in r.json()]

def overpass(q, lat, lon):
    """Finds named stations, bus stops, shops, hospitals, malls etc. by name within 60 km of the map view."""
    term = re.sub(r"[^\w\s\-]", " ", q).strip()
    if len(term) < 3:
        return []
    clat = 12.9716 if lat is None else lat
    clon = 77.5946 if lon is None else lon
    around = f"(around:60000,{clat},{clon})"
    sel = ['["railway"~"station|halt|subway_entrance"]', '["public_transport"="station"]', '["highway"="bus_stop"]',
           '["amenity"]', '["shop"]', '["tourism"]', '["leisure"]', '["place"]']
    body = "".join(f'nwr["name"~"{term}",i]{x}{around};' for x in sel)
    r = requests.post("https://overpass-api.de/api/interpreter", headers=UA, timeout=12,
                      data={"data": f"[out:json][timeout:9];({body});out center 40;"})
    out = []
    for e in r.json().get("elements", []):
        t = e.get("tags", {})
        la = e.get("lat") if e.get("lat") is not None else e.get("center", {}).get("lat")
        lo = e.get("lon") if e.get("lon") is not None else e.get("center", {}).get("lon")
        if la is None or lo is None or not t.get("name"):
            continue
        if t.get("railway") in ("station", "halt", "subway_entrance") or t.get("public_transport") == "station":
            metro = t.get("station") in ("subway", "metro") or "metro" in (t.get("network", "") + t.get("operator", "") + t["name"]).lower()
            kind, typ = "station", "Metro station" if metro else "Station"
        elif t.get("highway") == "bus_stop":
            kind, typ = "bus_stop", "Bus stop"
        else:
            kind = t.get("amenity") or t.get("shop") or t.get("tourism") or t.get("leisure") or t.get("place") or ""
            typ = kind.replace("_", " ").capitalize()
        where = ", ".join(x for x in (t.get("addr:suburb"), t.get("addr:city")) if x)
        label = t["name"] + (f" ({typ})" if typ else "") + (f", {where}" if where else "")
        out.append({"name": label, "lat": la, "lon": lo, "kind": kind,
                    "_k": (not t["name"].lower().startswith(term.lower()), kind != "station", hav((clat, clon), (la, lo)))})
    out.sort(key=lambda x: x.pop("_k"))
    return out

def safe(fn, *a):
    try:
        return fn(*a)
    except Exception:
        return []

@app.get("/api/geocode")
def geocode():
    q = request.args.get("q", "").strip()
    if len(q) < 3:
        return jsonify([])
    lat = request.args.get("lat", type=float)
    lon = request.args.get("lon", type=float)
    with ThreadPoolExecutor(3) as ex:
        f1, f2, f3 = ex.submit(safe, photon, q, lat, lon), ex.submit(safe, overpass, q, lat, lon), ex.submit(safe, nominatim, q)
        ph, ov, nm = f1.result(), f2.result(), f3.result()
    stations = [x for x in ov if x["kind"] == "station"]
    rest = [x for x in ov if x["kind"] != "station"]
    seen, out = set(), []
    for x in stations[:3] + ph + nm[:3] + rest + nm[3:]:
        key = (round(x["lat"], 3), round(x["lon"], 3))
        if key not in seen:
            seen.add(key)
            out.append(x)
    return jsonify(out[:10])

@app.get("/api/reverse")
def reverse():
    lat, lon = request.args.get("lat", type=float), request.args.get("lon", type=float)
    fallback = f"Pinned location ({lat:.4f}, {lon:.4f})" if lat is not None and lon is not None else "Pinned location"
    try:
        r = requests.get("https://nominatim.openstreetmap.org/reverse", headers=UA, timeout=8,
                         params={"format": "json", "lat": lat, "lon": lon, "zoom": 18})
        name = r.json().get("display_name")
        return jsonify(name=name or fallback)
    except Exception:
        return jsonify(name=fallback)

@app.get("/api/route")
def route():
    try:
        slat, slon, dlat, dlon = (float(request.args[k]) for k in ("slat", "slon", "dlat", "dlon"))
        mode = request.args.get("mode", "car")
        base = ROUTERS[mode]
    except Exception:
        return jsonify(error="Bad request"), 400
    url = f"https://routing.openstreetmap.de/{base}/route/v1/driving/{slon},{slat};{dlon},{dlat}"
    try:
        j = requests.get(url, params={"overview": "full", "geometries": "geojson", "alternatives": "true"},
                         headers=UA, timeout=20).json()
        if j.get("code") != "Ok":
            return jsonify(error="No route found between these places."), 404
    except Exception:
        return jsonify(error="Routing service is busy. Try again in a moment."), 502

    routes, samples = [], []
    for rt in j["routes"][:3]:
        g = [(c[1], c[0]) for c in rt["geometry"]["coordinates"]]
        cum = [0.0]
        for i in range(1, len(g)):
            cum.append(cum[-1] + hav(g[i - 1], g[i]))
        n = min(6, len(g))
        idx = sorted({round(i * (len(g) - 1) / max(n - 1, 1)) for i in range(n)})
        routes.append({"g": g, "cum": cum, "idx": idx, "dist": rt["distance"] / 1000, "dur": rt["duration"] / 60})
        samples += [g[i] for i in idx]
    try:
        wx = get_weather(samples)
    except Exception:
        wx = [{"mm": 0, "temp": None, "code": None}] * len(samples)

    reps, k, out = recent_reports(), 0, []
    for r in routes:
        pts, issues, level = [], [], 0
        for i in r["idx"]:
            w = wx[k]; k += 1
            pts.append({"lat": r["g"][i][0], "lon": r["g"][i][1], "mm": w["mm"]})
            lv = rain_level(w["mm"])
            level = max(level, lv)
            if lv >= 2:
                issues.append(f"{'Severe' if lv == 3 else 'Heavy'} rain ({w['mm']} mm/h), about {r['cum'][i]:.0f} km from start.")
        near = 0
        for rep in reps:
            best = min(range(len(r["g"])), key=lambda i: hav(r["g"][i], (rep["lat"], rep["lon"])))
            if hav(r["g"][best], (rep["lat"], rep["lon"])) < 0.3:
                near += 1
                issues.append(f"Flooded road reported about {r['cum'][best]:.0f} km from start.")
        if near:
            level = 3
        extra = {0: 0, 1: 0.05, 2: 0.25, 3: 0.5}[level]
        delay = round(r["dur"] * extra + 10 * near)
        out.append({"geometry": r["g"], "km": round(r["dist"], 1), "base": round(r["dur"]),
                    "minutes": round(r["dur"]) + delay, "delay": delay,
                    "risk": {"level": level, "points": pts, "issues": issues}})
    fastest = min(range(len(out)), key=lambda i: out[i]["base"])
    rec = min(range(len(out)), key=lambda i: (out[i]["risk"]["level"] >= 2, out[i]["risk"]["level"], out[i]["minutes"]))
    return jsonify(routes=out, fastest=fastest, recommended=rec, weather=wx[0])

@app.get("/api/reports")
def reports_get():
    return jsonify([{"lat": r["lat"], "lon": r["lon"], "mm": round(r["mm"] or 0, 1)} for r in recent_reports()])

@app.post("/api/reports")
def reports_post():
    d = request.get_json(silent=True) or {}
    try:
        lat, lon = float(d["lat"]), float(d["lon"])
        assert -90 <= lat <= 90 and -180 <= lon <= 180
    except Exception:
        return jsonify(ok=False, error="Bad location"), 400
    try:
        ok, now_mm, total_mm = rain_supports_flood(lat, lon)
    except Exception:
        return jsonify(ok=False, error="Could not check the weather right now. Please try again in a minute."), 503
    if not ok:
        return jsonify(ok=False, error=f"No heavy rain at this spot (last 3 hours: {total_mm} mm), so the flood report was not added."), 422
    with db() as c:
        c.execute("INSERT INTO reports(lat, lon, ts, next_check, mm) VALUES(?,?,?,?,?)",
                  (lat, lon, time.time(), time.time() + CHECK_EVERY, total_mm))
    return jsonify(ok=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)

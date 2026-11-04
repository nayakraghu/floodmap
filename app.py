import os, re, math, time, sqlite3
import requests
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__, static_folder="static", static_url_path="/static")
DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports.db")
UA = {"User-Agent": "LiveFloodMap/1.0 (learning project)"}
COUNTRY = os.environ.get("COUNTRY", "in")          # limit search to one country ("" = worldwide)
REPORT_TTL = 6 * 3600                               # flood reports stay active for 6 hours
ROUTERS = {"car": "routed-car", "bike": "routed-bike", "walk": "routed-foot"}

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

with db() as c:
    c.execute("CREATE TABLE IF NOT EXISTS reports(id INTEGER PRIMARY KEY, lat REAL, lon REAL, ts REAL)")

def hav(a, b):  # km between (lat, lon) pairs
    R = 6371.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))

def recent_reports():
    with db() as c:
        rows = c.execute("SELECT lat, lon, ts FROM reports WHERE ts > ?", (time.time() - REPORT_TTL,)).fetchall()
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
    return jsonify([{"lat": r["lat"], "lon": r["lon"]} for r in recent_reports()])

@app.post("/api/reports")
def reports_post():
    d = request.get_json(silent=True) or {}
    try:
        lat, lon = float(d["lat"]), float(d["lon"])
        assert -90 <= lat <= 90 and -180 <= lon <= 180
    except Exception:
        return jsonify(error="Bad location"), 400
    with db() as c:
        c.execute("INSERT INTO reports(lat, lon, ts) VALUES(?,?,?)", (lat, lon, time.time()))
        c.execute("DELETE FROM reports WHERE ts < ?", (time.time() - 24 * 3600,))
    return jsonify(ok=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)

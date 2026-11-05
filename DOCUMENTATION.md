# Live Flood-Aware Map: Project Documentation

**Author:** Raghavendra Devaray Nayak
**Live site:** https://nayak-floodmap.onrender.com/
**Last updated:** November 2026

---

## 1. Overview

**Live Flood-Aware Map** is a real-time web map for travelling safely when it rains. A user picks a start point and a destination, chooses car, bike or walk, and the app:

1. finds up to three routes,
2. checks live rainfall at several points along each route,
3. warns the user if a road is likely to be waterlogged or flooded,
4. estimates the extra delay, and
5. recommends the safest alternative route.

Users can also report flooded roads. Every report is cross-checked against live weather data, and false reports are rejected or removed automatically.

The app works for anyone who opens the link. No installation is needed on the user's device.

### Problem it solves
Normal navigation apps show traffic but do not clearly warn about rain-related waterlogging, which is a common problem in Indian cities such as Bengaluru. This project combines routing with live rainfall data to give an early warning and a safer alternative.

---

## 2. Features

| Area | Feature |
|---|---|
| Routing | Car, bike and walk modes; up to 3 alternative routes with distance and time |
| Vehicle icons | 5 car types (hatchback, SUV, taxi, sports, van), 5 bike types (sports bike, scooter, cycle, racer, cruiser), and a walking-man icon for walk mode |
| Flood alerts | Live rain check along the route, flood and waterlogging warning, delay estimate, safer route recommendation |
| Weather | Temperature and rain (mm/h) at the start point, refreshed every 2 minutes |
| Flood reports | Users tap the map to report a flooded road. Reports are verified against rainfall and re-checked every 10 minutes |
| Search | Finds places, metro stations, bus stops, hospitals, shops and more, ranked near the current map view |
| Picking places | Type a name, use the 📌 pin button, double-tap or double-click the map, drag the A and B pins, or use 🎯 for the current location |
| Live trip | Real GPS tracking. The icon moves only when the user moves |
| Trip controls | Pause, resume and stop. Automatic arrival detection |
| Ride summary | Popup on arrival showing distance, duration and average speed |
| Off-route handling | Automatic re-route if the user leaves the route by more than about 100 m |
| Map views | OpenStreetMap, Esri Streets and Satellite (with labels) |
| Appearance | Dark mode and light mode, remembered between visits; works on phones and computers |

---

## 3. Technology Stack

### Backend
| Technology | Purpose |
|---|---|
| **Python 3** | Main backend language |
| **Flask 3** | Web framework: serves the pages and the JSON API |
| **requests** | Calls the external map, weather and search services |
| **SQLite** (built into Python) | Stores flood reports |
| **gunicorn** | Production web server used on Render |

### Frontend
| Technology | Purpose |
|---|---|
| **HTML5** | Page structure |
| **CSS3** | Styling, responsive layout, dark/light themes using CSS variables |
| **JavaScript (ES2020, no framework)** | All app logic: search, routing, alerts, GPS tracking |
| **Leaflet 1.9.4** | Interactive map library |
| **Browser Geolocation API** | Real GPS position for live trips |
| **localStorage** | Remembers the chosen theme |

### Hosting
| Service | Purpose |
|---|---|
| **GitHub** | Stores the source code |
| **Render** (free plan) | Hosts the app and gives it an HTTPS link |

---

## 4. Requirements

### To use the site
- Any modern browser (Chrome, Edge, Firefox, Safari) on a phone or computer
- Internet connection
- For live GPS trips: location permission, and the site must be opened on an `https://` link or `localhost`. A phone gives the best GPS accuracy.

### To run it on your own computer
- Python 3.10 or newer
- Internet connection (the app calls online services)
- Python packages (listed in `requirements.txt`):

```
flask>=3.0
requests>=2.31
gunicorn>=21.2
```

No API keys, accounts or paid services are needed.

---

## 5. Data Sources and External Services

All sources below are free and need no API key.

| Purpose | Source | Notes |
|---|---|---|
| Map tiles (default) | OpenStreetMap (`tile.openstreetmap.org`) | Map data © OpenStreetMap contributors |
| Map tiles (alternatives) | Esri World Street Map, World Imagery and Reference labels (`server.arcgisonline.com`) | Used for the Esri Streets and Satellite views |
| Routing | `routing.openstreetmap.de` (OSRM-based, with car, bike and foot profiles) | Returns route geometry, distance, duration and alternatives |
| Live weather | Open-Meteo forecast API (`api.open-meteo.com`) | Current rain and temperature, hourly rain, and rain over the past 3 hours |
| Place search | Photon (`photon.komoot.io`) | General place and landmark search, biased to the map view |
| Place search and reverse lookup | Nominatim (`nominatim.openstreetmap.org`) | Address search, and converting a pinned point into a place name |
| Landmark search | Overpass API (`overpass-api.de`) | Finds named stations, bus stops, shops, hospitals and more by name within 60 km of the map |
| User location | Browser Geolocation API | Real GPS position, used only while a trip is running |
| Flood reports | Reports submitted by users of the app | Stored in the app's own SQLite database |

### Usage and attribution notes
- These are public community services meant for light use. For heavy traffic, use your own servers or a paid plan.
- Nominatim requires a proper `User-Agent` and fair use (about 1 request per second). The app sends one and waits briefly while the user types before searching.
- OpenStreetMap data is © OpenStreetMap contributors (ODbL licence). Esri imagery requires its attribution, which Leaflet shows on the map.
- Open-Meteo's free service is for non-commercial use and asks for attribution (data under CC BY 4.0). Check their terms before any commercial use.

---

## 6. Architecture

```
 Browser (HTML + CSS + JavaScript + Leaflet)
        │
        │  JSON over HTTPS
        ▼
 Flask backend (app.py) ───────► SQLite (flood reports)
        │
        ├──► Photon, Nominatim, Overpass     (search)
        ├──► routing.openstreetmap.de        (routes)
        └──► Open-Meteo                      (live rain and temperature)
```

The browser talks only to the Flask backend. The backend contacts the external services, combines the results (for example, route plus rainfall) and returns one answer.

### Project structure

```
floodmap/
├── app.py              Flask backend and API
├── requirements.txt    Python packages
├── README.md           Short description for GitHub
├── DOCUMENTATION.md    This document
└── static/
    ├── index.html      Page layout
    ├── style.css       Styles, dark and light themes
    └── app.js          Map and app logic
```

`reports.db` (the flood report database) is created automatically when the app runs. It should not be uploaded to GitHub.

---

## 7. Backend API

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | Serves the web page |
| GET | `/api/geocode?q=&lat=&lon=` | Searches for places. Combines Photon, Overpass and Nominatim results, removes duplicates and returns up to 10 |
| GET | `/api/reverse?lat=&lon=` | Converts a point on the map into a place name |
| GET | `/api/route?slat=&slon=&dlat=&dlon=&mode=` | Returns up to 3 routes (`mode` is `car`, `bike` or `walk`) with weather, flood risk, delay and a recommended route |
| GET | `/api/reports` | Returns the active, verified flood reports |
| POST | `/api/reports` | Submits a flood report (`lat`, `lon`). It is accepted only if the weather supports it |

Optional setting: the environment variable `COUNTRY` (default `in`) limits place search to one country. Set it empty for worldwide search.

---

## 8. How the Flood Logic Works

### 8.1 Route risk check
1. The backend asks the routing service for up to 3 routes.
2. For each route it picks up to 6 evenly spaced points.
3. It asks Open-Meteo for rain at all those points in one request. For each point it uses the higher of the current rain and the next hour's forecast.
4. Each point gets a rain level:

| Rain (mm/h) | Level | Meaning |
|---|---|---|
| below 0.5 | 0 | Clear |
| 0.5 to 4 | 1 | Light rain |
| 4 to 10 | 2 | Heavy rain, flood warning |
| 10 or more | 3 | Severe rain, flood risk |

5. A verified flood report within 300 m of the route sets the route to level 3.
6. The route's level is the highest level found. Routes at level 2 or 3 trigger a warning.

### 8.2 Delay estimate and recommendation
- Extra time added: level 1 about +5%, level 2 about +25%, level 3 about +50%, plus 10 minutes for each flood report near the route.
- The recommended route is the one with the lowest risk level, and among equals, the shortest adjusted time.
- If the fastest route is risky and a safer one exists, the app shows the warning and switches to the safer route.

### 8.3 Verification of flood reports
1. A user taps the map to report a flood.
2. The backend checks live rainfall at that exact spot. The report is accepted only if rain is at least **4 mm/h now** or at least **10 mm in the last 3 hours**.
3. If there was no heavy rain, the report is **rejected** and never added. The user sees a message explaining why.
4. Accepted reports are **re-checked every 10 minutes**. If the rain no longer supports the report, it is **removed**.
5. If the weather service cannot be reached during a re-check, the report is kept and checked again in about 2 minutes.
6. Every report is deleted after 6 hours at most.

The re-checks run when people use the site, because the free hosting plan has no background jobs. A report can therefore stay a few minutes beyond its 10-minute check if nobody is using the site.

### 8.4 Live trip tracking
- Position comes from the browser's GPS and is ignored if its accuracy is worse than 200 m.
- Distance is the sum of real GPS movement. Small jitter (under 5 m) and sudden jumps (over 500 m) are ignored.
- Arrival is detected within about 50 m of the destination and ends the ride automatically.
- Pausing stops tracking and the timer, and movement while paused is not counted.
- The route risk is refreshed every 2 minutes from the user's current position.

---

## 9. Installation and Running

### 9.1 Run on your own computer (Windows)

1. Install Python 3.10 or newer from python.org.
2. Open the project folder (the one that contains `app.py`).
3. Open Command Prompt in that folder (click the address bar in File Explorer, type `cmd`, press Enter).
4. Install the packages:
   ```
   py -m pip install -r requirements.txt
   ```
5. Start the app:
   ```
   py app.py
   ```
6. Open **http://localhost:5000** in your browser. Keep the Command Prompt window open while using the app.

On Mac or Linux, use `python3` and `pip3` instead of `py`.

### 9.2 Deploy online (GitHub and Render)

1. Upload the project files (`app.py`, `requirements.txt`, `README.md`, `static/`) to a GitHub repository.
2. On render.com, create a **Web Service** and connect the repository.
3. Use these settings:
   - Language: Python 3
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn app:app`
   - Instance type: Free
4. Click **Deploy Web Service**. When it shows **Live**, the app is available at `https://<service-name>.onrender.com`.

### 9.3 Updating the live site
1. Replace the changed files in the GitHub repository (**Add file** → **Upload files** → **Commit changes**).
2. Render redeploys automatically in about 2 to 5 minutes.
3. Press **Ctrl+F5** on the site to load the newest version.

---

## 10. Tools Used

| Tool | Use |
|---|---|
| Python and pip | Backend language and package installer |
| Flask, requests, gunicorn | Web framework, HTTP client, production server |
| Leaflet | Interactive maps in the browser |
| Windows Command Prompt | Running and testing the app locally |
| Web browser | Testing and debugging the interface |
| GitHub | Source code storage and version history |
| Render | Free web hosting with HTTPS |
| Claude (Anthropic AI assistant) | Helped design and write the code and this documentation |

---

## 11. Limitations

- **Flood detection is an estimate.** Rainfall data shows that a flood is likely, not that water is actually on a particular road. Real flood sensors or official flood data are not used.
- **No live traffic data.** Delay estimates only account for rain and flood reports, not traffic jams.
- **Map coverage depends on OpenStreetMap.** Some shops and businesses may be missing compared with commercial maps. Missing places can be added at openstreetmap.org.
- **Free hosting limits.** The site sleeps after about 15 minutes without visitors, so the first load can take around a minute. The flood report database is temporary and can reset when the app restarts or is redeployed.
- **Public services have usage limits.** Heavy use may need self-hosted or paid routing, search and weather services.
- **Alternative routes** are shown only when the routing service finds them.
- **Search and map defaults are tuned for India** (Bengaluru view, India-biased search).
- **Vehicle icons are emoji**, so they look slightly different on different phones and computers.
- **GPS accuracy** is much better on phones than on laptops.

---

## 12. Possible Future Improvements

- Permanent database (such as PostgreSQL) so flood reports survive restarts
- Official flood or rainfall-station data for more accurate warnings
- Traffic data for better time estimates
- Push notifications and voice guidance during a trip
- Saved places, trip history and user accounts
- Custom vehicle icons as images instead of emoji

---

## 13. Credits and Licence

- Map data © OpenStreetMap contributors
- Satellite imagery and street tiles by Esri
- Weather data by Open-Meteo.com
- Place search by Photon (Komoot), Nominatim and the Overpass API
- Map library: Leaflet

© 2026 Raghavendra Devaray Nayak. All rights reserved.

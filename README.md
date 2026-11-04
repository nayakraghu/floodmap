# Live Flood-Aware Map

Python (Flask) backend + HTML/CSS/JS frontend. Free services only, no API keys:
OpenStreetMap (map tiles + search), routing.openstreetmap.de (car/bike/walk routes), Open-Meteo (live rain).

## Run on your computer
    pip install -r requirements.txt
    python app.py
Open http://localhost:5000

## Put it online (Render.com, free)
1. Create a GitHub account and a new repository; upload all files in this folder.
2. On render.com: New > Web Service > connect the repository.
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn app:app`
5. Deploy. Share the https://....onrender.com link. It works on any phone or laptop.

Notes: the free plan sleeps when idle (first load takes ~30 s) and resets flood reports on redeploy.
Set the environment variable COUNTRY (default `in`) to change the search country, or empty for worldwide.

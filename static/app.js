const $ = s => document.querySelector(s);
const TYPES = {
  car: [{e:'🚗',n:'Hatchback'},{e:'🚙',n:'SUV'},{e:'🚕',n:'Taxi'},{e:'🏎️',n:'Sports'},{e:'🚐',n:'Van'}],
  bike: [{e:'🏍️',n:'Sports bike'},{e:'🛵',n:'Scooter'},{e:'🚲',n:'Cycle'},{e:'🚴',n:'Racer'},{e:'🏍️',n:'Cruiser',f:'hue-rotate(160deg) saturate(2)'}],
  walk: [{e:'🚶',n:'Walker'}]
};
const SPEED = {car: 11, bike: 6, walk: 1.4};   // metres per second at "real speed"
const BADGE = ['✅ Clear','🌦 Light rain','⚠️ Heavy rain','🌊 Flood risk'];

const map = L.map('map', {doubleClickZoom: false}).setView([12.9716, 77.5946], 11);
const osmStd = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom: 19, attribution: '© OpenStreetMap contributors'}).addTo(map);
const esriStreets = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}', {maxZoom: 19, attribution: 'Tiles © Esri'});
const satellite = L.layerGroup([
  L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {maxZoom: 19, attribution: 'Imagery © Esri'}),
  L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}', {maxZoom: 19})]);
L.control.layers({'OpenStreetMap': osmStd, 'Esri Streets': esriStreets, 'Satellite': satellite}, null, {position: 'bottomright'}).addTo(map);
map.on('baselayerchange', e => document.body.classList.toggle('sat', e.name === 'Satellite'));
const routeLayer = L.layerGroup().addTo(map), rainLayer = L.layerGroup().addTo(map), repLayer = L.layerGroup().addTo(map);

let mode = 'car', typeIdx = 0, pts = {from: null, to: null};
let routes = [], sel = 0, fastest = 0, rec = 0;
let vehicle = null, timer = null, watchId = null, reporting = false;

/* ---------- vehicle picker ---------- */
function renderTypes() {
  const box = $('#types'); box.innerHTML = '';
  TYPES[mode].forEach((t, i) => {
    const b = document.createElement('button');
    b.className = i === typeIdx ? 'sel' : '';
    b.innerHTML = `<span style="${t.f ? 'filter:' + t.f : ''}">${t.e}</span>${t.n}`;
    b.onclick = () => { typeIdx = i; renderTypes(); if (vehicle) vehicle.setIcon(icon()); };
    box.appendChild(b);
  });
  box.hidden = TYPES[mode].length < 2;
}
function icon() {
  const t = TYPES[mode][typeIdx] || TYPES[mode][0];
  return L.divIcon({className: '', iconSize: [40, 40], iconAnchor: [20, 20],
    html: `<div class="veh " style="${t.f ? 'filter:' + t.f : ''}">${t.e}</div>`});
}
document.querySelectorAll('.modes button').forEach(b => b.onclick = () => {
  document.querySelectorAll('.modes button').forEach(x => x.classList.remove('on'));
  b.classList.add('on'); mode = b.dataset.m; typeIdx = 0; renderTypes(); getRoutes();
});

/* ---------- search boxes ---------- */
function bindSearch(id, key) {
  const inp = $('#' + id), box = $('#' + id + '-s'); let t;
  inp.addEventListener('input', () => {
    clearTimeout(t); pts[key] = null; updatePins();
    const q = inp.value.trim();
    if (q.length < 3) { box.innerHTML = ''; return; }
    t = setTimeout(async () => {
      box.innerHTML = '<li>Searching…</li>';
      const c = map.getCenter();
      const r = await (await fetch(`/api/geocode?q=${encodeURIComponent(q)}&lat=${c.lat}&lon=${c.lng}`)).json();
      box.innerHTML = '';
      r.forEach(p => {
        const li = document.createElement('li');
        li.textContent = (['station','subway_entrance','halt'].includes(p.kind) ? '🚇 ' : ['bus_stop','bus_station'].includes(p.kind) ? '🚌 ' : '📍 ') + p.name;
        li.onclick = () => { pts[key] = p; inp.value = p.name; box.innerHTML = ''; updatePins(); map.setView([p.lat, p.lon], Math.max(map.getZoom(), 14)); getRoutes(); };
        box.appendChild(li);
      });
    }, 600);
  });
}
bindSearch('from', 'from'); bindSearch('to', 'to');
$('#gps').onclick = () => navigator.geolocation.getCurrentPosition(p => {
  pts.from = {lat: p.coords.latitude, lon: p.coords.longitude, name: 'My location'};
  $('#from').value = 'My location'; updatePins(); getRoutes();
}, () => alert('Location permission denied. Type a starting place instead.'));

/* ---------- routes + flood check ---------- */
async function getRoutes(silent = false, origin = null) {
  if (!pts.from || !pts.to) return;
  if (!silent) stopTrip();
  const o = origin || pts.from;
  const q = new URLSearchParams({slat: o.lat, slon: o.lon, dlat: pts.to.lat, dlon: pts.to.lon, mode});
  const d = await (await fetch('/api/route?' + q)).json();
  if (d.error) { $('#alert').hidden = false; $('#alert').className = 'bad'; $('#alert').textContent = d.error; return; }
  const keep = silent && !origin && routes.length ? sel : null;
  routes = d.routes; fastest = d.fastest; rec = d.recommended;
  sel = keep !== null && keep < routes.length ? keep : rec;
  const w = d.weather, wet = w.mm >= 0.5;
  $('#wx').textContent = `${wet ? '🌧' : (w.code > 3 ? '☁️' : '☀️')} ${w.temp ?? '–'}°C at start, rain ${w.mm} mm/h (updates every 2 min)`;
  draw(!silent);
}
function draw(fit) {
  routeLayer.clearLayers(); rainLayer.clearLayers();
  routes.forEach((r, i) => {
    const bad = r.risk.level >= 2, on = i === sel;
    L.polyline(r.geometry, {color: bad ? '#d93025' : on ? '#1a73e8' : '#7a7a7a', weight: on ? 7 : 5,
      opacity: on ? .95 : .6, dashArray: bad && !on ? '8 8' : null}).on('click', () => { sel = i; draw(false); }).addTo(routeLayer);
  });
  const r = routes[sel];
  r.risk.points.filter(p => p.mm >= 0.5).forEach(p =>
    L.circleMarker([p.lat, p.lon], {radius: 9 + Math.min(p.mm, 15), fillOpacity: .35,
      color: p.mm >= 10 ? '#b00020' : p.mm >= 4 ? '#e8710a' : '#1a73e8'}).bindPopup(`🌧 ${p.mm} mm/h`).addTo(rainLayer));
  if (fit) map.fitBounds(L.polyline(r.geometry).getBounds(), {padding: [50, 50]});
  cards(); banner();
}
function cards() {
  $('#routes').innerHTML = routes.map((r, i) =>
    `<div class="card ${i === sel ? 'on' : ''}" data-i="${i}"><b>Route ${i + 1}</b> · ${r.minutes} min · ${r.km} km` +
    `<span class="badge">${BADGE[r.risk.level]}</span>${i === rec && routes.length > 1 ? '<span class="badge">⭐ Recommended</span>' : ''}</div>`).join('');
  document.querySelectorAll('.card').forEach(c => c.onclick = () => { sel = +c.dataset.i; draw(false); });
}
function banner() {
  const a = $('#alert'), r = routes[sel], f = routes[fastest];
  a.hidden = false;
  const w = r.risk.level >= 2 ? r : (f.risk.level >= 2 ? f : null);
  if (!w) { a.className = 'ok'; a.textContent = '✅ No heavy rain or flood reports on this route.'; return; }
  let msg = '⚠️ <b>Road may be flooded or waterlogged.</b><br>' + w.risk.issues.join('<br>') + `<br>Expect delays of about +${w.delay} min.`;
  if (w !== r) msg += `<br>👉 Showing safer <b>Route ${sel + 1}</b> (${r.minutes} min).`;
  else {
    const alt = routes.findIndex((x, i) => i !== sel && x.risk.level < r.risk.level);
    msg += alt >= 0 ? `<br>👉 Try <b>Route ${alt + 1}</b> instead (${routes[alt].minutes} min).` : '<br>No safer route found. Consider waiting or leaving later.';
  }
  a.className = 'bad'; a.innerHTML = msg;
}

/* ---------- trip: simulated or real GPS ---------- */
let lastPos = null, lastReroute = 0, prevLL = null, bobT = null, cumCache = {g: null, cum: null};
function cumOf(g) {
  if (cumCache.g !== g) { const c = [0]; for (let i = 1; i < g.length; i++) c.push(c[i - 1] + map.distance(g[i - 1], g[i])); cumCache = {g, cum: c}; }
  return cumCache.cum;
}
function stopTrip(keepMarker) {
  if (watchId !== null) { navigator.geolocation.clearWatch(watchId); watchId = null; }
  if (vehicle && !keepMarker) { map.removeLayer(vehicle); vehicle = null; }
  prevLL = null; lastPos = null;
  $('#start').textContent = '▶ Start trip';
}
function onPos(p) {
  const ll = [p.coords.latitude, p.coords.longitude];
  if (p.coords.accuracy > 200) { $('#status').textContent = `Waiting for a precise GPS signal (±${Math.round(p.coords.accuracy)} m). A phone gives the best accuracy.`; return; }
  lastPos = {lat: ll[0], lon: ll[1], name: 'My location'};
  if (!vehicle) { vehicle = L.marker(ll, {icon: icon(), zIndexOffset: 1000}).addTo(map); map.setView(ll, Math.max(map.getZoom(), 16)); }
  else { vehicle.setLatLng(ll); map.panTo(ll); }
  const moved = prevLL ? map.distance(prevLL, ll) : 0; prevLL = ll;
  const el = vehicle.getElement() && vehicle.getElement().firstChild;
  if (el && mode === 'walk' && moved > 3) { el.classList.add('walk'); clearTimeout(bobT); bobT = setTimeout(() => el.classList.remove('walk'), 4000); }
  const g = routes[sel].geometry, cum = cumOf(g);
  let best = 0, bd = Infinity;
  for (let i = 0; i < g.length; i++) { const d = map.distance(ll, g[i]); if (d < bd) { bd = d; best = i; } }
  if (map.distance(ll, g.at(-1)) < 50) { stopTrip(true); $('#status').textContent = '🎉 You have arrived.'; return; }
  if (bd > 100) {
    $('#status').textContent = '⚠️ You are off the route. Finding a new one…';
    if (Date.now() - lastReroute > 20000) { lastReroute = Date.now(); getRoutes(true, lastPos); }
  } else {
    $('#status').textContent = `${((cum.at(-1) - cum[best]) / 1000).toFixed(1)} km to go`;
  }
}
function geoMsg(e) {
  if (!window.isSecureContext) return 'Location only works on https links or on localhost.';
  if (e.code === 1) return 'Location is blocked for this site. Click the icon at the left of the address bar, set Location to Allow, refresh the page, then press Start trip again.';
  if (e.code === 3) return 'Could not get your location in time. Check your signal and try again.';
  return 'Your device could not find your location. Turn on Location in your Windows or phone settings, then try again.';
}
function startTrip() {
  if (!routes.length) { $('#status').textContent = 'Pick a start and destination first.'; return; }
  if (!navigator.geolocation) { $('#status').textContent = 'This device has no GPS.'; return; }
  stopTrip();
  $('#start').textContent = '■ Stop trip';
  $('#status').textContent = 'Waiting for your location…';
  watchId = navigator.geolocation.watchPosition(onPos, err => {
    $('#status').textContent = geoMsg(err); stopTrip();
  }, {enableHighAccuracy: true, maximumAge: 2000, timeout: 20000});
}
$('#start').onclick = () => watchId !== null ? stopTrip() : startTrip();

/* ---------- crowd-sourced flood reports ---------- */
function toast(msg) { const h = $('#hint'); h.textContent = msg; h.hidden = false; clearTimeout(h._t); h._t = setTimeout(() => { h.hidden = true; }, 6000); }
async function loadReports() {
  const r = await (await fetch('/api/reports')).json();
  repLayer.clearLayers();
  r.forEach(p => L.marker([p.lat, p.lon], {icon: L.divIcon({className: '', html: '<div class="flood">🌊</div>', iconSize: [30, 30]})})
    .bindPopup(`Flooded road reported<br>Rain in last 3 h: ${p.mm} mm<br>Re-checked against the weather every 10 min`).addTo(repLayer));
}
$('#report').onclick = () => {
  reporting = !reporting; document.body.classList.toggle('reporting', reporting); if (reporting) cancelPick();
  $('#report').textContent = reporting ? 'Tap the flooded spot on the map…' : '🌊 Report a flooded road';
};
map.on('click', async e => {
  if (picking || reporting) lastAct = Date.now();
  if (picking) { const k = picking; cancelPick(); setPoint(k, e.latlng.lat, e.latlng.lng); return; }
  if (!reporting) return;
  reporting = false; document.body.classList.remove('reporting');
  $('#report').textContent = '🌊 Report a flooded road';
  toast('Checking rainfall at this spot…');
  let d = {};
  try { d = await (await fetch('/api/reports', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({lat: e.latlng.lat, lon: e.latlng.lng})})).json(); }
  catch (err) { d = {error: 'Could not reach the server.'}; }
  toast(d.ok ? '🌊 Verified by rainfall data and added to the map.' : (d.error || 'Report not added.'));
  await loadReports(); getRoutes(true);
});
$('#toggle').onclick = () => { const b = $('#body'); b.hidden = !b.hidden; $('#toggle').textContent = b.hidden ? '▲' : '▼'; };

/* ---------- pin start / destination on the map ---------- */
const pinLayer = L.layerGroup().addTo(map);
let picking = null;
function pinIcon(l, c) {
  return L.divIcon({className: '', iconSize: [30, 30], iconAnchor: [15, 30], html: `<div class="pin" data-l="${l}" style="background:${c}"></div>`});
}
function updatePins() {
  pinLayer.clearLayers();
  [['from', 'A', '#1e8e3e'], ['to', 'B', '#d93025']].forEach(([k, l, c]) => {
    const p = pts[k]; if (!p) return;
    L.marker([p.lat, p.lon], {icon: pinIcon(l, c), draggable: true, zIndexOffset: 900})
      .on('dragend', e => { const ll = e.target.getLatLng(); setPoint(k, ll.lat, ll.lng); }).addTo(pinLayer);
  });
}
async function setPoint(k, lat, lon) {
  pts[k] = {lat, lon, name: 'Pinned location'};
  $('#' + k).value = 'Finding place name…';
  try { pts[k].name = (await (await fetch(`/api/reverse?lat=${lat}&lon=${lon}`)).json()).name; } catch (e) {}
  $('#' + k).value = pts[k].name; updatePins(); getRoutes();
}
function cancelPick() {
  picking = null; document.body.classList.remove('picking'); $('#hint').hidden = true;
  $('#body').hidden = false; $('#toggle').textContent = '▼';
}
document.querySelectorAll('.pick').forEach(b => b.onclick = () => {
  picking = b.dataset.k; reporting = false; document.body.classList.remove('reporting');
  document.body.classList.add('picking');
  $('#hint').textContent = picking === 'from' ? '📌 Tap the map to set your starting point' : '📌 Tap the map to set your destination';
  $('#hint').hidden = false; $('#body').hidden = true; $('#toggle').textContent = '▲';
});

renderTypes(); loadReports();
setInterval(() => { loadReports(); if (routes.length) getRoutes(true, watchId !== null ? lastPos : null); }, 120000);

/* ---------- dark / light mode ---------- */
function setTheme(t) {
  document.documentElement.dataset.theme = t;
  $('#theme').textContent = t === 'dark' ? '☀️' : '🌙';
  try { localStorage.setItem('theme', t); } catch (e) {}
}
let savedTheme = null;
try { savedTheme = localStorage.getItem('theme'); } catch (e) {}
setTheme(savedTheme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'));
$('#theme').onclick = () => setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');

/* ---------- double-tap any spot to set start or destination ---------- */
let lastAct = 0;
function applyPoint(k, lat, lon, name) {
  pts[k] = {lat, lon, name}; $('#' + k).value = name; updatePins(); getRoutes();
}
map.on('dblclick', async e => {
  if (Date.now() - lastAct < 700) return;
  const {lat, lng} = e.latlng;
  const pop = L.popup().setLatLng(e.latlng).setContent('Finding place…').openOn(map);
  let name = `Pinned location (${lat.toFixed(4)}, ${lng.toFixed(4)})`;
  try { name = (await (await fetch(`/api/reverse?lat=${lat}&lon=${lng}`)).json()).name || name; } catch (err) {}
  const box = document.createElement('div'), t = document.createElement('div');
  t.textContent = name; t.style.cssText = 'max-width:230px;margin-bottom:8px;font-size:13px';
  const mk = (label, k) => { const b = document.createElement('button'); b.textContent = label; b.style.margin = '0 6px 4px 0';
    b.onclick = () => { map.closePopup(); applyPoint(k, lat, lng, name); }; return b; };
  box.append(t, mk('Set as start', 'from'), mk('Set as destination', 'to'));
  pop.setContent(box);
});

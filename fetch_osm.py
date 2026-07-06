#!/usr/bin/env python3
"""Fetch OSM peaks (ele>=2000) + mountain huts in the Alps via Overpass API.

Output: soiusa_osm_peaks.geojson, soiusa_osm_huts.geojson (compact, committed).
Loaded by build.py as URL-based MapLibre sources (NOT inlined) to keep index.html small.
© OpenStreetMap contributors, ODbL.
"""
import io
import json
import pathlib
import re
import sys
import time
import urllib.parse
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = pathlib.Path(__file__).parent

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",   # zuletzt: haengt zeitweise (Timeout)
]
BBOX = "42.5,3.5,49.5,18.5"   # S,W,N,E — Alpenraum (deckt maxBounds ab)
MIN_ELE = 2000

PEAKS_Q = f'[out:json][timeout:300];(node["natural"="peak"]["name"]["ele"]({BBOX}););out qt;'
# nwr + out center: huts/passes are often mapped as building WAYS, not nodes.
HUTS_Q = (f'[out:json][timeout:300];'
          f'(nwr["tourism"="alpine_hut"]["name"]({BBOX});'
          f'nwr["tourism"="wilderness_hut"]["name"]({BBOX}););out center;')
PASS_Q = (f'[out:json][timeout:300];'
          f'(nwr["mountain_pass"="yes"]["name"]({BBOX}););out center;')

# ── Anreise-Datenschicht (SPEC_Orte_Seilbahnen_Parkplaetze) ──────────────────
# Orte: city/town/village immer; hamlet nur wenn ele-getaggt (dann >1200 m Filter).
PLACES_Q = (f'[out:json][timeout:300];'
            f'(node["place"~"^(city|town|village)$"]["name"]({BBOX});'
            f'node["place"="hamlet"]["name"]["ele"]({BBOX}););out qt;')
# Seilbahnen: NUR cable_car + gondola (Michael-Entscheid). Linien + zugehoerige Stationen;
# als Punkt spaeter die niedrigste Station (Talstation) je Linie.
CABLE_Q = (f'[out:json][timeout:300];'
           f'way["aerialway"~"^(cable_car|gondola)$"]({BBOX})->.lines;'
           f'(.lines; node(w.lines)["aerialway"="station"];);out;')
# W4: Seilbahn-LINIEN (voller Verlauf Tal->Berg) — NUR cable_car + gondola (keine Sessellifte).
CABLE_LINES_Q = (f'[out:json][timeout:300];'
                 f'(way["aerialway"~"^(cable_car|gondola)$"]({BBOX}););out geom;')
# Wanderparkplaetze: hiking=yes ODER Name enthaelt Wanderparkplatz/Wanderer. v1 = nur Zaehlen.
PARK_Q = (f'[out:json][timeout:300];'
          f'(nwr["amenity"="parking"]["hiking"="yes"]({BBOX});'
          f'nwr["amenity"="parking"]["name"~"Wanderparkplatz|Wanderer",i]({BBOX}););out center;')
PLACE_RANK = {"city": 3, "town": 2, "village": 1, "hamlet": 0}

# ── Peak hierarchy tiers (0 Mont Blanc · 1 Länder-Höchste · 2/3/4 Höhenbänder) ──
NAMED_PEAKS = {   # name substring : (tier, approx ele) — Wikidata-verified values
    "Mont Blanc":       (0, 4806),
    "Dufourspitze":     (1, 4634),
    "Gran Paradiso":    (1, 4061),
    "Großglockner":     (1, 3798),
    "Zugspitze":        (1, 2962),
    "Triglav":          (1, 2864),
    "Vorder Grauspitz": (1, 2599),
}


def peak_tier(name, ele):
    low = (name or "").lower()
    for key, (t, kele) in NAMED_PEAKS.items():
        if key.lower() in low and abs(ele - kele) <= 45:
            return t
    if ele >= 4000:
        return 2
    if ele >= 3000:
        return 3
    return 4


# Landmark peaks (touristic icons) — flag independent of height. name substr : approx ele.
LANDMARKS = {
    "Matterhorn": 4478, "Eiger": 3967, "Mönch": 4107, "Jungfrau": 4158, "Mont Blanc": 4806,
    "Großglockner": 3798, "Grossglockner": 3798, "Zugspitze": 2962, "Watzmann": 2713,
    "Cima Grande": 2999, "Drei Zinnen": 2999, "Marmolada": 3343, "Marmolata": 3343,
    "Langkofel": 3181, "Sassolungo": 3181, "Schlern": 2563, "Sciliar": 2563,
    "Hoher Dachstein": 2995, "Säntis": 2502, "Triglav": 2864, "Piz Bernina": 4048,
    "Ortler": 3905, "Ortles": 3905, "Grandes Jorasses": 4208, "Dent du Géant": 4013,
    "Großvenediger": 3657, "Wildspitze": 3768, "Tofana di Rozes": 3225, "Civetta": 3220,
    "Monte Pelmo": 3168, "Cima Tosa": 3136, "Dufourspitze": 4634, "Dom": 4545,
    "Dent Blanche": 4357, "Gran Paradiso": 4061,
}


def is_landmark(name, ele):
    low = (name or "").lower()
    for k, ke in LANDMARKS.items():
        if k.lower() in low and abs(ele - ke) <= 70:
            return True
    return False


# Famous passes — matched against OSM name in any language.
FAMOUS_PASS_RE = re.compile(
    r"Stilfser|Stelvio|Timmelsjoch|Passo del Rombo|Hochtor|Brennerpass|Passo del Brennero|"
    r"Reschenpass|Passo di Resia|Fernpass|Arlbergpass|Grimselpass|Furkapass|Sustenpass|"
    r"Gotthardpass|Passo del San Gottardo|San Bernardino|Splügenpass|Passo dello Spluga|"
    r"Julierpass|Malojapass|Berninapass|Passo del Bernina|Flüelapass|Simplonpass|Passo del Sempione|"
    r"Grosser Sankt Bernhard|Großer Sankt Bernhard|Grand-Saint-Bernard|Gran San Bernardo|"
    r"Col du Galibier|Col de l.Iseran|Bonette|Mont ?Cenis|Moncenisio|Sellajoch|Passo (di )?Sella|"
    r"Pordoijoch|Passo Pordoi|Grödnerjoch|Groednerjoch|Passo Gardena|Falzarego|Gaviapass|Passo di Gavia|"
    r"Tonalepass|Passo del Tonale", re.IGNORECASE)

# Curated famous passes with coordinates (Wikidata) — guarantees these get famous=1
# even if the OSM name misses the regex; matched by nearest OSM pass.
FAMOUS_PASS_COORDS = [
    (46.5300, 10.4540), (46.9053, 11.0967), (47.0071, 11.5065), (46.8344, 10.5101),
    (47.3625, 10.8310), (47.1298, 10.2106), (46.5617, 8.3453), (46.5728, 8.4167),
    (46.7300, 8.4490), (46.5592, 8.5617), (46.4970, 9.1720), (46.5055, 9.3304),
    (46.4722, 9.7278), (46.4000, 9.6958), (46.4108, 10.0275), (46.7515, 9.9486),
    (46.2502, 8.0317), (45.8691, 7.1704), (45.0640, 6.4080), (45.4169, 7.0308),
    (44.3267, 6.8072), (46.5067, 11.7572), (46.4877, 11.8136), (46.5500, 11.8094),
    (46.5189, 12.0094), (46.3436, 10.4881), (46.2581, 10.5808),
]


def query(q):
    data = urllib.parse.urlencode({"data": q}).encode()
    last = None
    for attempt in range(3):
        for ep in OVERPASS_ENDPOINTS:
            try:
                req = urllib.request.Request(ep, data=data,
                                             headers={"User-Agent": "Bergtouren-Map/1.0"})
                with urllib.request.urlopen(req, timeout=90) as r:   # haengende Server schnell durchfallen lassen
                    return json.loads(r.read())
            except Exception as e:  # noqa: BLE001
                last = e
                print(f"   {ep.split('/')[2]} fehlgeschlagen ({type(e).__name__}); naechster...", flush=True)
        time.sleep(8)
    raise last


def query_tiled(tmpl, rows=3, cols=4):
    """Split the Alpen-BBOX into a grid and merge elements (village-Query ist sonst zu schwer)."""
    S, W, N, E = 42.5, 3.5, 49.5, 18.5
    dlat, dlon = (N - S) / rows, (E - W) / cols
    seen, out = set(), []
    for i in range(rows):
        for j in range(cols):
            bb = f"{S+i*dlat:.3f},{W+j*dlon:.3f},{S+(i+1)*dlat:.3f},{W+(j+1)*dlon:.3f}"
            els = query(tmpl(bb)).get("elements", [])
            for e in els:
                k = (e.get("type"), e.get("id"))
                if k not in seen:
                    seen.add(k); out.append(e)
            print(f"     Kachel {i},{j}: +{len(els)} (gesamt {len(out)})")
    return out


def _places_q(bb):
    return (f'[out:json][timeout:120];'
            f'(node["place"~"^(city|town|village)$"]["name"]({bb});'
            f'node["place"="hamlet"]["name"]["ele"]({bb}););out qt;')


def _park_q(bb):
    return (f'[out:json][timeout:90];'
            f'(nwr["amenity"="parking"]["hiking"="yes"]({bb});'
            f'nwr["amenity"="parking"]["name"~"Wanderparkplatz|Wanderer",i]({bb}););out center;')


def lonlat(el):
    """Coordinates for a node (lon/lat) or a way/relation (center)."""
    if "lon" in el and "lat" in el:
        return el["lon"], el["lat"]
    c = el.get("center") or {}
    return c.get("lon"), c.get("lat")


def peaks_geojson(elements):
    feats = []
    for el in elements:
        if el.get("type") != "node":
            continue
        lon, lat = el.get("lon"), el.get("lat")
        name = (el.get("tags") or {}).get("name")
        if lon is None or not name:
            continue
        raw = str((el["tags"]).get("ele", "")).replace(",", ".").split()
        try:
            ele = float(raw[0])
        except (ValueError, IndexError):
            continue
        if ele < MIN_ELE:
            continue
        feats.append({"type": "Feature",
                      "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]},
                      "properties": {"name": name, "ele": round(ele)}})
    feats.sort(key=lambda f: -f["properties"]["ele"])
    return feats


import re

# Exclude alpine dairy farms / pastures / non-hut noise, keep real hiking huts.
ALM_RE = re.compile(r"Alm|Alpe|Alpage|Malga|\bAlp\b|Rifugio Alpe|Bergerie|forestale|camper|Stazzo",
                    re.IGNORECASE)
# Alpine-club operators → prioritised "club" category (tier 1).
CLUB_RE = re.compile(r"Alpenverein|DAV|ÖAV|OeAV|AVS|SAC|CAI|FFCAM|Naturfreunde", re.IGNORECASE)


def huts_geojson(elements):
    feats = []
    for el in elements:
        lon, lat = lonlat(el)
        tags = el.get("tags") or {}
        name = tags.get("name")
        if lon is None or not name:
            continue
        if ALM_RE.search(name):        # drop Almen/Alpe/Malga
            continue
        op = tags.get("operator", "") or ""
        # 3 tiers: club (Verband) > wild (unbewirtschaftet) > hut (sonstige bewirtschaftet)
        if CLUB_RE.search(op):
            kat = "club"
        elif tags.get("tourism") == "wilderness_hut":
            kat = "wild"
        else:
            kat = "hut"
        props = {"name": name, "kat": kat}
        if op:
            props["operator"] = op        # keep for reproducibility / DAV cross-check
        if tags.get("tourism"):
            props["tourism"] = tags["tourism"]
        raw = str(tags.get("ele", "")).replace(",", ".").split()
        if raw:
            try:
                props["ele"] = round(float(raw[0]))
            except (ValueError, IndexError):
                pass
        feats.append({"type": "Feature",
                      "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]},
                      "properties": props})
    return feats


def passes_geojson(elements):
    feats = []
    for el in elements:
        lon, lat = lonlat(el)
        tags = el.get("tags") or {}
        name = tags.get("name")
        if lon is None or not name:
            continue
        props = {"name": name, "famous": 1 if FAMOUS_PASS_RE.search(name) else 0}
        raw = str(tags.get("ele", "")).replace(",", ".").split()
        if raw:
            try:
                props["ele"] = round(float(raw[0]))
            except (ValueError, IndexError):
                pass
        feats.append({"type": "Feature",
                      "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]},
                      "properties": props})
    return feats


def places_geojson(elements):
    feats = []
    for el in elements:
        if el.get("type") != "node":
            continue
        tags = el.get("tags") or {}
        name, place = tags.get("name"), tags.get("place")
        lon, lat = el.get("lon"), el.get("lat")
        if lon is None or not name or place not in PLACE_RANK:
            continue
        ele = None
        raw = str(tags.get("ele", "")).replace(",", ".").split()
        if raw:
            try:
                ele = round(float(raw[0]))
            except (ValueError, IndexError):
                ele = None
        if place == "hamlet" and (ele is None or ele <= 1200):   # nur Bergdoerfer
            continue
        props = {"name": name, "place": place, "rank": PLACE_RANK[place]}
        if ele is not None:
            props["ele"] = ele
        pop = tags.get("population")
        if pop:
            try:
                props["pop"] = int(re.sub(r"[^\d]", "", pop))
            except ValueError:
                pass
        feats.append({"type": "Feature",
                      "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]},
                      "properties": props})
    feats.sort(key=lambda f: (-f["properties"]["rank"], -(f["properties"].get("pop") or 0)))
    return feats


def _ele_of(node):
    raw = str((node.get("tags") or {}).get("ele", "")).replace(",", ".").split()
    try:
        return float(raw[0])
    except (ValueError, IndexError):
        return None


def cableways_geojson(elements):
    """One point per cable_car/gondola line at its VALLEY station (lowest ele station)."""
    stations, ways = {}, []
    for el in elements:
        tags = el.get("tags") or {}
        if el.get("type") == "node" and tags.get("aerialway") == "station":
            stations[el["id"]] = el
        elif el.get("type") == "way" and tags.get("aerialway") in ("cable_car", "gondola"):
            ways.append(el)
    feats, seen = [], set()
    for w in ways:
        tags = w.get("tags") or {}
        st = [stations[nid] for nid in w.get("nodes", []) if nid in stations]
        if not st:
            continue
        with_ele = [n for n in st if _ele_of(n) is not None]
        valley = min(with_ele, key=_ele_of) if with_ele else st[0]
        key = (round(valley["lon"], 4), round(valley["lat"], 4))
        if key in seen:
            continue
        seen.add(key)
        name = tags.get("name") or (valley.get("tags") or {}).get("name")
        if not name:
            continue
        props = {"name": name}
        ve = _ele_of(valley)
        if ve is not None:
            props["ele"] = round(ve)
        if with_ele:
            props["ele_top"] = round(_ele_of(max(with_ele, key=_ele_of)))   # Bergstation fuer Tal->Berg
        feats.append({"type": "Feature",
                      "geometry": {"type": "Point", "coordinates": [round(valley["lon"], 5), round(valley["lat"], 5)]},
                      "properties": props})
    return feats


def cableway_lines_geojson(elements):
    """LineString je cable_car/gondola-Way (voller Verlauf via 'out geom'). Name + Endhöhen falls da."""
    feats = []
    for el in elements:
        if el.get("type") != "way":
            continue
        geom = el.get("geometry") or []
        if len(geom) < 2:
            continue
        coords = [[round(p["lon"], 5), round(p["lat"], 5)] for p in geom if "lon" in p and "lat" in p]
        if len(coords) < 2:
            continue
        tags = el.get("tags") or {}
        props = {}
        if tags.get("name"):
            props["name"] = tags["name"]
        if tags.get("aerialway"):
            props["kind"] = tags["aerialway"]
        feats.append({"type": "Feature",
                      "geometry": {"type": "LineString", "coordinates": coords},
                      "properties": props})
    return feats


def line_mask_filter(feats, buffer_deg):
    """Keep a line if ANY vertex lies inside the SOIUSA mask expanded by buffer_deg."""
    try:
        from shapely.geometry import Point, shape
        from shapely.ops import unary_union
        from shapely.prepared import prep
    except ImportError:
        print("  (shapely fehlt -> kein Maske-Clip fuer Linien)")
        return feats
    fc = json.loads((HERE / "soiusa_sts_colored.geojson").read_text(encoding="utf-8"))
    u = unary_union([shape(f["geometry"]) for f in fc["features"]])
    if buffer_deg:
        u = u.buffer(buffer_deg)
    m = prep(u)
    return [f for f in feats
            if any(m.contains(Point(xy)) for xy in f["geometry"]["coordinates"])]


def parking_points(elements):
    pts = []
    for el in elements:
        lon, lat = lonlat(el)
        if lon is None:
            continue
        pts.append((lon, lat, (el.get("tags") or {}).get("name", "")))
    return pts


def parking_country_report(pts):
    """Count Wander-parking per SOIUSA country (v1 = kein Layer, nur Report)."""
    try:
        from shapely.geometry import Point, shape
        from shapely.ops import unary_union
        from shapely.prepared import prep
    except ImportError:
        print("  (shapely fehlt -> kein Parkplatz-Report)")
        return None
    fc = json.loads((HERE / "soiusa_sts_colored.geojson").read_text(encoding="utf-8"))
    byc = {}
    for f in fc["features"]:
        byc.setdefault(f["properties"].get("country", "??"), []).append(shape(f["geometry"]))
    prepped = {c: prep(unary_union(g)) for c, g in byc.items()}
    counts = {c: 0 for c in prepped}
    outside = named = 0
    for lon, lat, nm in pts:
        p = Point(lon, lat)
        hit = next((c for c, pr in prepped.items() if pr.contains(p)), None)
        if hit:
            counts[hit] += 1
        else:
            outside += 1
        if nm:
            named += 1
    return {"counts": counts, "outside": outside, "total": len(pts), "named": named}


def alps_filter(feats):
    """Keep only features whose point lies inside the SOIUSA polygons (drop non-alpine)."""
    try:
        from shapely.geometry import Point, shape
        from shapely.ops import unary_union
        from shapely.prepared import prep
    except ImportError:
        print("  (shapely fehlt -> kein SOIUSA-Clip)")
        return feats
    fc = json.loads((HERE / "soiusa_sts_colored.geojson").read_text(encoding="utf-8"))
    union = prep(unary_union([shape(f["geometry"]) for f in fc["features"]]))
    return [f for f in feats if union.contains(Point(f["geometry"]["coordinates"]))]


def mask_filter(feats, buffer_deg):
    """Keep points inside the SOIUSA mask expanded by buffer_deg (Orte: ~5 km Talrand)."""
    try:
        from shapely.geometry import Point, shape
        from shapely.ops import unary_union
        from shapely.prepared import prep
    except ImportError:
        print("  (shapely fehlt -> kein Maske+Puffer-Clip)")
        return feats
    fc = json.loads((HERE / "soiusa_sts_colored.geojson").read_text(encoding="utf-8"))
    u = unary_union([shape(f["geometry"]) for f in fc["features"]])
    if buffer_deg:
        u = u.buffer(buffer_deg)
    m = prep(u)
    return [f for f in feats if m.contains(Point(f["geometry"]["coordinates"]))]


def save(name, feats, label):
    (HERE / name).write_text(json.dumps({"type": "FeatureCollection", "features": feats},
                                        ensure_ascii=False), encoding="utf-8")
    kb = (HERE / name).stat().st_size // 1024
    print(f"-> {name}  {len(feats)} {label}  {kb} KB")


# --anreise: nur die neue Anreise-Datenschicht ziehen (Gipfel/Huetten/Paesse unangetastet).
_ARGS = sys.argv[1:]

# W4: --cable-lines zieht NUR die Seilbahn-Linien (aerialway-Ways) und beendet danach.
if "--cable-lines" in _ARGS:
    print("Overpass: Seilbahn-LINIEN (cable_car/gondola, out geom)...")
    lf = cableway_lines_geojson(query(CABLE_LINES_Q).get("elements", []))
    before = len(lf)
    lf = line_mask_filter(lf, 0.02)   # Linie behalten, wenn ein Vertex in SOIUSA-Maske (+~2 km)
    save("soiusa_osm_cableways_lines.geojson", lf, f"Seilbahn-Linien (von {before} nach Maske-Clip)")
    sys.exit(0)

# Sessellift-EINBAU (Anreise-Folgepaket): chair_lift-Linien als EIGENE Datei (Muster --cable-lines),
# EINE Overpass-Query, out geom, gleicher Maske-Clip. Keine Stationen. Bestehende cable/gondola-Datei bleibt.
if "--chairlifts" in _ARGS:
    print("Overpass: Sessellift-LINIEN (aerialway=chair_lift, out geom)...")
    CHAIR_LINES_Q = (f'[out:json][timeout:300];'
                     f'(way["aerialway"="chair_lift"]({BBOX}););out geom;')
    lf = cableway_lines_geojson(query(CHAIR_LINES_Q).get("elements", []))
    before = len(lf)
    lf = line_mask_filter(lf, 0.02)
    save("soiusa_osm_chairlifts.geojson", lf, f"Sessellift-Linien (von {before} nach Maske-Clip)")
    sys.exit(0)

# Anreise-Workorder B: Sessellift-ZAEHL-Report — NUR zaehlen, KEIN Layer/Persist der Geometrie.
# Eine Overpass-Query (Server schonen), Clip wie die W4-Linien (line_mask_filter).
if "--count-chairlifts" in _ARGS:
    print("Overpass: Sessellifte (aerialway=chair_lift, out geom) — nur Zaehl-Report...")
    CHAIR_Q = (f'[out:json][timeout:300];'
               f'(way["aerialway"="chair_lift"]({BBOX}););out geom;')
    cl = cableway_lines_geojson(query(CHAIR_Q).get("elements", []))
    raw = len(cl)
    clipped = line_mask_filter(cl, 0.02)   # Linie behalten, wenn ein Vertex in SOIUSA-Maske (+~2 km)
    size_kb = len(json.dumps({"type": "FeatureCollection", "features": clipped},
                             ensure_ascii=False, separators=(",", ":")).encode("utf-8")) // 1024
    named = sum(1 for f in clipped if f["properties"].get("name"))
    invis = None
    try:
        from shapely.geometry import Point, shape
        from shapely.ops import unary_union
        from shapely.prepared import prep
        _fc = json.loads((HERE / "soiusa_sts_colored.geojson").read_text(encoding="utf-8"))
        _vg = [shape(f["geometry"]) for f in _fc["features"] if f["properties"].get("visited") == 1]
        if _vg:
            _vu = prep(unary_union(_vg))
            invis = sum(1 for f in clipped
                        if any(_vu.contains(Point(xy)) for xy in f["geometry"]["coordinates"]))
    except ImportError:
        print("  (shapely fehlt -> 'in besuchten Gruppen' nicht bestimmbar)")
    rep = {"raw": raw, "after_clip": len(clipped), "est_kb": size_kb,
           "named": named, "in_visited_groups": invis}
    print(f"   Sessellifte roh: {raw} · nach SOIUSA-Clip: {len(clipped)} · ~{size_kb} KB "
          f"(vgl. cable/gondola-Linien) · benannt: {named} · in besuchten Gruppen: {invis}")
    (HERE / "chairlift_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    sys.exit(0)

RUN_CORE = "--anreise" not in _ARGS
RUN_ANREISE = True

if RUN_CORE:
    out_p = HERE / "soiusa_osm_peaks.geojson"
    if out_p.exists() and len(json.loads(out_p.read_text(encoding="utf-8"))["features"]) > 1000:
        print("Gipfel vorhanden — lade + clippe auf SOIUSA...")
        pf = json.loads(out_p.read_text(encoding="utf-8"))["features"]
    else:
        print("Overpass: Gipfel (kann etwas dauern)...")
        pf = peaks_geojson(query(PEAKS_Q).get("elements", []))
    before = len(pf)
    pf = alps_filter(pf)
    lm = 0
    for f in pf:                       # hierarchy tier + landmark flag
        nm, ele = f["properties"].get("name", ""), f["properties"].get("ele", 0)
        f["properties"]["tier"] = peak_tier(nm, ele)
        if is_landmark(nm, ele):
            f["properties"]["landmark"] = 1
            lm += 1
    save("soiusa_osm_peaks.geojson", pf, f"Gipfel (von {before} nach SOIUSA-Clip, {lm} Landmarks)")
    tier01 = [f["properties"]["name"] for f in pf if f["properties"]["tier"] <= 1]
    print(f"   Tier 0/1 (Alpen-König + Länder-Höchste): {tier01}")

    print("Overpass: Huetten...")
    hf = huts_geojson(query(HUTS_Q).get("elements", []))
    before = len(hf)
    hf = alps_filter(hf)
    save("soiusa_osm_huts.geojson", hf, f"Huetten (von {before} nach SOIUSA-Clip)")

    print("Overpass: Paesse...")
    xf = passes_geojson(query(PASS_Q).get("elements", []))
    before = len(xf)
    xf = alps_filter(xf)
    for clat, clon in FAMOUS_PASS_COORDS:      # guarantee curated famous passes via nearest match
        best, bd = None, 9e9
        for f in xf:
            lo, la = f["geometry"]["coordinates"]
            d = (la - clat) ** 2 + (lo - clon) ** 2
            if d < bd:
                bd, best = d, f
        if best and bd <= 0.03 ** 2:
            best["properties"]["famous"] = 1
    fam = sum(1 for f in xf if f["properties"]["famous"])
    save("soiusa_osm_passes.geojson", xf, f"Paesse (von {before} nach Clip, {fam} famous)")

if RUN_ANREISE:
    print("Overpass: Orte (gekachelt)...")
    plf = places_geojson(query_tiled(_places_q, 3, 4))
    before = len(plf)
    plf = mask_filter(plf, 0.06)                 # SOIUSA-Maske + ~5 km Talrand-Puffer
    ha = sum(1 for f in plf if f["properties"]["place"] == "hamlet")
    save("soiusa_osm_places.geojson", plf, f"Orte (von {before} nach Maske+5km, {ha} Bergdoerfer)")

    print("Overpass: Seilbahnen (Talstationen)...")
    cbf = cableways_geojson(query(CABLE_Q).get("elements", []))
    before = len(cbf)
    cbf = alps_filter(cbf)
    save("soiusa_osm_cableways.geojson", cbf, f"Seilbahn-Talstationen cable_car/gondola (von {before} nach Clip)")

    print("Overpass: Wanderparkplaetze (v1 = nur Zaehl-Report, KEIN Layer; gekachelt)...")
    rep = parking_country_report(parking_points(query_tiled(_park_q, 3, 4)))
    if rep:
        print(f"   Parkplaetze roh: {rep['total']} (davon benannt: {rep['named']})")
        for c in sorted(rep["counts"], key=lambda k: -rep["counts"][k]):
            print(f"     {c}: {rep['counts'][c]}")
        print(f"     ausserhalb SOIUSA-Maske: {rep['outside']}")
        (HERE / "parking_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
print("Naechster Schritt: python build.py")

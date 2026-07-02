#!/usr/bin/env python3
"""Reclassify OSM huts as kat="club" using the authoritative de.wikipedia alpine-club
categories (MediaWiki API). OSM `operator` is far too sparse; the categories are complete.
Runs AFTER fetch_osm.py, edits soiusa_osm_huts.geojson in place (adds `club` property).

Match = normalized name (parentheticals stripped, diacritics-folded). Order: DAV first
(wins ties). Impersonal / keyless.
"""
import io
import json
import pathlib
import re
import sys
import unicodedata
import urllib.parse
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = pathlib.Path(__file__).parent
API = "https://de.wikipedia.org/w/api.php"
UA = "Bergtouren-Map/1.0 (https://github.com/guncanrun/alpentouren)"

CATS = [   # DAV first -> wins ties
    ("DAV",   "Kategorie:Schutzhütte des Deutschen Alpenvereins"),
    ("ÖAV",   "Kategorie:Schutzhütte des Österreichischen Alpenvereins"),
    ("AVS",   "Kategorie:Schutzhütte des Alpenvereins Südtirol"),
    ("SAC",   "Kategorie:Schutzhütte des Schweizer Alpen-Clubs"),
    ("CAI",   "Kategorie:Schutzhütte des Club Alpino Italiano"),
    ("FFCAM", "Kategorie:Schutzhütte des Club Alpin Français"),
]


def norm(s):
    s = re.sub(r"\s*\(.*?\)", "", s or "")     # drop "(Kitzbüheler Alpen)" etc.
    s = s.replace("ß", "ss")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip().lower()


def category_members(cat):
    titles, cont = [], None
    while True:
        params = {"action": "query", "format": "json", "list": "categorymembers",
                  "cmtitle": cat, "cmlimit": "500", "cmtype": "page"}
        if cont:
            params["cmcontinue"] = cont
        url = API + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        for m in data.get("query", {}).get("categorymembers", []):
            t = m["title"]
            if t.startswith("Liste "):
                continue
            titles.append(t)
        cont = data.get("continue", {}).get("cmcontinue")
        if not cont:
            break
    return titles


# Build normalized-name -> Verband (DAV first wins)
club_by_norm = {}
for verband, cat in CATS:
    members = category_members(cat)
    for t in members:
        club_by_norm.setdefault(norm(t), verband)
    print(f"{verband}: {len(members)} Kategorie-Einträge")

# Match against OSM huts
p = HERE / "soiusa_osm_huts.geojson"
fc = json.loads(p.read_text(encoding="utf-8"))
counts = {}
for f in fc["features"]:
    nn = norm(f["properties"].get("name", ""))
    v = club_by_norm.get(nn)
    if v:
        f["properties"]["kat"] = "club"
        f["properties"]["club"] = v
        counts[v] = counts.get(v, 0) + 1

# AVS (Südtirol) via coordinates — these run in OSM under CAI/Italian names, so
# name-matching misses them. Nearest OSM hut within ~250 m gets kat=club, club=AVS.
AVS_COORDS = [
    ("Brixner Hütte", 46.9128, 11.6206), ("Dreischusterhütte", 46.6745, 12.2973),
    ("Friedensbiwak", 46.5683, 12.0288), ("Friedl-Mutschlechner-Haus", 46.8042, 12.3787),
    ("Guido-Lammer-Biwak", 46.7262, 11.0684), ("Günther-Messner-Hochferner-Biwak", 46.9862, 11.7054),
    ("Hochfeilerhütte", 46.9639, 11.7003), ("Josef-Pixner-Biwak", 46.8207, 11.1000),
    ("Marteller Hütte", 46.4696, 10.6732), ("Meraner Hütte", 46.6834, 11.2818),
    ("Obere Laaser Alm", 46.5708, 10.6800), ("Oberetteshütte", 46.7648, 10.7111),
    ("Radlseehütte", 46.7078, 11.5803), ("Rieserfernerhütte", 46.8900, 12.0794),
    ("Schlernbödelehütte", 46.5221, 11.5837), ("Sesvennahütte", 46.7346, 10.4354),
    ("Sterzinger Hütte", 46.9198, 11.5717), ("Tablander Warter", 46.5859, 10.9881),
    ("Tiefrastenhütte", 46.8763, 11.7817), ("Walter-Brenninger-Biwak", 46.9387, 11.6955),
]
avs_hits = 0
for _name, clat, clon in AVS_COORDS:
    best, bd = None, 9e9
    for f in fc["features"]:
        lo, la = f["geometry"]["coordinates"]
        d = (la - clat) ** 2 + (lo - clon) ** 2
        if d < bd:
            bd, best = d, f
    if best and bd <= 0.003 ** 2:      # ~250-330 m
        best["properties"]["kat"] = "club"
        best["properties"]["club"] = "AVS"
        avs_hits += 1
print(f"AVS Koordinaten-Match: {avs_hits}/{len(AVS_COORDS)}")

total_club = sum(1 for f in fc["features"] if f["properties"].get("kat") == "club")
p.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
print(f"\nNamens-Match je Verband: {dict(sorted(counts.items()))}")
print(f"-> soiusa_osm_huts.geojson  kat=club gesamt: {total_club} / {len(fc['features'])}")

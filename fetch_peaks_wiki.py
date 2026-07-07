#!/usr/bin/env python3
"""Gipfel-Enrichment (N3): Wikidata/Wikipedia-Daten fuer Gipfel-Popups.

Zielmenge (aus soiusa_osm_peaks.geojson):
  (a) die hoechsten Gipfel je SOIUSA-Gruppe (soiusa_group_peaks.json, Koordinaten-Match)
  (b) alle OSM-Gipfel > 3000 m sowie die Landmark-Gipfel

Quelle: Wikidata (Box-Queries ueber den Alpenraum, P2044 Hoehe, P18 Bild,
de.wikipedia-Sitelink) + Commons-API fuer Bild-Attributionen (CC-Pflicht).
Matching KONSERVATIV ueber Koordinaten-Naehe UND Namensgleichheit (normalisiert)
— nie ueber Namens-Strings allein (Dubletten wie 2x Krottenkopf!).

Output: soiusa_peaks_wiki.json (getrackt, NEUTRAL — Muster soiusa_huts_wiki.json),
Key = "lon,lat" (5 Dezimalen, identisch zu den OSM-Feature-Koordinaten).
Budget-Gate: > 400 KB kompakt -> nur Teilmenge (a) + Landmarks schreiben.
"""
import io
import json
import math
import pathlib
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = pathlib.Path(__file__).parent
UA = {"User-Agent": "Bergtouren-Map/1.0 (https://github.com/guncanrun/alpentouren)"}
WDQS = "https://query.wikidata.org/sparql"
COMMONS = "https://commons.wikimedia.org/w/api.php"
BUDGET = 400 * 1024


def _get(url, timeout=90):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def norm(s):
    s = str(s or "").lower().replace("ß", "ss")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", s)


def name_variants(osm_name):
    """OSM-Doppelnamen ("Mont Blanc / Monte Bianco") -> Einzelvarianten + Gesamtname."""
    parts = [p.strip() for p in str(osm_name).split("/") if p.strip()]
    out = {norm(osm_name)}
    for p in parts:
        out.add(norm(p))
        out.add(norm(re.sub(r"\([^)]*\)", "", p)))   # Klammerzusaetze weg
    return {v for v in out if v}


def hav_m(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[1], a[0], b[1], b[0]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 12742000 * math.asin(math.sqrt(h))


# ── 1. Zielgipfel bestimmen ───────────────────────────────────────────────────
peaks = json.loads((HERE / "soiusa_osm_peaks.geojson").read_text(encoding="utf-8"))["features"]
gp = json.loads((HERE / "soiusa_group_peaks.json").read_text(encoding="utf-8"))

by_coord = {}
for f in peaks:
    c = f["geometry"]["coordinates"]
    by_coord[f"{c[0]:.5f},{c[1]:.5f}"] = f

targets = {}   # key -> feature
n_a = 0
for sts, c in gp.items():
    k = f"{c[0]:.5f},{c[1]:.5f}"
    if k in by_coord:
        targets[k] = by_coord[k]
        n_a += 1
    else:
        print(f"  WARN Gruppen-Gipfel {sts} {k} nicht im OSM-Datensatz")
for f in peaks:
    p = f["properties"]
    if (p.get("ele") or 0) > 3000 or p.get("landmark") == 1:
        c = f["geometry"]["coordinates"]
        targets[f"{c[0]:.5f},{c[1]:.5f}"] = f
print(f"Ziele: {len(targets)} Gipfel (Gruppen-Hoechste {n_a} · >3000m/Landmark inkl. Ueberlapp)")

# ── 2. Wikidata: Box-Queries ueber den Alpenraum (Split bei Timeout) ──────────
lons = [f["geometry"]["coordinates"][0] for f in targets.values()]
lats = [f["geometry"]["coordinates"][1] for f in targets.values()]
BBOX = (min(lons) - 0.05, min(lats) - 0.05, max(lons) + 0.05, max(lats) + 0.05)

Q = """SELECT ?item ?coord ?ele ?img ?art ?lbl WHERE {
  SERVICE wikibase:box {
    ?item wdt:P625 ?coord .
    bd:serviceParam wikibase:cornerSouthWest "Point(%f %f)"^^geo:wktLiteral .
    bd:serviceParam wikibase:cornerNorthEast "Point(%f %f)"^^geo:wktLiteral .
  }
  ?item wdt:P2044 ?ele .
  OPTIONAL { ?item wdt:P18 ?img . }
  OPTIONAL { ?art schema:about ?item ; schema:isPartOf <https://de.wikipedia.org/> . }
  OPTIONAL { ?item rdfs:label ?lbl FILTER(LANG(?lbl) IN ("de","en")) }
}"""

items = {}   # qid -> {lon,lat,ele,img,art,names:set}


def wd_box(w, s, e, n, depth=0):
    q = Q % (w, s, e, n)
    url = WDQS + "?" + urllib.parse.urlencode({"query": q, "format": "json"})
    try:
        data = json.loads(_get(url))
    except Exception as ex:  # noqa: BLE001 — Timeout/429 -> Viertel-Split
        if depth >= 4:
            print(f"  ERR Tile ({w:.2f},{s:.2f})-({e:.2f},{n:.2f}): {type(ex).__name__} (max depth)")
            return
        mw, mn = (w + e) / 2, (s + n) / 2
        time.sleep(2)
        for bb in ((w, s, mw, mn), (mw, s, e, mn), (w, mn, mw, n), (mw, mn, e, n)):
            wd_box(*bb, depth=depth + 1)
        return
    rows = data["results"]["bindings"]
    for r in rows:
        qid = r["item"]["value"].rsplit("/", 1)[-1]
        it = items.setdefault(qid, {"names": set()})
        m = re.match(r"Point\(([-0-9.]+) ([-0-9.]+)\)", r["coord"]["value"])
        if m:
            it["lon"], it["lat"] = float(m.group(1)), float(m.group(2))
        try:
            it["ele"] = float(r["ele"]["value"])
        except (KeyError, ValueError):
            pass
        if "img" in r:
            # P18 kommt als Special:FilePath-URL mit BEREITS percent-encodiertem
            # Basename -> erst unquoten, sonst Doppel-Encoding im Thumb-Link.
            it["img"] = urllib.parse.unquote(r["img"]["value"].rsplit("/", 1)[-1])
        if "art" in r:
            it["art"] = r["art"]["value"]
            it["names"].add(norm(urllib.parse.unquote(r["art"]["value"].rsplit("/", 1)[-1]).replace("_", " ")))
        if "lbl" in r:
            it["names"].add(norm(r["lbl"]["value"]))
    time.sleep(0.5)


TILE = 1.0
w = BBOX[0]
n_tiles = 0
while w < BBOX[2]:
    s = BBOX[1]
    while s < BBOX[3]:
        wd_box(w, s, min(w + TILE, BBOX[2]), min(s + TILE, BBOX[3]))
        n_tiles += 1
        s += TILE
    w += TILE
print(f"Wikidata: {len(items)} Kandidaten-Items aus {n_tiles} Tiles (+Splits)")

# ── 3. Matching: Koordinaten-Naehe UND Namensgleichheit ───────────────────────
# Grid-Index (~0.02 Grad) fuer Kandidaten in der Nachbarschaft.
grid = {}
for qid, it in items.items():
    if "lon" not in it:
        continue
    grid.setdefault((int(it["lon"] / 0.02), int(it["lat"] / 0.02)), []).append(qid)


def candidates(lon, lat):
    gx, gy = int(lon / 0.02), int(lat / 0.02)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            yield from grid.get((gx + dx, gy + dy), [])


matched = {}    # key -> (feature, item)
for k, f in targets.items():
    lon, lat = f["geometry"]["coordinates"][:2]
    variants = name_variants(f["properties"].get("name"))
    best, best_d = None, 1e9
    for qid in candidates(lon, lat):
        it = items[qid]
        d = hav_m((lon, lat), (it["lon"], it["lat"]))
        if d > 2000 or d >= best_d:
            continue
        if variants & it["names"]:
            best, best_d = qid, d
    if best:
        matched[k] = (f, items[best])
print(f"Matching: {len(matched)}/{len(targets)} Gipfel mit Wikidata-Item (Name+Koordinate)")

# ── 4. Commons: Bild-Attributionen (Batch a 50) ───────────────────────────────
files = sorted({it["img"] for _, it in matched.values()
                if it.get("img", "").lower().endswith((".jpg", ".jpeg", ".png"))})
attr = {}
for i in range(0, len(files), 50):
    batch = files[i:i + 50]
    params = {"action": "query", "format": "json",
              "titles": "|".join("File:" + b for b in batch),
              "prop": "imageinfo", "iiprop": "extmetadata"}
    try:
        data = json.loads(_get(COMMONS + "?" + urllib.parse.urlencode(params)))
        for pg in data.get("query", {}).get("pages", {}).values():
            title = pg.get("title", "")[5:]
            ii = (pg.get("imageinfo") or [{}])[0].get("extmetadata", {})
            artist = re.sub(r"<[^>]+>", "", ii.get("Artist", {}).get("value", "")).strip()
            artist = re.sub(r"\s+", " ", artist)[:70] or "Wikimedia Commons"
            lic = ii.get("LicenseShortName", {}).get("value", "").strip()
            attr[title.replace(" ", "_")] = (artist + (" / " + lic if lic else "")).strip()
    except Exception as ex:  # noqa: BLE001
        print(f"  WARN Commons-Batch {i}: {type(ex).__name__}")
    time.sleep(0.4)
print(f"Commons: {len(attr)} Bild-Attributionen")


def thumb_url(fname, width=330):
    # Special:FilePath (stabiler MediaWiki-Redirect auf das Thumb) statt des langen
    # upload.wikimedia-Thumb-Pfads: ~halbe URL-Laenge -> Standalone-Budget (13,9 MB).
    return ("https://commons.wikimedia.org/wiki/Special:FilePath/"
            + urllib.parse.quote(fname.replace(" ", "_")) + f"?width={width}")


# ── 5. Eintraege bauen + Budget-Gate ──────────────────────────────────────────
def build_entry(f, it):
    e = {"name": f["properties"].get("name")}
    if it.get("art"):
        e["wiki"] = it["art"]
    if it.get("ele") is not None:
        e["ele_wd"] = int(round(it["ele"]))
    fn = it.get("img", "")
    if fn.lower().endswith((".jpg", ".jpeg", ".png")):
        key = fn.replace(" ", "_")
        if key in attr:
            e["img"] = thumb_url(fn)
            e["img_attr"] = attr[key]
    return e if ("wiki" in e or "img" in e) else None


gp_keys = {f"{c[0]:.5f},{c[1]:.5f}" for c in gp.values()}
gipfel, dev = {}, []
for k, (f, it) in sorted(matched.items()):
    e = build_entry(f, it)
    if not e:
        continue
    gipfel[k] = e
    ele_osm = f["properties"].get("ele")
    if ele_osm and e.get("ele_wd") and abs(ele_osm - e["ele_wd"]) > 25:
        dev.append((e["name"], ele_osm, e["ele_wd"]))

meta = {"quelle": "Wikidata (P2044/P18/de-Sitelink) + Wikimedia Commons",
        "lizenz": "Text CC BY-SA; Bilder Wikimedia Commons, Attribution je Bild",
        "hinweis": "Key = 'lon,lat' (5 Dezimalen) der OSM-Gipfel-Koordinate",
        "stand": time.strftime("%Y-%m-%d")}


def dump(d):
    return json.dumps({"meta": meta, "gipfel": d}, ensure_ascii=False, separators=(",", ":"))


out = dump(gipfel)
if len(out.encode("utf-8")) > BUDGET:
    subset = {k: v for k, v in gipfel.items()
              if k in gp_keys or (by_coord[k]["properties"].get("landmark") == 1)}
    print(f"Budget-Gate: {len(out)//1024} KB > 400 KB -> nur Gruppen-Hoechste+Landmarks "
          f"({len(subset)} von {len(gipfel)} Eintraegen)")
    gipfel, out = subset, dump(subset)

(HERE / "soiusa_peaks_wiki.json").write_text(out, encoding="utf-8")
n_img = sum(1 for e in gipfel.values() if "img" in e)
n_wiki = sum(1 for e in gipfel.values() if "wiki" in e)
print(f"-> soiusa_peaks_wiki.json  {len(gipfel)} Gipfel · {n_wiki} wiki · {n_img} img · "
      f"{len(out.encode('utf-8'))//1024} KB")
print(f"Hoehen-Abweichungen OSM vs. Wikidata > 25 m: {len(dev)}")
for nm, eo, ew in dev[:20]:
    print(f"   {nm}: OSM {eo} vs. WD {ew}")

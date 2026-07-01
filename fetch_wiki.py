#!/usr/bin/env python3
"""Scrape höchster Berg + Höhe for the UNVISITED SOIUSA groups from de.wikipedia
(Infobox Gebirge), keyed by name_de. Merges into soiusa_wiki.json WITHOUT touching
the 12 hand-curated visited entries. Draft — needs Cowork verification.
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
API = "https://de.wikipedia.org/w/api.php"


def wikitext(title):
    params = {"action": "query", "prop": "revisions", "rvprop": "content",
              "rvslots": "main", "format": "json", "redirects": "1", "titles": title}
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "User-Agent": "Bergtouren-Map/1.0 (https://github.com/guncanrun/alpentouren)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    for pid, pg in data.get("query", {}).get("pages", {}).items():
        if pid == "-1":
            return None
        revs = pg.get("revisions")
        if revs:
            return revs[0]["slots"]["main"]["*"]
    return None


def param(text, names):
    for n in names:
        m = re.search(r"\|\s*" + n + r"\s*=\s*([^\n]+)", text, re.IGNORECASE)
        if m and m.group(1).strip():
            return m.group(1).strip()
    return None


def clean_link(s):
    if not s:
        return ""
    m = re.findall(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", s)
    if m:
        return m[0].strip()
    return re.sub(r"<[^>]+>|\{\{[^}]*\}\}", "", s).strip()


def parse_height(s):
    if not s:
        return None
    s = s.replace(".", "").replace(" ", "").replace("\xa0", " ")
    m = re.search(r"(\d{3,5})", s)
    return int(m.group(1)) if m else None


wp = HERE / "soiusa_wiki.json"
wiki = json.loads(wp.read_text(encoding="utf-8"))
existing = wiki.setdefault("gruppen", {})

# OSM peaks name->max ele, to resolve heights (Infobox Gebirgsgruppe has no HÖHE field)
osm_ele = {}
try:
    op = json.loads((HERE / "soiusa_osm_peaks.geojson").read_text(encoding="utf-8"))
    for f in op["features"]:
        nm, el = f["properties"].get("name"), f["properties"].get("ele")
        if nm and el and el > osm_ele.get(nm, 0):
            osm_ele[nm] = el
except Exception:  # noqa: BLE001
    pass

fc = json.loads((HERE / "soiusa_sts_colored.geojson").read_text(encoding="utf-8"))
targets = []
for f in fc["features"]:
    p = f["properties"]
    sts = p.get("STS", "")
    if p.get("visited") == 1 or sts in existing:
        continue
    targets.append((sts, p.get("name_de") or sts, p.get("settore", ""), p.get("country", "")))

print(f"{len(targets)} unbesuchte Gruppen zu scrapen...")
hits = 0
for i, (sts, name_de, settore, country) in enumerate(targets):
    text = None
    try:
        text = wikitext(name_de)
    except Exception as e:  # noqa: BLE001
        print(f"  ERR {name_de}: {type(e).__name__}")
    page_exists = text is not None
    entry = {
        "name_de": name_de,
        "land": [country] if country else [],
        "region_kanton": [],
        "hoechster_berg": "",
        "hoehe_m": None,
        # only link when the article actually exists — no dead links in public map
        "wiki_url": ("https://de.wikipedia.org/wiki/" + urllib.parse.quote(name_de.replace(" ", "_")))
                    if page_exists else "",
        "bild_url": "",
        "bild_attr": "",
    }
    if text:
        berg = clean_link(param(text, ["HÖCHSTER GIPFEL", "HÖCHSTER BERG"]))
        hoehe = parse_height(param(text, ["HÖHE"]))
        if berg and not hoehe:
            hoehe = osm_ele.get(berg)   # resolve height from OSM peaks by name
        if berg:
            entry["hoechster_berg"] = berg
        if hoehe:
            entry["hoehe_m"] = hoehe
        if berg or hoehe:
            hits += 1
    existing[sts] = entry
    if (i + 1) % 20 == 0:
        print(f"  {i+1}/{len(targets)}  (mit Berg/Höhe: {hits})")
    time.sleep(0.3)

wiki["meta"]["status"] = ("Entwurf — 12 besuchte handkuratiert; unbesuchte teils automatisch "
                          "aus de.wikipedia (Infobox Gebirge). Cowork-Verifikation ausstehend.")
wp.write_text(json.dumps(wiki, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"-> soiusa_wiki.json  {len(existing)} Gruppen gesamt · {hits}/{len(targets)} unbesuchte mit Berg/Höhe")

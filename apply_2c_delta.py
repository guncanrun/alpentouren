#!/usr/bin/env python3
"""Merge the Cowork 2c-Delta (12 verified visited profiles + Wikimedia images) into
soiusa_wiki.json. Also applies the confirmed Ortler height fix. Impersonal / public-safe.
Source: _cowork_specs/HANDOVER_2c_Delta_12besuchte.md
"""
import json
import pathlib
import urllib.parse

HERE = pathlib.Path(__file__).parent
THUMB = "https://upload.wikimedia.org/wikipedia/commons/thumb/"

# (STS-Key, hashA, hashAB, Commons-Dateiname, Autor, Lizenz)
DELTA = [
    ("Alpi di Berchtesgaden", "0", "07", "Hochkoenig.jpg", "Aconcagua", "CC BY-SA 3.0"),
    ("Alpi Venoste (Ötztaler Alpen)", "6", "6b", "Wildspitzefromtiefenbachkogel.JPG", "Pirmin Olde Weghuis", "CC BY-SA 3.0"),
    ("Monti delle Lechquellen", "e", "ed", "RoteWand2.jpg", "Bernhard Mäser", "CC BY-SA 3.0"),
    ("Alpi del Monte Bianco", "b", "b1", "MontBlancFromENE.jpg", "Cactus26", "CC BY-SA 3.0"),
    ("Monti del Kaiser", "7", "77", "Ellmauer_Halt2_HQ.jpg", "Luidger", "CC BY-SA 3.0"),
    ("Alpi del Silvretta, del Samnaun e del Verwall", "a", "ad", "Piz_linard_von_Nordosten.jpg", "Stefan.straub", "CC BY-SA 4.0"),
    ("Alpi Carniche", "5", "59", "HoheWarte_KellerspitzeWest_Karnische.jpg", "Herzi Pinki", "CC BY 2.5"),
    ("Rätikon", "d", "d9", "Schesaplana_von_der_Mannheimer_Hütte.jpg", "Jörg Braukmann", "CC BY-SA 4.0"),
    ("Dolomiti di Gardena e di Fassa", "0", "06", "Marmolata,_3343m.jpg", "2015 Michael 2015", "CC BY-SA 4.0"),
    ("Prealpi Gardesane", "8", "89", "Monte_Cadria.jpg", "Niccolò Caranti", "CC BY-SA 4.0"),
    ("Alpi dello Stubai", "0", "01", "Zuckerhütl.jpg", "Jörg Braukmann", "CC BY-SA 4.0"),
    ("Monti del Dachstein", "b", "b4", "Ramsau_am_Dachstein_-_Dachsteinsüdwand_(c).JPG", "C.Stadler/Bwag", "CC BY-SA 4.0"),
]


def thumb_url(a, ab, fname):
    enc = urllib.parse.quote(fname, safe="")   # ü,(,),comma → %XX ; keeps . and _
    return f"{THUMB}{a}/{ab}/{enc}/500px-{enc}"


wp = HERE / "soiusa_wiki.json"
wiki = json.loads(wp.read_text(encoding="utf-8"))
g = wiki["gruppen"]

missing = []
for key, a, ab, fname, autor, lizenz in DELTA:
    if key not in g:
        missing.append(key)
        continue
    g[key]["bild_url"] = thumb_url(a, ab, fname)
    g[key]["bild_attr"] = f"Foto: {autor} / {lizenz} (Wikimedia Commons)"

# Textkorrektur + bestätigter Höhenfix
if "Dolomiti di Gardena e di Fassa" in g:
    g["Dolomiti di Gardena e di Fassa"]["wiki_url"] = "https://de.wikipedia.org/wiki/Marmolata"
if "Alpi dell'Ortles" in g:
    g["Alpi dell'Ortles"]["hoehe_m"] = 3905

wiki["meta"]["status"] = ("Entwurf — 12 besuchte Cowork-verifiziert inkl. Bilder; "
                          "unbesuchte teils automatisch (de.wikipedia + OSM), "
                          "Cowork-Verifikation ausstehend.")
wp.write_text(json.dumps(wiki, ensure_ascii=False, indent=2), encoding="utf-8")

print(f"12-Delta gemerged. Fehlende Keys: {missing or 'keine'}")
print("Bild-URLs zur Kontrolle:")
for key, a, ab, fname, *_ in DELTA:
    print(" ", thumb_url(a, ab, fname))

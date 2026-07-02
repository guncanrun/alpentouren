#!/usr/bin/env python3
"""Merge remaining unvisited-group profiles (höchster Berg + Höhe) into soiusa_wiki.json.
Source: _cowork_specs/HANDOVER_RestSteckbriefe_Landmarks_Paesse.md §1 (a verified, b curated).
"""
import json
import pathlib

HERE = pathlib.Path(__file__).parent

DELTA = {
    # a) Wikidata-verified
    "Prealpi dello Chablais": ("Dents du Midi", 3257),
    "Alpi Pusteresi (Defereggen Alpen)": ("Hochgall", 3436),
    "Tauri di Wölz e di Rottenmann": ("Rettlkirchspitze", 2475),
    "Dolomiti di Fiemme": ("Cima di Cece", 2754),
    "Prealpi di Vaud e Friburgo": ("Vanil Noir", 2389),
    "Prealpi Orientali della Bassa Austria": ("Ötscher", 1893),
    "Alpi di Lanzo e dell'Alta Moriana": ("Uia di Ciamarella", 3676),
    "Alpi del Moncenisio": ("Pointe de Ronce", 3612),
    "Prealpi Bresciane": ("Cornone di Blumone", 2843),
    # b) curated / well-known values
    "Alpi del Weisshorn e del Cervino": ("Weisshorn", 4506),
    "Alpi della Grande Sassière e del Rutor": ("Grande Sassière", 3747),
    "Alpi delle Grandes Rousses e Aiguilles d'Arves": ("Pic Bayle", 3465),
    "Alpi del Monginevro": ("Chaberton", 3131),
    "Massiccio del Taillefer": ("Le Taillefer", 2857),
    "Catena delle Aiguilles Rouges": ("Aiguille du Belvédère", 2965),
    "Prealpi Bergamasche": ("Pizzo Arera", 2512),
    "Prealpi dei Bornes": ("Pointe Percée", 2750),
    "Prealpi del Giffre": ("Mont Buet", 3096),
    "Alpi del Wallgau": ("Krottenkopf", 2086),
}

wp = HERE / "soiusa_wiki.json"
wiki = json.loads(wp.read_text(encoding="utf-8"))
g = wiki["gruppen"]

missing, done = [], 0
for key, (berg, hoehe) in DELTA.items():
    if key not in g:
        missing.append(key)
        continue
    g[key]["hoechster_berg"] = berg
    g[key]["hoehe_m"] = hoehe
    done += 1

wp.write_text(json.dumps(wiki, ensure_ascii=False, indent=2), encoding="utf-8")
filled = sum(1 for v in g.values() if v.get("hoehe_m"))
print(f"{done} Rest-Steckbriefe eingetragen. Fehlend: {missing or 'keine'}")
print(f"Gruppen mit Höhe gesamt: {filled} / {len(g)}")

#!/usr/bin/env python3
"""Merge Cowork's verified höchster Berg + Höhe for unvisited SOIUSA groups into
soiusa_wiki.json (Wikidata-verified P610/P2044). Overrides prior auto-scraped values.
Source: _cowork_specs/HANDOVER_2c_Delta_unbesucht.md
"""
import json
import pathlib

HERE = pathlib.Path(__file__).parent

# STS-Key : (hoechster_berg, hoehe_m)
DELTA = {
    "Alpi Marittime": ("Monte Argentera", 3297),
    "Alpi Orobie": ("Pizzo di Coca", 3052),
    "Alpi Sarentine (Sarntaler Alpen)": ("Hirzer", 2781),
    "Alpi Scistose Salisburghesi": ("Hundstein", 2117),
    "Alpi del Chiemgau": ("Sonntagshorn", 1961),
    "Alpi del Mangfall": ("Rotwand", 1884),
    "Alpi del Gran Paradiso": ("Gran Paradiso", 4061),
    "Alpi del Grand Combin": ("Grand Combin", 4309),
    "Alpi del Marguareis": ("Punta Marguareis", 2651),
    "Alpi del Mischabel e del Weissmies": ("Dom", 4546),
    "Alpi del Monte Leone e del San Gottardo": ("Monte Leone", 3553),
    "Alpi del Monte Rosa": ("Dufourspitze", 4634),
    "Alpi del Monviso": ("Monte Viso", 3841),
    "Alpi dell'Adamello e della Presanella": ("Presanella", 3556),
    "Alpi dell'Adula": ("Rheinwaldhorn", 3402),
    "Alpi dell'Algovia": ("Großer Krottenkopf", 2656),
    "Alpi dell'Ammergau": ("Daniel", 2342),
    "Alpi dell'Ennstal": ("Hochtor", 2369),
    "Alpi dell'Ybbstal": ("Hochstadl", 1919),
    "Alpi della Gurktal": ("Eisenhut", 2441),
    "Alpi della Val Müstair": ("Piz Sesvenna", 3204),
    "Alpi della Val di Non": ("Laugenspitze", 2434),
    "Alpi della Vanoise e del Grand Arc": ("Grande Casse", 3855),
    "Alpi della Zillertal": ("Hochfeiler", 3509),
    "Alpi di Kitzbühel": ("Kreuzjoch", 2558),
    "Alpi di Livigno": ("Cima de' Piazzi", 3439),
    "Alpi di Provenza": ("Tête de l'Estrop", 2961),
    "Alpi di Vaud": ("Les Diablerets", 3216),
    "Alti Tauri (Hohe Tauern)": ("Großglockner", 3798),
    "Caravanche": ("Hochstuhl", 2237),
    "Catena di Belledonne": ("Grand pic de Belledonne", 2977),
    "Dolomiti Feltrine e delle Pale di San Martino": ("Cima di Vezzana", 3192),
    "Dolomiti di Sesto, di Braies e d'Ampezzo": ("Dreischusterspitze", 3145),
    "Dolomiti di Zoldo": ("Monte Pelmo", 3168),
    "Kreuzeckgruppe": ("Polinik", 2784),
    "Monti di Mieming e del Wetterstein": ("Zugspitze", 2962),
    "Prealpi Appenzellesi e Sangallesi": ("Säntis", 2501),
    "Prealpi dei Bauges": ("Arcalod", 2210),
    "Prealpi del Devoluy": ("Obiou", 2790),
    "Prealpi del Vercors": ("Grand Veymont", 2341),
    "Prealpi della Chartreuse": ("Chamechaude", 2082),
    "Prealpi di Bregenz": ("Glatthorn", 2134),
    # 6 markierte Hoch-Gruppen (Cowork-Werte)
    "Alpi del Weisshorn e del Cervino": ("Weisshorn", 4506),
    "Alpi della Grande Sassière e del Rutor": ("Grande Sassière", 3747),
    "Alpi delle Grandes Rousses e Aiguilles d'Arves": ("Pic Bayle", 3465),
    "Prealpi dello Chablais": ("Haute Cime (Dents du Midi)", 3257),
    "Catena delle Aiguilles Rouges": ("Aiguille du Belvédère", 2965),
    "Massiccio del Taillefer": ("Le Taillefer", 2857),
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

wiki["meta"]["status"] = ("Entwurf — 12 besuchte + 48 unbesuchte Cowork/Wikidata-verifiziert; "
                          "restliche Voralpen/obskure Gruppen offen (Cowork-Verifikation).")
wp.write_text(json.dumps(wiki, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"{done} unbesuchte Höhen eingetragen. Fehlende Keys: {missing or 'keine'}")

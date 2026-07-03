#!/usr/bin/env python3
"""Kuratiertes Delta der 21 leeren SOIUSA-Steckbriefe (Cowork-Recherche) in
soiusa_wiki.json einpflegen — plus eine Bestandskorrektur.
Quelle/Regeln: _cowork_specs/HANDOVER_Delta_21_Steckbriefe.md
Regel wiki_url: de-Artikel des GIPFELS falls vorhanden, sonst it/fr/sl;
kein Artikel -> leer. Erwartung danach: 0 leere Steckbriefe.
"""
import json
import pathlib

HERE = pathlib.Path(__file__).parent

# STS-Key : (hoechster_berg, hoehe_m, wiki_url)  — "" wiki_url = kein Artikel
DELTA = {
    "Alpi Biellesi e Cusiane":          ("Monte Mars", 2600, "https://it.wikipedia.org/wiki/Monte_Mars"),
    "Alpi Nord-orientali di Stiria":    ("Hochschwab", 2277, "https://de.wikipedia.org/wiki/Hochschwab"),
    "Alpi del Beaufortain":             ("Roignais", 2995, "https://it.wikipedia.org/wiki/Roignais"),
    "Massiccio del Champsaur":          ("Vieux Chaillol", 3163, "https://it.wikipedia.org/wiki/Vieux_Chaillol"),
    "Massiccio dell'Embrunais":         ("Tête de Soulaure", 3242, "https://it.wikipedia.org/wiki/Tête_de_Soulaure"),
    "Monti orientali di Gap":           ("Pointe de la Diablée", 2928, "https://it.wikipedia.org/wiki/Pointe_de_la_Diablée"),
    "Prealpi Giulie":                   ("Monte Plauris", 1958, "https://it.wikipedia.org/wiki/Monte_Plauris"),
    "Prealpi Liguri":                   ("Monte Armetta", 1739, "https://it.wikipedia.org/wiki/Monte_Armetta"),
    "Prealpi Slovene nord-orientali":   ("Črni vrh (Schwarzkogel)", 1543, "https://de.wikipedia.org/wiki/Črni_Vrh"),
    "Prealpi Slovene occidentali":      ("Porezen", 1630, "https://it.wikipedia.org/wiki/Porezen"),
    "Prealpi Slovene orientali":        ("Kum", 1220, "https://sl.wikipedia.org/wiki/Kum"),
    "Prealpi Svittesi e Urane":         ("Schächentaler Windgällen", 2764, "https://it.wikipedia.org/wiki/Schächentaler_Windgällen"),
    "Prealpi centrali di Stiria":       ("Stuhleck", 1782, "https://de.wikipedia.org/wiki/Stuhleck"),
    "Prealpi del Diois":                ("Montagne de Belle-Motte", 1952, ""),
    "Prealpi delle Baronnies":          ("Montagne de Chamouse", 1532, ""),
    "Prealpi di Grasse":                ("Sommet de la Bernarde", 1941, "https://it.wikipedia.org/wiki/Sommet_de_la_Bernarde"),
    "Prealpi di Nizza":                 ("Cime de Roccasiera", 1501, "https://it.wikipedia.org/wiki/Cime_de_Roccasiera"),
    "Prealpi di Vaucluse":              ("Mont Ventoux", 1912, "https://de.wikipedia.org/wiki/Mont_Ventoux"),
    "Prealpi occidentali di Gap":       ("Montagne de Céüse", 2016, "https://it.wikipedia.org/wiki/Montagne_de_Céüse"),
    "Prealpi orientali di Stiria":      ("Hochwechsel", 1743, "https://de.wikipedia.org/wiki/Wechsel_(Berg)"),
    "Prealpi sud-occidentali di Stiria": ("Großer Speikkogel", 2140, "https://de.wikipedia.org/wiki/Großer_Speikkogel"),
}

# Bestandskorrektur: STS-Key : (hoehe_m_alt, hoehe_m_neu, wiki_url_neu)
# Prealpi vicentine: Cima Dodici 2446 -> 2336 m (it/SOIUSA-Kanon). Die 2446er ist
# eine ANDERE Cima Dodici (Vallaccia/Dolomiten).
KORREKTUR = {
    "Prealpi vicentine": ("Cima Dodici", 2446, 2336, "https://de.wikipedia.org/wiki/Cima_Dodici"),
}

wp = HERE / "soiusa_wiki.json"
wiki = json.loads(wp.read_text(encoding="utf-8"))
g = wiki["gruppen"]

missing, done = [], 0
for key, (berg, hoehe, url) in DELTA.items():
    if key not in g:
        missing.append(key)
        continue
    g[key]["hoechster_berg"] = berg
    g[key]["hoehe_m"] = hoehe
    g[key]["wiki_url"] = url
    done += 1

korr = []
for key, (berg, alt, neu, url) in KORREKTUR.items():
    if key not in g:
        missing.append(key)
        continue
    before = g[key].get("hoehe_m")
    g[key]["hoechster_berg"] = berg
    g[key]["hoehe_m"] = neu
    g[key]["wiki_url"] = url
    korr.append(f"{key}: {before} -> {neu}")

# Verifikation: keine leeren Steckbriefe mehr.
empty = [k for k, v in g.items() if not v.get("hoechster_berg") or not v.get("hoehe_m")]

wp.write_text(json.dumps(wiki, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"{done}/21 Steckbriefe gefüllt. Korrekturen: {korr or 'keine'}")
print(f"Fehlende Keys: {missing or 'keine'}")
print(f"Leere Steckbriefe danach: {len(empty)}" + (f" -> {empty}" if empty else " (OK)"))

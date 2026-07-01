# Alpentouren — interaktive 3D-Karte

Eine statische, **keyless** 3D-Webkarte der Alpen auf Basis von **MapLibre GL JS**.
Sie zeigt die 131 SOIUSA-Untergruppen (Sottosezioni) als flaches, nach den fünf
**Grandi Settori** eingefärbtes Mosaik über einem Satelliten-Relief; besuchte Gruppen
sind orange hervorgehoben. Klick auf eine Fläche öffnet Namen und Details.

**Live:** https://guncanrun.github.io/alpentouren/

## Features
- 3D-Terrain (kippbar/rotierbar) über offenem DEM, ohne API-Key
- 131 SOIUSA-Sottosezioni als Flächen-Mosaik, eingefärbt nach den 5 SOIUSA-Settori
- Deutschsprachige Gruppennamen (IT-SOIUSA → DE-Lookup)
- Zuschaltbare Labels, self-hosted Glyphs (offline-fähig)
- Klick-Popup + Detail-Panel, Abdeckungs-Liste
- Einzelne, in sich geschlossene `index.html` — GitHub-Pages-tauglich

## Tech-Stack
- **MapLibre GL JS 4.7.1** (standalone HTML, keyless)
- Build-Pipeline in Python: `fetch_soiusa.py → simplify_sts.py → assign_countries.py → build.py`
- `check.py` als Sanity-Suite über das gebaute HTML

## Build
```bash
python fetch_fonts.py       # einmalig: Glyph-PBFs nach fonts/ holen
python fetch_soiusa.py      # SOIUSA-Layer von ARPA Piemonte ziehen (Cache)
python simplify_sts.py      # Geometrie vereinfachen (mapshaper)
python assign_countries.py  # Settore/Farbe/Namen zuweisen, Maske + Label-Punkte
python build.py             # index.html erzeugen
python check.py             # Verifikation
```

## Datenquellen & Lizenzen
- **SOIUSA-Grenzen:** ARPA Piemonte (ArcGIS REST, keyless) — SOIUSA nach Marazzi / Accorsi
- **Satellit:** Esri World Imagery (© Esri, Maxar, Earthstar Geographics)
- **Höhenmodell:** Mapzen Terrain Tiles / AWS Open Data (Terrarium)
- **Ländergrenzen (Zuordnung):** Natural Earth 110m
- **Schrift:** Noto Sans (SIL Open Font License), als PBF-Glyphs self-hosted

Karten-Code und Aufbereitung: eigenes Projekt. Kartendaten wie oben zitiert.

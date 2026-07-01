#!/usr/bin/env python3
"""Derive touren_public.json (committed) from touren.json (local canon).

Strips personal fields — teilnehmer, bemerkung, huetten, dauer, and any private
meta — keeping only impersonal fields needed for the public coverage map.
gipfel + heights stay (impersonal). Run before the public build.
"""
import json
import pathlib

HERE = pathlib.Path(__file__).parent
d = json.loads((HERE / "touren.json").read_text(encoding="utf-8").replace("\x00", ""))

KEEP = {"id", "jahr", "jahr_unsicher", "gegend", "gebirge",
        "land", "lat", "lon", "gipfel", "verifiziert"}

pub = {
    "meta": {
        "titel": "Alpentouren — wo ich war",
        "stand": d["meta"].get("stand"),
        "anzahl": d["meta"].get("anzahl"),
        "hinweis": "Öffentliche Abdeckungskarte (ohne persönliche Angaben).",
    },
    "touren": [{k: v for k, v in t.items() if k in KEEP} for t in d["touren"]],
}

out = HERE / "touren_public.json"
out.write_text(json.dumps(pub, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"touren_public.json: {len(pub['touren'])} Touren "
      f"(teilnehmer/bemerkung/huetten/dauer entfernt)")

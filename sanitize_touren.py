#!/usr/bin/env python3
"""OBSOLETE since E8 (Public = neutral SOIUSA atlas).

The public build no longer reads ANY tour data: build.py loads touren.json only
for --private, and touren_public.json is no longer committed (it still named the
visited groups = personal). This script is kept for reference/history only.

(Historic) Derive touren_public.json from touren.json using a WHITELIST that keeps
ONLY `gruppe` and `besucht`.
"""
import json
import pathlib

HERE = pathlib.Path(__file__).parent
d = json.loads((HERE / "touren.json").read_text(encoding="utf-8").replace("\x00", ""))

# Public whitelist — nothing else survives.
WHITELIST = {"gruppe", "besucht"}


def to_public(t):
    src = {"gruppe": t.get("gebirge", ""), "besucht": True}
    return {k: v for k, v in src.items() if k in WHITELIST}


pub = {
    "meta": {
        "titel": "Alpentouren — wo ich war",
        "hinweis": "Öffentliche Abdeckungskarte — nur besuchte Gebiete, keine Zeit-/Personendaten.",
    },
    "touren": [to_public(t) for t in d["touren"]],
}

out = HERE / "touren_public.json"
out.write_text(json.dumps(pub, ensure_ascii=False, indent=2), encoding="utf-8")
keys = sorted({k for t in pub["touren"] for k in t})
print(f"touren_public.json: {len(pub['touren'])} Einträge, Keys={keys} (Whitelist gruppe/besucht)")

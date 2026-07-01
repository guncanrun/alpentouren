import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
data = json.loads(open('touren.json', encoding='utf-8').read())
found = 0
for t in data['touren']:
    for k in ('gebirge', 'gegend', 'land', 'bemerkung'):
        v = str(t.get(k, '') or '')
        bad = [(hex(ord(c)), repr(c)) for c in v if ord(c) > 0xFF]
        if bad:
            tid = t['id']
            print(f"Tour {tid} [{k}]: {repr(v[:60])} -> {bad}")
            found += 1
    for g in (t.get('gipfel') or []):
        v = g.get('name','')
        bad = [(hex(ord(c)), repr(c)) for c in v if ord(c) > 0xFF]
        if bad:
            print(f"Tour {t['id']} gipfel: {repr(v)} -> {bad}")
            found += 1
if not found:
    print("ALL CLEAR — no chars outside Latin-1 in touren.json")

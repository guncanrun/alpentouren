#!/usr/bin/env python3
"""Sichert den gitignorierten Privat-Kanon nach OneDrive.

Betroffen (nicht im Git, nur 1 lebende Kopie): touren.json (Kanon) und
_cowork_specs/ (Auftrags-/Spec-Dateien, NICHT regenerierbar). Wird als datiertes
ZIP unter dem OneDrive-Backup-Ordner abgelegt; die neuesten KEEP Staende bleiben,
aeltere werden geloescht (Rotation).

Zielordner: <OneDrive>\\05_Archiv\\Backups\\Alpentouren
Der Benutzername wird zur Laufzeit ueber die OneDrive-Env-Var aufgeloest, damit
KEIN persoenlicher Pfad im Repo steht (Datei ist committfaehig).

Aufruf:
  python backup_privat.py           # einmalig, manuell
  (automatisch am Ende von: python build.py --private)
"""
import datetime
import os
import pathlib
import sys
import zipfile

HERE = pathlib.Path(__file__).parent

BACKUP_SUBPATH = pathlib.PurePath("05_Archiv", "Backups", "Alpentouren")
KEEP = 5                                     # Rotation: neueste N ZIPs behalten
SOURCES = ["touren.json", "_cowork_specs"]   # gitignorierter Privat-Kanon


def onedrive_base():
    """OneDrive-Wurzel ueber Env-Vars finden (Fallback: ~/OneDrive)."""
    for var in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        v = os.environ.get(var)
        if v and pathlib.Path(v).is_dir():
            return pathlib.Path(v)
    cand = pathlib.Path.home() / "OneDrive"
    return cand if cand.is_dir() else None


def backup():
    base = onedrive_base()
    if base is None:
        print("backup_privat: OneDrive nicht gefunden -- Backup uebersprungen.")
        return False

    present = [HERE / s for s in SOURCES if (HERE / s).exists()]
    if not present:
        print("backup_privat: keine Privat-Dateien gefunden -- nichts zu sichern.")
        return False

    dest = base / BACKUP_SUBPATH
    dest.mkdir(parents=True, exist_ok=True)

    stamp = datetime.date.today().isoformat()          # JJJJ-MM-TT
    zpath = dest / f"Bergtouren_privat_{stamp}.zip"     # gleicher Tag -> ueberschreibt

    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for p in present:
            if p.is_dir():
                for f in sorted(p.rglob("*")):
                    if f.is_file():
                        z.write(f, f.relative_to(HERE))
            else:
                z.write(p, p.relative_to(HERE))

    # Rotation: neueste KEEP behalten, aeltere loeschen.
    archives = sorted(dest.glob("Bergtouren_privat_*.zip"),
                      key=lambda p: p.stat().st_mtime, reverse=True)
    for old in archives[KEEP:]:
        try:
            old.unlink()
        except OSError:
            pass

    kept = min(len(archives), KEEP)
    size_kb = zpath.stat().st_size / 1024
    print(f"backup_privat: {zpath.name} ({size_kb:.0f} KB) -> {dest} "
          f"[{kept} Stand/Staende behalten]")
    return True


if __name__ == "__main__":
    sys.exit(0 if backup() else 1)

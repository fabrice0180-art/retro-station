"""Vérifications en ligne (CI) : noms MAME et photos des bornes. N'échoue jamais la fabrication."""
import os
import sys
import tempfile

os.environ["RETROSTATION_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from retrostation import mamedb, photos, romcheck, arcadedb  # noqa: E402

ok = mamedb.download()
for line in mamedb._log:
    print(f"::notice::MAME source {line}")
for n in ("daytona", "daytona93", "daytonas", "sf2", "pacman", "outrun"):
    print(f"::notice::MAME {n} = {mamedb.title(n)!r} (clone de {(mamedb.info(n) or {}).get('p')!r})")
for cid in ("arcade", "mame"):
    got = photos.download(cid)
    f = photos.best(cid)
    print(f"::notice::Photo {cid} : {got} {f.stat().st_size if f else 0} octets")
print("::notice::MAME liste ok" if ok else "::warning::MAME liste indisponible")
arcadedb.download()
romcheck.download_mame2003()
for core in ("fbneo", "mame", "mame2003_plus"):
    db = romcheck.load(core)
    print(f"::notice::Empreintes {core} : {len(db) if db else 0} jeux ; f1dream = {len((db or {}).get('f1dream', {}).get('r', []))} puces")

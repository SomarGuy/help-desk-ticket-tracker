#!/usr/bin/env python3
"""
Rebuild vercel-deploy/ from the real app so the hosted copy can never drift.

The hosted copy is the same Flask app, with the package named `helpdesk`
(Vercel's Flask runtime looks for app.py next to it) and a different entry
point that keeps its database in /tmp. Run this after changing anything in app/
or seed.py:

    python scripts/sync_vercel_bundle.py          # write the copy
    python scripts/sync_vercel_bundle.py --check  # exit 1 if it is out of date
"""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "vercel-deploy"


def expected() -> dict:
    """Relative path -> bytes of every file the hosted copy should contain."""
    files = {}
    for src in sorted((ROOT / "app").rglob("*")):
        if src.is_file() and "__pycache__" not in src.parts and src.suffix != ".pyc":
            files["helpdesk/" + str(src.relative_to(ROOT / "app"))] = src.read_bytes()
    seed = (ROOT / "seed.py").read_text().replace("from app", "from helpdesk")
    files["seed.py"] = seed.encode()
    files["LICENSE"] = (ROOT / "LICENSE").read_bytes()
    return files


def main() -> int:
    want = expected()
    if "--check" in sys.argv:
        stale = [name for name, data in want.items()
                 if not (OUT / name).exists() or (OUT / name).read_bytes() != data]
        extra = [str(p.relative_to(OUT)) for p in (OUT / "helpdesk").rglob("*")
                 if p.is_file() and "__pycache__" not in p.parts
                 and str(p.relative_to(OUT)) not in want]
        for name in stale + extra:
            print("out of date:", name)
        return 1 if stale or extra else 0
    if (OUT / "helpdesk").exists():
        shutil.rmtree(OUT / "helpdesk")
    for name, data in want.items():
        target = OUT / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    print(f"wrote {len(want)} files to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

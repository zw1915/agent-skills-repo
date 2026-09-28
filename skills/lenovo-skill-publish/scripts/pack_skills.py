"""Package WorkBuddy skill folders into Lenovo-compatible zips.

Lenovo skillcreate spec: ZIP must contain SKILL.md, total size <= 10MB.

IMPORTANT (learned from a failed push): SKILL.md MUST be at the ZIP ROOT,
not nested in a subfolder. Server rejects otherwise:
  {"status": -2, "message": "SKILL.md 必须位于 ZIP 包的根目录下，不能放在子目录中"}
So we zip the CONTENTS of each skill folder, not the folder itself.
"""
import os
import zipfile

SRC = r"C:\Users\zw\.workbuddy\skills"
OUT = r"F:\workbuddy\2026-09-28-19-38-12\lenovo_zips"

EXCLUDE_DIRS = {"__pycache__", ".git", "node_modules", ".venv", "venv", ".idea"}
EXCLUDE_EXT = {".pyc", ".pyo"}
LIMIT = 10 * 1024 * 1024


def main():
    os.makedirs(OUT, exist_ok=True)
    names = sorted(
        d for d in os.listdir(SRC)
        if os.path.isdir(os.path.join(SRC, d)) and not d.startswith(".")
    )
    results = []
    for n in names:
        src = os.path.join(SRC, n)
        zpath = os.path.join(OUT, n + ".zip")
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
            for root, dirs, files in os.walk(src):
                dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
                for f in files:
                    if os.path.splitext(f)[1] in EXCLUDE_EXT:
                        continue
                    full = os.path.join(root, f)
                    # relative to the SKILL dir -> SKILL.md lands at zip root
                    arc = os.path.relpath(full, src).replace(os.sep, "/")
                    z.write(full, arc)
        sz = os.path.getsize(zpath)
        results.append((n, sz, sz > LIMIT))

    for n, sz, over in results:
        print(f"{n}.zip\t{sz/1024/1024:.2f}MB\t{'OVER-LIMIT' if over else 'ok'}")
    print(f"\ntotal: {len(results)} zips -> {OUT}")
    over = [n for n, _, o in results if o]
    if over:
        print("OVER 10MB:", over)


if __name__ == "__main__":
    main()

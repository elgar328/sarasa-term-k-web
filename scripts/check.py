"""Static checks on dist/ against the source TTFs. Exits non-zero on any failure."""
import argparse
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor

import ots
from fontTools.ttLib import TTFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build import ROOT, SARASA_VERSION, STYLES, css_name, parse_range, ttf_path  # noqa: E402

FACE_RE = re.compile(
    r'src: url\("\./files/([^"]+)"\) format\("woff2"\);\s*unicode-range: ([^;]+);'
)
HINT_TABLES = ("fpgm", "prep", "cvt ", "gasp")
JSDELIVR_LIMIT = 150_000_000  # bytes; jsDelivr does not serve larger npm packages


def parse_css(path):
    """Return [(woff2 file name, code point set)] for one per-style CSS file."""
    with open(path) as f:
        text = f.read()
    faces = [(m.group(1), parse_range(m.group(2))) for m in FACE_RE.finditer(text)]
    if text.count("@font-face") != len(faces):
        raise ValueError(f"{path}: unparsed @font-face rules")
    if "url(" in FACE_RE.sub("", text):
        raise ValueError(f"{path}: url() outside the expected relative form")
    return faces


def check_slice(job):
    """Check one woff2 against its unicode-range and the source font."""
    woff2, cps, src = job
    errors = []
    font = TTFont(woff2)
    cmap = font.getBestCmap()
    if set(cmap) != cps:
        errors.append(f"cmap != unicode-range ({len(set(cmap) ^ cps)} differ)")
    if any(t.format == 14 and t.uvsDict for t in font["cmap"].tables):
        errors.append("non-empty cmap format 14")
    missing = [t for t in HINT_TABLES if t not in font]
    if missing:
        errors.append(f"missing tables {missing}")
    ref = TTFont(src, lazy=True)
    ref_cmap, ref_hmtx = ref.getBestCmap(), ref["hmtx"]
    hmtx = font["hmtx"]
    bad = [cp for cp, g in cmap.items() if hmtx[g][0] != ref_hmtx[ref_cmap[cp]][0]]
    if bad:
        errors.append(f"{len(bad)} advance widths differ, e.g. U+{bad[0]:04X}")
    res = ots.sanitize(woff2, os.devnull, capture_output=True)
    if res.returncode != 0:
        errors.append(f"OTS: {res.stderr.decode().strip()[:200]}")
    return os.path.basename(woff2), errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ttf-dir", required=True)
    ap.add_argument("--dist", default=os.path.join(ROOT, "dist"))
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) // 2))
    a = ap.parse_args()
    failures = []

    regular = TTFont(ttf_path(a.ttf_dir, "Regular"), lazy=True)
    font_cps = set(regular.getBestCmap())
    hmtx, cmap = regular["hmtx"], regular.getBestCmap()
    latin, hangul = hmtx[cmap[ord("a")]][0], hmtx[cmap[ord("가")]][0]
    if hangul != 2 * latin:
        failures.append(f"source: Hangul advance {hangul} != 2 x Latin {latin}")

    jobs, referenced = [], set()
    for style_name, weight, style in STYLES:
        css = os.path.join(a.dist, css_name(weight, style))
        faces = parse_css(css)
        seen = set()
        for name, cps in faces:
            if seen & cps:
                failures.append(f"{css}: overlapping unicode-range in {name}")
            seen |= cps
            path = os.path.join(a.dist, "files", name)
            if not os.path.isfile(path):
                failures.append(f"{css}: missing file {name}")
                continue
            referenced.add(name)
            jobs.append((path, cps, ttf_path(a.ttf_dir, style_name)))
        if seen != font_cps:
            failures.append(f"{css}: covers {len(seen)} code points, font has {len(font_cps)}")

    on_disk = set(os.listdir(os.path.join(a.dist, "files")))
    if on_disk - referenced:
        failures.append(f"files/ has {len(on_disk - referenced)} unreferenced woff2")

    # Every x.y.z version written in the docs must be the one being built.
    docs = [os.path.join(ROOT, "README.md"), os.path.join(ROOT, "RELEASING.md"), os.path.join(a.dist, "README.md")]
    for doc in docs:
        with open(doc) as f:
            stale = set(re.findall(r"\b\d+\.\d+\.\d+\b", f.read())) - {SARASA_VERSION}
        if stale:
            failures.append(f"{doc}: mentions version(s) {sorted(stale)}, building {SARASA_VERSION}")
    with open(os.path.join(a.dist, "package.json")) as f:
        if json.load(f)["version"] != SARASA_VERSION:
            failures.append("dist/package.json version differs from SARASA_VERSION")

    with open(os.path.join(a.dist, "index.css")) as f:
        index = f.read()
    parts = []
    for _, weight, style in STYLES:
        with open(os.path.join(a.dist, css_name(weight, style))) as f:
            parts.append(f.read())
    if index != "\n".join(parts):
        failures.append("index.css is not the concatenation of the per-style CSS files")

    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        for name, errors in ex.map(check_slice, jobs, chunksize=8):
            failures += [f"{name}: {e}" for e in errors]

    packed = json.loads(subprocess.run(
        ["npm", "pack", "--dry-run", "--json", a.dist], capture_output=True, text=True, check=True
    ).stdout)[0]
    dist_files = sum(len(fs) for _, _, fs in os.walk(a.dist))
    for kind in ("size", "unpackedSize"):
        if packed[kind] > JSDELIVR_LIMIT:
            failures.append(f"npm package {kind} {packed[kind] / 1e6:.1f} MB exceeds jsDelivr's 150 MB limit")
    if packed["entryCount"] != dist_files:
        failures.append(f"npm pack has {packed['entryCount']} entries, dist/ has {dist_files} files")

    print(f"checked {len(jobs)} woff2 in {len(STYLES)} styles; npm tarball {packed['size'] / 1e6:.1f} MB "
          f"packed, {packed['unpackedSize'] / 1e6:.1f} MB unpacked, {packed['entryCount']} entries")
    if failures:
        print(f"{len(failures)} FAILURES:")
        for f in failures[:50]:
            print("  " + f)
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()

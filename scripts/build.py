"""Build the Sarasa Term K webfont package.

Subcommands:
  fetch  Download the hinted TTF release from GitHub, verify sha256, extract it.
  build  Split each style into unicode-range woff2 slices and write dist/.

Slicing rule: walk an ordered list of groups and put every code point of the
font into the first group that contains it, so each code point lives in
exactly one slice. Leftovers are packed into fixed-size chunks.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor

from fontTools import subset
from fontTools.ttLib import TTFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The only place the version is set. See RELEASING.md before changing it.
SARASA_VERSION = "1.0.42"
ARCHIVE = f"SarasaTermK-TTF-{SARASA_VERSION}.7z"
ARCHIVE_SHA256 = "2592c52b0dd36738a206b14451fdad68b48df0526073ff84f6082b8dfed2fb66"
FAMILY = "Sarasa Term K"
FILE_PREFIX = "sarasa-term-k"
EXTRA_CHUNK = 600  # code points per leftover chunk (mostly rare Han)

# (source style name, CSS weight, CSS style)
STYLES = [
    ("ExtraLight", 200, "normal"),
    ("ExtraLightItalic", 200, "italic"),
    ("Light", 300, "normal"),
    ("LightItalic", 300, "italic"),
    ("Regular", 400, "normal"),
    ("Italic", 400, "italic"),
    ("SemiBold", 600, "normal"),
    ("SemiBoldItalic", 600, "italic"),
    ("Bold", 700, "normal"),
    ("BoldItalic", 700, "italic"),
]


def span(a, b):
    return set(range(a, b + 1))


# Blocks taken out before the Korean frequency slices. Google spreads the
# KS X 1001 symbols (Greek, arrows, box drawing, ...) over Korean slices,
# which would make Latin-only code pull Korean slices.
SYMBOL_GROUPS = [
    ("greek", span(0x0370, 0x03FF)),
    ("arrows", span(0x2190, 0x21FF)),
    ("math", span(0x2200, 0x22FF)),
    ("technical", span(0x2300, 0x23FF)),
    ("box", span(0x2500, 0x259F)),
    ("shapes", span(0x25A0, 0x25FF)),
]

# Old Hangul composition (ljmo/vjmo/tjmo) needs all jamo in one face.
# Listed before SYMBOL_GROUPS so the dotted circle U+25CC lands here.
JAMO_GROUP = (
    "hangul-jamo",
    span(0x1100, 0x11FF) | span(0xA960, 0xA97F) | span(0xD7B0, 0xD7FF)
    | span(0x302E, 0x302F) | {0x25CC},
)


def parse_range(value):
    """Parse a CSS unicode-range value into a set of code points."""
    cps = set()
    for part in value.split(","):
        part = part.strip()[2:]
        if "-" in part:
            a, b = part.split("-")
            cps.update(range(int(a, 16), int(b, 16) + 1))
        else:
            cps.add(int(part, 16))
    return cps


def load_google_slices():
    path = os.path.join(ROOT, "data", "noto-sans-kr-slices.txt")
    with open(path) as f:
        lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]
    assert len(lines) == 124, f"expected 124 slices, got {len(lines)}"
    return [parse_range(l) for l in lines]


def to_unicode_range(cps):
    """Compress a set of code points into a CSS unicode-range value."""
    cps = sorted(cps)
    out, start, prev = [], cps[0], cps[0]
    for c in cps[1:] + [None]:
        if c is not None and c == prev + 1:
            prev = c
            continue
        out.append(f"U+{start:x}" if start == prev else f"U+{start:x}-{prev:x}")
        if c is not None:
            start = prev = c
    return ", ".join(out)


def ordered_groups(google):
    """Return the ordered (name, code points) list used for first-match slicing."""
    groups = [
        ("latin", google[123] | span(0x0300, 0x036F)),
        ("latin-ext", google[122]),
        ("vietnamese", google[121]),
        ("cyrillic", google[120]),
        JAMO_GROUP,
        *SYMBOL_GROUPS,
    ]
    groups += [(f"ko-{i}", google[i]) for i in range(120)]
    return groups


def plan_slices(font_cps, google):
    """Assign every font code point to exactly one named slice."""
    remaining = set(font_cps)
    plan = []
    for name, cps in ordered_groups(google):
        hit = cps & remaining
        if hit:
            plan.append((name, hit))
            remaining -= hit
    leftover = sorted(remaining)
    for i in range(0, len(leftover), EXTRA_CHUNK):
        plan.append((f"extra-{i // EXTRA_CHUNK}", set(leftover[i : i + EXTRA_CHUNK])))
    return plan


def css_name(weight, style):
    return f"{weight}.css" if style == "normal" else f"{weight}-{style}.css"


def woff2_name(weight, style, slice_name):
    return f"{FILE_PREFIX}-{weight}-{style}-{slice_name}.woff2"


def build_slice(job):
    src, cps, out = job
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.layout_features = ["*"]
    opts.name_IDs = ["*"]
    opts.notdef_outline = True
    # Do not pull in bidi-mirrored partners: each code point must stay in one slice.
    opts.bidi_closure = False
    # Hinting is kept (subset default).
    font = TTFont(src)
    sub = subset.Subsetter(opts)
    sub.populate(unicodes=cps)
    sub.subset(font)
    font.flavor = "woff2"
    font.save(out)
    return out, os.path.getsize(out)


def ttf_path(ttf_dir, style_name):
    return os.path.join(ttf_dir, f"SarasaTermK-{style_name}.ttf")


def cmd_fetch(a):
    os.makedirs(a.cache, exist_ok=True)
    archive = os.path.join(a.cache, ARCHIVE)
    if not os.path.exists(archive):
        subprocess.run(
            ["gh", "release", "download", f"v{SARASA_VERSION}", "-R", "be5invis/Sarasa-Gothic",
             "-p", ARCHIVE, "-D", a.cache],
            check=True,
        )
    h = hashlib.sha256()
    with open(archive, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    if h.hexdigest() != ARCHIVE_SHA256:
        sys.exit(f"sha256 mismatch: {h.hexdigest()}")
    out = os.path.join(a.cache, "ttf")
    if not os.path.isdir(out):
        subprocess.run(["7zz", "x", "-y", f"-o{out}", archive], check=True, stdout=subprocess.DEVNULL)
    print(f"sha256 ok; TTFs in {out}")


def cmd_build(a):
    styles = [s for s in STYLES if not a.only or s[0] in a.only]
    google = load_google_slices()

    # All styles must share one cmap so one slice plan serves every style.
    cmaps = {s[0]: set(TTFont(ttf_path(a.ttf_dir, s[0]), lazy=True).getBestCmap()) for s in STYLES}
    first = cmaps[STYLES[0][0]]
    for name, cm in cmaps.items():
        if cm != first:
            sys.exit(f"cmap of {name} differs from {STYLES[0][0]}")
    plan = plan_slices(first, google)

    if os.path.exists(a.out):
        shutil.rmtree(a.out)
    os.makedirs(os.path.join(a.out, "files"))

    jobs, meta = [], []
    for style_name, weight, style in styles:
        src = ttf_path(a.ttf_dir, style_name)
        for slice_name, cps in plan:
            out = os.path.join(a.out, "files", woff2_name(weight, style, slice_name))
            jobs.append((src, sorted(cps), out))
            meta.append((style_name, weight, style, slice_name, cps))

    t0 = time.time()
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        results = list(ex.map(build_slice, jobs, chunksize=1))
    elapsed = time.time() - t0

    report = {"sarasa_version": SARASA_VERSION, "archive_sha256": ARCHIVE_SHA256,
              "fonttools": __import__("fontTools").version, "workers": a.workers,
              "build_seconds": round(elapsed, 1), "code_points": len(first),
              "slices_per_style": len(plan), "styles": {}}
    css_by_style = {}
    for style_name, weight, style in styles:
        rules, sizes = [], {}
        for (s_name, w, st, slice_name, cps), (path, size) in zip(meta, results):
            if s_name != style_name:
                continue
            sizes[slice_name] = size
            rules.append(
                "@font-face {\n"
                f'  font-family: "{FAMILY}";\n'
                f"  font-style: {style};\n"
                f"  font-weight: {weight};\n"
                "  font-display: swap;\n"
                f'  src: url("./files/{os.path.basename(path)}") format("woff2");\n'
                f"  unicode-range: {to_unicode_range(cps)};\n"
                "}\n"
            )
        css = "\n".join(rules)
        name = css_name(weight, style)
        with open(os.path.join(a.out, name), "w") as f:
            f.write(css)
        css_by_style[style_name] = css
        src = TTFont(ttf_path(a.ttf_dir, style_name), lazy=True)
        largest = max(sizes, key=sizes.get)
        report["styles"][style_name] = {
            "css": name,
            "css_bytes": len(css.encode()),
            "woff2_bytes": sum(sizes.values()),
            "largest_slice": [largest, sizes[largest]],
            "hangul_jamo_bytes": sizes.get("hangul-jamo"),
            "hinting_table_bytes": {t: len(src.reader[t]) for t in ("fpgm", "prep", "cvt ") if t in src.reader},
            "slices": sizes,
        }

    if not a.only:
        with open(os.path.join(a.out, "index.css"), "w") as f:
            f.write("\n".join(css_by_style[s[0]] for s in STYLES))
        write_package_files(a.out)

    os.makedirs(os.path.dirname(a.report), exist_ok=True)
    with open(a.report, "w") as f:
        json.dump(report, f, indent=2)

    total = sum(v["woff2_bytes"] for v in report["styles"].values())
    print(f"{len(styles)} styles x {len(plan)} slices, woff2 {total / 1e6:.1f} MB, {elapsed:.0f}s")


def write_package_files(out):
    with open(os.path.join(ROOT, "package.json")) as f:
        pkg = json.load(f)
    pkg.pop("private", None)
    pkg = {"name": pkg.pop("name"), "version": SARASA_VERSION, **pkg}
    pkg["files"] = ["*.css", "files/*.woff2", "LICENSE", "README.md"]
    pkg["publishConfig"] = {"access": "public"}
    with open(os.path.join(out, "package.json"), "w") as f:
        json.dump(pkg, f, indent=2, ensure_ascii=False)
        f.write("\n")
    shutil.copy(os.path.join(ROOT, "OFL.txt"), os.path.join(out, "LICENSE"))
    with open(os.path.join(ROOT, "npm", "README.md")) as f:
        readme = f.read().replace("{{VERSION}}", SARASA_VERSION)
    with open(os.path.join(out, "README.md"), "w") as f:
        f.write(readme)


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    f = sp.add_parser("fetch")
    f.add_argument("--cache", required=True, help="directory for the archive and extracted TTFs")
    b = sp.add_parser("build")
    b.add_argument("--ttf-dir", required=True)
    b.add_argument("--out", default=os.path.join(ROOT, "dist"))
    b.add_argument("--report", default=os.path.join(ROOT, "build", "report.json"))
    b.add_argument("--only", nargs="*", help="build only these source styles (no index.css/package files)")
    b.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) // 2))
    a = ap.parse_args()
    {"fetch": cmd_fetch, "build": cmd_build}[a.cmd](a)


if __name__ == "__main__":
    main()

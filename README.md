# sarasa-term-k-web

Build scripts for the npm package [`@elgar328/sarasa-term-k`](https://www.npmjs.com/package/@elgar328/sarasa-term-k), a webfont build of [Sarasa Term K](https://github.com/be5invis/Sarasa-Gothic) served through jsDelivr.

Sarasa Term K combines Iosevka for Latin with Source Han Sans for Hangul. Latin glyphs are 0.5 em wide and Hangul glyphs exactly 1 em, so mixed Korean and English code stays aligned on a two-column grid. The build splits all ten styles of the hinted release into small woff2 files by `unicode-range`, so a browser downloads only the parts a page actually uses.

## Usage

Load a style with `<link>` or `@import`, then use the `"Sarasa Term K"` family.

```html
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@elgar328/sarasa-term-k@1.0.42/400.css">
```

```css
@import url("https://cdn.jsdelivr.net/npm/@elgar328/sarasa-term-k@1.0.42/400.css");
@import url("https://cdn.jsdelivr.net/npm/@elgar328/sarasa-term-k@1.0.42/400-italic.css");

code, pre {
  font-family: "Sarasa Term K", monospace;
}
```

There is one stylesheet per style: `200.css`, `300.css`, `400.css`, `600.css`, `700.css`, and an `-italic` version of each. `index.css` includes all ten but is large, so load only the styles you need.

The stylesheets point only to the web files and do not use `local()`, so every visitor sees the same build. On pages that load them, the web font is used even where Sarasa Term K is installed. To prefer an installed copy, define your own family with `local()` sources and list it before `"Sarasa Term K"`.

## How the font is split

Each character in the font goes into exactly one file: the first group below that contains it.

1. Latin groups from Google Fonts: `latin` (with combining marks U+0300–036F), `latin-ext`, `vietnamese`, `cyrillic`
2. `hangul-jamo`: old Hangul jamo, kept together so they can combine
3. Symbol blocks common in code: `greek`, `arrows`, `math`, `technical`, `box`, `shapes`
4. Korean groups from Google Fonts' Noto Sans KR, split by frequency of use: `ko-0` … `ko-119`
5. All remaining characters, in code point order, 600 per file: `extra-N`

As a result, English-only text loads just the `latin` file, and a file tree such as `├── →` adds only `box` and `arrows`.

### Known limitations

- Variation sequences (cmap format 14, mostly Han ideograph variants) are not supported. The default glyph is shown instead.
- A combining mark added to a letter outside `latin`, such as decomposed Vietnamese or Cyrillic, may be misplaced. Precomposed text is not affected.
- A modern Hangul syllable followed by an old Hangul final jamo may not combine.

## Building

Requires `gh`, `7zz`, `uv`, and Node.js.

```sh
venv=$(mktemp -d)
(cd "$venv" && uv init --bare --python 3.12 && uv add fonttools brotli opentype-sanitizer playwright)
py() { uv run --project "$venv" python -I "$@"; }

cache=$(mktemp -d)
py scripts/build.py fetch --cache "$cache"        # download, verify sha256, extract
py scripts/build.py build --ttf-dir "$cache/ttf"  # write dist/
py scripts/check.py --ttf-dir "$cache/ttf"        # static checks

npm pack ./dist
tar xzf elgar328-sarasa-term-k-*.tgz
uv run --project "$venv" playwright install webkit chromium
py scripts/browser_test.py --pkg package --shots shots  # WebKit and Chromium tests
```

`dist/` is the npm package. Generated files are not committed.

To publish a new version, see [RELEASING.md](RELEASING.md).

## License

- Build scripts: MIT (`LICENSE`)
- Fonts: SIL Open Font License 1.1 (`OFL.txt`, shipped as `LICENSE` in the npm package)

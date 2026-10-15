# @elgar328/sarasa-term-k

Webfont build of [Sarasa Term K](https://github.com/be5invis/Sarasa-Gothic) {{VERSION}}, the Korean monospace variant of Sarasa Gothic (Iosevka + Source Han Sans).

All ten styles of the hinted release are split into small woff2 files by `unicode-range`, so a browser downloads only the parts a page actually uses. The glyphs are unchanged. This is an unofficial redistribution.

## Usage

Load a style with `<link>` or `@import`, then use the `"Sarasa Term K"` family.

```html
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@elgar328/sarasa-term-k@{{VERSION}}/400.css">
```

```css
@import url("https://cdn.jsdelivr.net/npm/@elgar328/sarasa-term-k@{{VERSION}}/400.css");

code, pre {
  font-family: "Sarasa Term K", monospace;
}
```

Load only the styles you need:

| Weight | Upright | Italic |
|---|---|---|
| 200 ExtraLight | `200.css` | `200-italic.css` |
| 300 Light | `300.css` | `300-italic.css` |
| 400 Regular | `400.css` | `400-italic.css` |
| 600 SemiBold | `600.css` | `600-italic.css` |
| 700 Bold | `700.css` | `700-italic.css` |

`index.css` includes all ten styles, but it is a large stylesheet. Prefer the per-style files.

For details and build scripts, see [github.com/elgar328/sarasa-term-k-web](https://github.com/elgar328/sarasa-term-k-web).

## License

The fonts are licensed under the SIL Open Font License 1.1. See `LICENSE`.

Copyright (c) 2015-2025, Renzhi Li (aka. Belleve Invis). Portions copyright The Inter Project Authors, Adobe Systems Incorporated (Reserved Font Name 'Source'), and Google Inc.

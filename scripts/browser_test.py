"""Render tests in WebKit and Chromium against an extracted npm package (or a CDN URL).

Most cases use a copy of the CSS with the family renamed to "Sarasa Term K Test", so an
installed Sarasa can never satisfy the test; one case loads the shipped CSS unchanged.
Fallback is Courier (0.6 em), so a 0.5 em cell width proves the web font is in use.
"""
import argparse
import functools
import http.server
import os
import re
import sys
import tempfile
import threading
import urllib.request

from playwright.sync_api import sync_playwright

TEST_FAMILY = "Sarasa Term K Test"
SIZE = 16  # px; Latin cell = 8 px, Hangul = 16 px
SLICE_RE = re.compile(r"sarasa-term-k-(\d+)-(normal|italic)-(.+)\.woff2$")


class CorsHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *args):
        pass


class Server(http.server.ThreadingHTTPServer):
    # The default backlog (5) drops connections when a browser fetches many slices at once.
    request_queue_size = 128

    def handle_error(self, request, client_address):
        # Browsers drop keep-alive connections when a context closes; that is not a failure.
        if not isinstance(sys.exc_info()[1], (ConnectionResetError, BrokenPipeError)):
            super().handle_error(request, client_address)


def serve(root):
    handler = functools.partial(CorsHandler, directory=root)
    httpd = Server(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_port}"


def make_test_css(pkg_css_text, base):
    """Rename the family and point url()s at the package base URL."""
    text = pkg_css_text.replace('font-family: "Sarasa Term K";', f'font-family: "{TEST_FAMILY}";')
    return text.replace('url("./files/', f'url("{base}/files/')


def page_html(css_links, body, family=TEST_FAMILY, extra_style=""):
    links = "".join(f'<link rel="stylesheet" href="{u}">' for u in css_links)
    return (
        f'<!doctype html><html><head><meta charset="utf-8">{links}<style>'
        f'body{{margin:8px}} .m{{font:{SIZE}px/1.5 "{family}", Courier; white-space:pre}}'
        f" span{{display:inline-block}} {extra_style}</style></head><body>{body}</body></html>"
    )


class Runner:
    def __init__(self, browser, work, work_url, failures):
        self.browser, self.work, self.work_url, self.failures = browser, work, work_url, failures

    def open(self, name, html, via_file=False):
        """Write a page, load it in a fresh context, return (context, page, fetched slices)."""
        path = os.path.join(self.work, f"{name}.html")
        with open(path, "w") as f:
            f.write(html)
        ctx = self.browser.new_context()
        page = ctx.new_page()
        fetched = set()

        def on_response(resp):
            m = SLICE_RE.search(resp.url)
            if m and resp.ok:
                fetched.add(f"{m.group(1)}-{m.group(2)}-{m.group(3)}")
            elif m:
                self.fail(name, f"HTTP {resp.status} for {resp.url}")

        page.on("response", on_response)
        page.on("requestfailed", lambda req: SLICE_RE.search(req.url) and self.fail(
            name, f"request failed ({req.failure}): {req.url}"))
        url = f"file://{path}" if via_file else f"{self.work_url}/{name}.html"
        page.goto(url)
        page.evaluate("document.fonts.ready.then(() => 0)")
        page.wait_for_load_state("networkidle")
        errors = page.evaluate(
            "[...document.fonts].filter(f => f.status === 'error')"
            ".map(f => `${f.family} ${f.weight} ${f.style} ${f.unicodeRange.slice(0, 40)}`)"
        )
        if errors:
            self.fail(name, f"font faces failed to load: {errors[:3]}")
        return ctx, page, fetched

    def fail(self, case, msg):
        self.failures.append(f"[{self.browser.browser_type.name}] {case}: {msg}")

    def width(self, page, sel):
        return page.evaluate(
            f"(() => {{ const r = document.createRange(); r.selectNodeContents(document.querySelector('{sel}'));"
            " return r.getBoundingClientRect().width; })()"
        )

    def expect_width(self, case, page, sel, expected):
        w = self.width(page, sel)
        if abs(w - expected) > 0.01:
            self.fail(case, f"{sel} width {w} != {expected}")

    def expect_fetched(self, case, fetched, want=None, allow_prefix=None):
        if want is not None and fetched != want:
            self.fail(case, f"fetched {sorted(fetched)} != {sorted(want)}")
        if allow_prefix is not None:
            bad = [s for s in fetched if not any(s.startswith(p) for p in allow_prefix)]
            if bad:
                self.fail(case, f"unexpected slices {bad}")


def run(browser, css_base, work, work_url, failures, shots):
    r = Runner(browser, work, work_url, failures)
    t400, t400i = f"{work_url}/test/400.css", f"{work_url}/test/400-italic.css"

    # Latin-only text: only the latin slice.
    ctx, page, got = r.open("latin", page_html([t400], '<div class="m"><span id="a">abcdefgh</span>\n'
                                                "fn main() { println!(\"0O il1 {}\", x != y); }</div>"))
    r.expect_fetched("latin", got, {"400-normal-latin"})
    r.expect_width("latin", page, "#a", 8 * SIZE / 2)
    ctx.close()

    # File tree: latin + box + arrows.
    ctx, page, got = r.open("tree", page_html([t400], '<div class="m">src\n├── main.rs → ok\n└── lib.rs</div>'))
    r.expect_fetched("tree", got, {"400-normal-latin", "400-normal-box", "400-normal-arrows"})
    ctx.close()

    # Mixed Korean: latin + Korean slices only; Hangul is exactly two cells.
    ctx, page, got = r.open("mixed", page_html([t400], '<div class="m"><span id="h">가나다라</span>'
                                                '<span id="a">abcdefgh</span>\n// 설정 파일을 읽어서 템플릿 경로를 확인합니다</div>'))
    r.expect_fetched("mixed", got, allow_prefix=["400-normal-latin", "400-normal-ko-"])
    if not any(s.startswith("400-normal-ko-") for s in got):
        r.fail("mixed", "no Korean slice fetched")
    r.expect_width("mixed", page, "#h", 4 * SIZE)
    r.expect_width("mixed", page, "#a", 8 * SIZE / 2)
    ctx.close()

    # Italic text uses the italic files only.
    ctx, page, got = r.open("italic", page_html([t400, t400i], '<div class="m" style="font-style:italic">'
                                                 '<span id="i">abcdefgh</span></div>'))
    r.expect_fetched("italic", got, {"400-italic-latin"})
    r.expect_width("italic", page, "#i", 8 * SIZE / 2)
    ctx.close()

    # Old Hangul: three jamo compose into one syllable-wide glyph.
    ctx, page, got = r.open("jamo", page_html([t400], '<div class="m"><span id="j">ᄒᆞᆫ</span>'
                                              '<span id="g">가</span></div>'))
    r.expect_fetched("jamo", got, allow_prefix=["400-normal-hangul-jamo", "400-normal-ko-", "400-normal-latin"])
    r.expect_width("jamo", page, "#j", r.width(page, "#g"))
    ctx.close()

    # A file:// page loading the CSS over http, like a saved HTML document opened from disk.
    ctx, page, got = r.open("file-origin", page_html([t400], '<div class="m"><span id="a">abcdefgh</span>한글</div>'),
                            via_file=True)
    r.expect_width("file-origin", page, "#a", 8 * SIZE / 2)
    if "400-normal-latin" not in got:
        r.fail("file-origin", f"latin slice not fetched: {sorted(got)}")
    ctx.close()

    # The shipped CSS, unmodified.
    ctx, page, got = r.open("shipped", page_html([f"{css_base}/400.css"], '<div class="m">abc 한글</div>',
                                                 family="Sarasa Term K"))
    r.expect_fetched("shipped", got, allow_prefix=["400-normal-latin", "400-normal-ko-"])
    if "400-normal-latin" not in got:
        r.fail("shipped", f"latin slice not fetched: {sorted(got)}")
    ctx.close()

    # All ten styles, rendered for visual review.
    sample = "fn main() { let 이름 = \"사라사\"; } // 0O il1 → ├──"
    rows = "".join(
        f'<div class="m" style="font-weight:{w};font-style:{s}">{w} {s:6} {sample}</div>'
        for w in (200, 300, 400, 600, 700) for s in ("normal", "italic")
    )
    links = [f"{work_url}/test/{w}{'' if s == 'normal' else '-italic'}.css"
             for w in (200, 300, 400, 600, 700) for s in ("normal", "italic")]
    ctx, page, got = r.open("styles", page_html(links, rows))
    if len({s.split("-")[0] + s.split("-")[1] for s in got}) != 10:
        r.fail("styles", f"not all ten styles fetched: {sorted(got)}")
    page.screenshot(path=os.path.join(shots, f"{browser.browser_type.name}-styles.png"), full_page=True)
    ctx.close()

    # Web font (top) against the installed Sarasa, if any (bottom), for visual review.
    rows = (f'<div class="m">{sample}</div>'
            f'<div class="m" style="font-family:\'Sarasa Term K\', Courier">{sample}</div>')
    ctx, page, got = r.open("compare", page_html([t400], rows, extra_style=".m{font-size:13px}"))
    page.screenshot(path=os.path.join(shots, f"{browser.browser_type.name}-compare.png"),
                    clip={"x": 0, "y": 0, "width": 480, "height": 60})
    ctx.close()


def main():
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--pkg", help="extracted npm package directory (served locally)")
    src.add_argument("--base-url", help="package URL to test instead, e.g. on jsDelivr")
    ap.add_argument("--shots", required=True, help="directory for screenshots")
    a = ap.parse_args()
    os.makedirs(a.shots, exist_ok=True)

    work = tempfile.mkdtemp(prefix="sarasa-browser-")
    pkg_httpd = None
    if a.pkg:
        pkg_httpd, base = serve(a.pkg)
    else:
        base = a.base_url.rstrip("/")
    work_httpd, work_url = serve(work)

    os.makedirs(os.path.join(work, "test"))
    for w in (200, 300, 400, 600, 700):
        for s in ("", "-italic"):
            with urllib.request.urlopen(f"{base}/{w}{s}.css") as resp:
                css = resp.read().decode()
            with open(os.path.join(work, "test", f"{w}{s}.css"), "w") as f:
                f.write(make_test_css(css, base))

    failures = []
    with sync_playwright() as p:
        for bt in (p.webkit, p.chromium):
            browser = bt.launch()
            run(browser, base, work, work_url, failures, a.shots)
            browser.close()

    work_httpd.shutdown()
    if pkg_httpd:
        pkg_httpd.shutdown()
    if failures:
        print(f"{len(failures)} FAILURES:")
        for f in failures:
            print("  " + f)
        sys.exit(1)
    print(f"all browser checks passed; screenshots in {a.shots}")


if __name__ == "__main__":
    main()

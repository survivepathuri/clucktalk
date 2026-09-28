"""Font fall-through probe: evidence for docs/evidence/2026-09-28_strict_csp.md (not part of the app).

Serves a page with the Simulator's real sandbox CSP (clucktalk.simulator.app.sandbox_csp) and writes a probe
document into an inner iframe with doc.write, exactly as sandbox.js does, so the probe inherits that CSP.
The probe declares one @font-face whose src lists the bundled Noto Sans Telugu as a data: URL first and an
https URL second, then reports which source Chrome activated.

Run (Windows, from the repo root; needs network access to fonts.gstatic.com for the https test font):
    .venv\\Scripts\\python docs\\evidence\\2026-09-28_strict_csp\\font_probe.py 8799
    chrome --headless=new --virtual-time-budget=8000 --dump-dom "http://127.0.0.1:8799/probe?case=<name>"
The result is the JSON in <pre id="out">.
"""

import base64
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
from clucktalk.simulator.app import sandbox_csp  # noqa: E402

GSTATIC = (
    "https://fonts.gstatic.com/s/notosanstelugu/v30/"
    "0FlxVOGZlE2Rrtr-HmgkMWJNjJ5_RyT8o8c7fHkeg-esVC5dzHkHIJQqrEntezbaWkzey3s.woff2"
)
DATA = "data:font/otf;base64," + base64.b64encode((ROOT / "ui/fonts/NotoSansTelugu-Regular.otf").read_bytes()).decode()
DECLARED = {"resourceDomains": ["https://fonts.gstatic.com"]}

CASES = {
    # name: (strict, declared csp, src list)
    "strict_data_then_https": (True, DECLARED, [(DATA, "opentype"), (GSTATIC, "woff2")]),
    "strict_data_only": (True, {}, [(DATA, "opentype")]),
    "reference_data_then_https": (False, DECLARED, [(DATA, "opentype"), (GSTATIC, "woff2")]),
}

PROBE = """<!doctype html><html><head><meta charset="utf-8"><style>
@font-face { font-family: "Probe"; font-weight: 400; src: %s; }
body { font-family: "Probe", monospace; }
</style></head><body><span lang="te">తెలుగు</span><script>
const violations = [];
document.addEventListener("securitypolicyviolation", (e) =>
  violations.push({ directive: e.effectiveDirective, blocked: e.blockedURI.slice(0, 40) }));
document.fonts.load('16px "Probe"', "తెలుగు")
  .catch((e) => violations.push({ load_error: String(e) }))
  .then(() => document.fonts.ready).then(() => {
  const faces = [...document.fonts].filter((f) => f.family.replace(/"/g, "") === "Probe").map((f) => f.status);
  const fetched = performance.getEntriesByType("resource").map((r) => r.name).filter((n) => n.includes("gstatic"));
  parent.document.getElementById("out").textContent = JSON.stringify({
    check: document.fonts.check('16px "Probe"', "తెలుగు"), faces, gstatic_fetched: fetched.length > 0, violations });
});
</script></body></html>"""

OUTER = """<!doctype html><html><head><meta charset="utf-8"></head><body><pre id="out">pending</pre><script>
const inner = document.createElement("iframe");
inner.setAttribute("sandbox", "allow-scripts allow-same-origin");
document.body.appendChild(inner);
const doc = inner.contentDocument; doc.open(); doc.write(%s); doc.close();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        url = urlparse(self.path)
        case = parse_qs(url.query).get("case", [""])[0]
        if url.path != "/probe" or case not in CASES:
            self.send_error(404)
            return
        strict, declared, srcs = CASES[case]
        src = ", ".join(f'url("{u}") format("{f}")' for u, f in srcs)
        body = (OUTER % json.dumps(PROBE % src).replace("</", "<\\/")).encode()  # keep the outer <script> intact
        self.send_response(200)
        self.send_header("content-type", "text/html; charset=utf-8")
        self.send_header("content-security-policy", sandbox_csp(declared, strict=strict))
        self.send_header("x-probe-csp", sandbox_csp(declared, strict=strict))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()

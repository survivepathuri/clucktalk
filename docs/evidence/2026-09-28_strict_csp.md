# Evidence: card fonts under a strict MCP Apps CSP (2026-09-28)

Question: a host that applies the MCP Apps default CSP literally (`default-src 'none'`, no `font-src`) blocks the
card's inlined `data:` font (FRICTION_LOG FL-007). If a card lists the inlined font first and an https copy second,
and declares the https origin in `_meta.ui.csp.resourceDomains` (the spec maps it to `font-src`), does the browser
skip the blocked `data:` entry and load the https one? MDN's `@font-face src` page says the browser uses "the first
one it can successfully activate" but does not say whether a CSP-blocked entry counts as a failure (FL-010).

Setup: Windows 11 Pro, Google Chrome 153.0.8010.53 (headless, `--headless=new`), Python 3.13.15, demo data.

## 1. Simulator: new "Card CSP (fonts)" control

Developer panel → **Card CSP (fonts)**: *Reference host* (default: spec default + `font-src 'self' data:`, as the
ext-apps reference host) or *Strict* (the spec default only; fonts load only from declared `resourceDomains`).
URL option `?csp=strict`. The proxy header comes from `sandbox_csp(..., strict=True)`; with nothing declared it has
no `font-src` directive at all, so fonts fall back to `default-src 'none'`.

Real Simulator turn ("how is shed two doing", Echo Show, 1024×600), driven over the Chrome DevTools protocol:

| Mode | Developer panel (excerpt) | Result |
|---|---|---|
| Strict | `card: ui://clucktalk/farm-status.html in sandbox http://localhost:8766 (CSP: strict spec default)` · `card log (warning): {"event":"font","message":"Bundled Noto Sans Telugu did not load (host CSP?); using a system Telugu font."}` · `cross-modal ✓ all 11 spoken numbers are on the card; all 25 card numbers are in the tool result; 3 KPI values equal their fields` | Telugu renders in the system font; the card reports it ([screenshot](2026-09-28_strict_csp/01_strict-csp_system-telugu-font.png)) |
| Reference | `(CSP: spec default + font-src data:)`, no font warning, cross-modal ✓ | Bundled Noto Sans Telugu ([screenshot](2026-09-28_strict_csp/02_reference-csp_bundled-font.png)) |

## 2. Fall-through probe

[`font_probe.py`](2026-09-28_strict_csp/font_probe.py) serves a page whose CSP header is built by the Simulator's own
`sandbox_csp`, and writes a probe document into a sandboxed inner iframe with `doc.write`, as `sandbox.js` does, so the
probe inherits that CSP. The probe declares one `@font-face` whose `src` lists the bundled Noto Sans Telugu 2.005 as
`data:` (first), then Noto Sans Telugu woff2 from `https://fonts.gstatic.com` (second; a public https test URL only,
since CluckTalk's own public https origin arrives with the AWS setup). It reports `document.fonts.check`, the face
status, whether the https file was fetched (Resource Timing), and CSP violations.

| Case | CSP `font-src` | `src` order | Face | https fetched | Violations |
|---|---|---|---|---|---|
| strict_data_then_https | `https://fonts.gstatic.com` | data:, https | **loaded** (`check` true) | **yes** | `font-src` blocked `data` |
| strict_data_only | *(none → `default-src 'none'`)* | data: | error (`check` false) | no | `font-src` blocked `data`; `NetworkError` |
| reference_data_then_https | `'self' data: https://fonts.gstatic.com` | data:, https | loaded (`check` true) | **no** | none |

Raw output (run twice, identical):

```
== strict_data_then_https
{"check":true,"faces":["loaded"],"gstatic_fetched":true,"violations":[{"directive":"font-src","blocked":"data"}]}
== strict_data_only
{"check":false,"faces":["error"],"gstatic_fetched":false,"violations":[{"load_error":"NetworkError: A network error occurred."},{"directive":"font-src","blocked":"data"}]}
== reference_data_then_https
{"check":true,"faces":["loaded"],"gstatic_fetched":false,"violations":[]}
```

## 3. Conclusion

In Chrome 153, a CSP-blocked `data:` entry in `@font-face src` falls through to the next entry. On a permissive host
the https copy is never fetched. So the planned order (inlined font first, declared https copy second) works on both
kinds of host. Not yet verified: other engines (Safari/WebKit, Firefox), the real Alexa+ renderer, and CluckTalk's
own https font origin (waits for the AWS setup task). Nothing in the card changed today.

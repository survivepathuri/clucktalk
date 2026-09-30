# Evidence: Health Triage step 1B, placeholder photo input + triage card (2026-09-30)

Demo mode only (`MOCK_BEDROCK=true`, demo rules, synthetic farm). **No AWS call and no paid model call was made for
this step.** There are no real photos in the repository: the three images are labelled placeholders
(`docs/assets/`, `docs/SOURCES.md`). Photo input is **not validated on real photos**; nothing here shows that photo
triage works. In this step a photo is recorded and shown as attached, is never sent to a model, and never changes the
result.

## End to end: Simulator -> MCP server -> spoken answer + card
Real `python tasks.py run` processes (Simulator on 8766, MCP server on 8765, fresh state), driven through the
Simulator's own `POST /api/turn` with `photo_ref` (what its "Attach a photo" control sends), device "Echo Show".

| Farmer says (+ attached) | Tool | Round trip | Result |
|---|---|---|---|
| "shed 2 birds are coughing and not eating" + placeholder 2 | `start_health_check` | 188 ms | `analyzing`, floor `urgent`, `photo.analyzed = false`; speech ends "A placeholder photo is attached. It was not analyzed, and it did not change the result." |
| "is the shed 2 health check ready" | `get_health_check` | 8 ms | `ready`, `urgent`, same photo block read back from the stored check |
| "shed 1 birds are panting" (no photo) | `start_health_check` | 13 ms | `photo: null`, no photo sentence |
| "house two swollen heads and blue combs, birds dying suddenly" + placeholder 3 | `start_health_check` | 14 ms | `ready` at once, `notifiable_suspect`, engine `none` (no model call), photo recorded only |

All four answers name the card `ui://clucktalk/health-check.html` (`text/html;profile=mcp-app`).

## Card rendering (headless Chrome, scratch host page)
The built card was loaded in an iframe of a small scratch host page that answers `ui/initialize` and sends the real
`structuredContent` captured above as the tool result (screenshots in `docs/evidence/2026-09-30_health_photo/`, light
and dark for: still checking with a photo, ready with a photo, red flags with a photo). Not run inside the Simulator's
sandbox proxy. This first render found two card bugs, both fixed and re-rendered: the word "null" printed where a
section was missing (regression test added), and the Telugu caption overflowing the placeholder tile.

## Harness
- `python tasks.py check`: PASSED. 24 harness, **377 unit (+13)**, **183 contract (+13)**, AOSS, secret scan.
- `python tasks.py eval-fast`: **21/21** (was 19/19; +2 photo cases, 0 regressions).
- Mutation check (scratch script, byte-exact restore): **9/9 caught** (spoken photo note, photo not stored, photo output
  dropped, ready-text sentence, photo leaking into the prompt, Simulator attaching a photo to any intent, Simulator
  accepting any `photo_ref`, the card appending a missing section, the SOURCES placeholder label).
- Telugu: 227 -> 245 pending (+18 new strings, all left pending; none approved).
- Tests were written after the code in this step (not before); the mutation run is the check that they fail without it.
- Not done: the Rule 11 independent review for agent 1 is still owed (see the progress log).

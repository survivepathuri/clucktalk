# Evidence: Simulator first screen, starter chips and judge view (2026-10-18)

Demo mode only (`MOCK_BEDROCK=true`, synthetic farm, rule-based host). No AWS call. Screenshots are from the real
Simulator and MCP server (two processes, started by hand and stopped by PID), driven in headless Chrome over its
DevTools protocol, viewport 1024x600 (the two device-screen shots are clipped to the 1024x600 screen at scale 1).
Restyled the same day: the starters and the Yes/No taps are large colour tiles in the colours of the farmer's pilot page
(pastel tints, large Telugu label, English gloss under it); the banner, the device frame and the "Simulator" name are
unchanged. At 1920x1080 and 1366x768 the device sits left and the conversation right, so the Yes/No taps stay on screen
after the longest answer; the 1024x600 shots below show the one-column layout of a small window.
They show what the page does; they do not show Telugu speech (there is none: the microphone is the browser's
English speech recognition, and spoken answers are English) and nothing here ran on Alexa+.

| File | What it shows |
|---|---|
| `01_first-screen_chips_1024x600.png` | The banner, neutral device labels (Smart display / Speaker), the judge-view switch, and five starter tiles: the Telugu question large, its English gloss under it |
| `02_telugu-answer_judge-view-on_1024x600.png` | The "Help" answer on the device screen: the Telugu answer large, its English side small under it |
| `03_telugu-answer_judge-view-off_1024x600.png` | The same answer with the judge view off: Telugu only; the screen does not overflow |
| `04_vet-offer_yes-no-taps_1024x600.png` | The health-check chip's answer ends with the vet-summary offer; the Yes and No tiles appear under the ask box (each is an existing catalog pair); the window is scrolled to the end of the page |
| `05_developer-panel_mcp-wire_1024x600.png` | The developer panel, now a right-hand drawer that pushes the page left instead of covering it, with the `tools/call` JSON-RPC request and response of the chip's turn |

The chips send these English sentences (the demo host reads English text only): "How is the farm?", "When to sell?",
"Today's briefing", "Help" (each is the chip's own English gloss) and "Shed two birds are coughing and not eating" for
the "Health check" chip. Each is run in `tests/contract/test_simulator_starters.py` against the live demo host.

Left out because the demo host does not answer them: the schedule questions ("What day is it today?", "When is the next
vaccination?"; they need the pilot farm file) and "Birds after the check" (answered only once a follow-up is due).

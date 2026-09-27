# Bundled font: Noto Sans Telugu

The MCP App cards show Telugu, and a card cannot load fonts from the network (the MCP Apps default CSP allows no
external requests). So the font ships with the repo and `scripts/build_cards.py` inlines it into each card.

| Item | Value |
|---|---|
| Font | Noto Sans Telugu, version 2.005, Regular (400) and Bold (700), OpenType CFF (`full/otf/`) |
| Source | Official release `NotoSansTelugu-v2.005` (2023-09-28), https://github.com/notofonts/telugu/releases/tag/NotoSansTelugu-v2.005 |
| Downloaded | 2026-09-27; release zip SHA-256 `3553e00ca341dc06f4a143c604dd93a1342553169b5a06dc8b0ff50ab6eba0a2` |
| License | SIL Open Font License 1.1 (`OFL.txt`, copied unchanged from the release; "Copyright 2022 The Noto Project Authors") |

File checksums (SHA-256):

```
27faca3bb7caa65ab7f71f10ff6f834cc6322013b1722c9d23509e95644f4e51  NotoSansTelugu-Regular.otf
2f646169cb7db3be4985c6ece7ce3ee63a148a6a9dab1383d39a9d255786eab2  NotoSansTelugu-Bold.otf
481c72a8f1b4f645a7e6b10326be41b2da2c15cb470ff48a07fab773eed00102  OFL.txt
```

OFL 1.1 allows bundling and embedding the font with software, including commercial software, provided the
license travels with it and the font is not sold by itself. The files are unmodified. Inside the cards the font
is declared under a private family name ("Noto Sans Telugu CT") only so the card can detect whether this bundled
copy loaded; the font data itself is not changed. (The release's copyright statement declares no Reserved Font
Name, checked 2026-09-27.)

# Data Sources and Provenance

Every number CluckTalk uses is either **sourced** (cited below), **computed** (formula shown in code), **fictional demo data** (`data/seed/`), or **simulated** (market price, supplier). Each output labels which one applies.

| Used for | Source | How used | File |
|---|---|---|---|
| Ross 308 target weight, daily intake, cumulative intake by age | Aviagen, *Ross 308 / 308 FF Broiler: Performance Objectives 2022*, As-Hatched table (metric). https://aviagen.com/assets/Tech_Center/Ross_Broiler/RossxRoss308-BroilerPerformanceObjectives2022-EN.pdf (retrieved 2026-09-27) | Weekly checkpoints only (days 0, 1, 7 … 56), linearly interpolated by CluckTalk. **Citation only**: the PDF disallows copying, so the full table is never reproduced | `data/reference/ross308_2022_as_hatched_weekly.json` |
| Broiler feed phases (pre-starter 0–2 wk, starter 3–4 wk, finisher 5–6 wk) | TNAU Agritech Portal, Broiler Management. http://www.agritech.tnau.ac.in/expert_system/poultry/Broiler%20Management.html (retrieved 2026-09-27) | Phase names and age boundaries | `src/clucktalk/domain/feed.py` |
| Cumulative mortality thresholds 5% / 10% | jebas.org/ojs/index.php/jebas/article/view/832 (2023): farms < 5% mortality more profitable than > 10% (docs/DESIGN.md §9) | Watch / alert thresholds | `src/clucktalk/domain/thresholds.py` |
| Mortality spike, feed-drop, weight, FCR-margin, laying-drop thresholds | **CluckTalk heuristics**, not veterinary standards | Early-warning flags; user text must not present them as standards | `src/clucktalk/domain/thresholds.py` |

## Breeds without a cited curve
- **Cobb 430**: no public performance table found (search 2026-09-27). Weight- and feed-vs-target comparisons are refused with a clear message (`NoReferenceCurve`), never substituted.
- **BV-300** (layer): no public standard found yet. Layer status and feed plans use the house's own records only.

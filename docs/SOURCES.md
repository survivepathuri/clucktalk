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

## Sources for planned features (docs/DESIGN.md §13), checked 2026-09-27
Status: **verified** = fetched and the cited point was found in the text; **not verified** = could not be read.
Nothing below is used in code yet. When it is, the exact passage and the file that uses it are added here.

| Topic | Source | Status and what it supports |
|---|---|---|
| Contract broiler farming in India (integrator supplies chicks, feed, medicines, advisory; farmer paid a growing charge; farm record keeping) | P.V.K. Sasidhar and M. Suvedi, *Integrated Contract Broiler Farming: An Evaluation Case Study in India*, MEAS Evaluation Report, USAID, June 2015 (Karnataka, Telangana, Andhra Pradesh). meas.illinois.edu/wp-content/uploads/2015/04/MEAS-EVAL-2015-Broiler-India-long-Sasidhar-Suvedi-June-2015.pdf | **Verified.** Describes contract vs non-contract farming and "a complete and accurate farm record-keeping system" as a feature of contract farming. Contains one company's 2015 example terms (growing charge Rs 4.00/kg, standard FCR 1.85, mortality allowed 5%): usable only as a labeled 2015 example, never as current terms. |
| Contract farming, payment per kg and farmer-borne losses (West Bengal) | Hennessey et al., *Broiler farming and antibiotic use through an agency theory lens. A case study from West Bengal, India*, PLOS ONE, **2025**. doi:10.1371/journal.pone.0314090 | **Verified** (journal page shows 2025). Payment per kg produced relative to a company standard; delays in lifting raise mortality and FCR at the farmer's cost. |
| Poultry value chain, contract integration | Springer chapter doi:10.1007/978-981-33-4268-2_7 | **Not verified**: the page redirects to a login. Not cited until read. |
| Example vaccination schedule (Marek's day 1; ND/LaSota 4–7 days; IBD 11–13 days; broiler ND booster 21–23 days; layer IB, Fowl Pox, R2B) | ReAct Group, *Disease Management & Vaccination Schedule* (A3 poster, 2021). reactgroup.org/wp-content/uploads/2021/06/Disease-Management-_-Vaccination-Schedule_A3.pdf | **Verified.** Includes per-bird **doses**, which CluckTalk never relays. Its colour key (layers / broilers) appears inconsistent with the ages shown, one more reason the schedule must come from the farmer's vet or company. |
| Drinking-water vaccination: water free of disinfectants incl. chlorine; skim milk stabiliser 20–30 min before the vaccine; water withheld 1–2 h; consumed within 2–3 h | J.H. Breytenbach (Intervet), *Auditing Vaccine Application Procedures in Poultry*, The Poultry Site, 31 May 2005. thepoultrysite.com/articles/auditing-vaccine-application-procedures-in-poultry | **Verified** (quotes checked). |
| Chlorine as low as 1 ppm can inactivate vaccine; skim milk 2–5 g/L; about 2 h drinking period; about 60 min water withdrawal | Hudson, Saravana Kumar, Tomar, Dhakare, *Drinking Water Vaccination in Chicken*, SR Publication, 3 Jan 2025. www.srpublication.com/drinking-water-vaccination-in-chicken/ | **Verified.** Does **not** state how many days before to stop disinfectants. |
| Sanitisers (chlorine, peroxide, organic acids) removed at least 24 h before and after; stabiliser; water withheld 2–3 h; vaccine consumed in 1–2 h | Elanco, *Best Practices in Water Vaccination*, 16 June 2025. farmanimal.elanco.com/us/poultry/article/best-practices-water-vaccination | **Verified** (quotes checked). |

Sources disagree on water withholding (about 1 h to 3 h) and the drinking window (1–2 h to 2–3 h). CluckTalk will present these as ranges with sources and defer to the vaccine label and the farmer's vet or company.

## Telugu wording review
Telugu strings are reviewed by a native speaker. Status is tracked **per string** in `data/i18n/telugu_approvals.json` and shown in `docs/TELUGU_REVIEW.md` (pending strings first). An approval covers one exact English + Telugu pair; any new or changed string, in either language, is pending until reviewed again. Word choices follow the glossary in `docs/DESIGN.md` §8.1.

| Date | Reviewer | Scope |
|---|---|---|
| 2026-09-27 | Pathuri Venkateswara Rao (native Telugu speaker) | All 82 Telugu strings in the code at that date (80 unique English + Telugu pairs), after applying the reviewer's corrections and glossary |

## Device sizes and visual guidance for cards (checked 2026-09-27)
| Used for | Source | What it supports |
|---|---|---|
| Echo Show 1024×600 preset | Amazon, *Viewport Object in the Data-binding Context* (APL). https://developer.amazon.com/en-US/docs/alexa/alexa-presentation-language/apl-viewport-property.html | "the viewport object on the original Echo Show reports": width 1024, height 600, pixelWidth 1024, pixelHeight 600, dpi 160 |
| Echo Show 960×600 dp preset | Amazon, *Alexa.Presentation.APL Interface Reference*. https://developer.amazon.com/en-US/docs/alexa/alexa-presentation-language/apl-interface.html | Example HUB device viewport: pixelWidth 1280, pixelHeight 800, dpi 213 (= 960×600 dp) |
| 960×480 dp preset (Echo Show 5 class) | Amazon, *Viewport Profiles* and *Select the Viewport Profiles Your Skill Supports* (APL) | `hubLandscapeSmall`: width 960–1279 dp, height 100–599 dp; the Echo Show 5 is named as a device with this profile. The exact Echo Show 5 size was not found on the pages read, so the preset is labeled as a profile-range size |
| Phone 390×844 preset | none (typical phone size) | Labeled "not from Amazon docs" in the Simulator |
| Legibility, cross-modal and accessibility checks | Amazon, *Design Guide: Test Your Add-on Customer Experience*. https://developer.amazon.com/docs/alexaplus/add-ons/mcp-addon-test-addon-cx.html; *Functional Requirements*. https://developer.amazon.com/docs/alexaplus/add-ons/functional-requirements.html | Text readable at arm's length; no voice/screen data contradictions; no stale previous-turn content; Echo Show (primary), Alexa app, web and voice-only devices; colour correction/inversion must not hide content; "still working" message when slow |
| MCP Apps on Alexa+ | Amazon, *Alexa+ MCP Toolkit Overview*. https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-overview.html | Alexa+ supports the MCP Apps extension ("render interactive UIs for MCP tools directly in the conversation view"). No container sizes or supported-message list published (FRICTION_LOG FL-009) |
| Bundled Telugu font | Noto Sans Telugu 2.005, https://github.com/notofonts/telugu (SIL Open Font License 1.1) | License and checksums in `ui/fonts/README.md` |

# Draft add-on listing (placeholder, not deployed)

`addon.json` in this folder is a **draft example**. Read this before using any of it.

- The structure was taken from the `addon.json` schema reference on Amazon's Alexa+ MCP QuickStart page (last updated
  Jul 10, 2026), as read by the project owner: `manifestVersion` "1.0", `storeListing` (`distributionCountries`,
  `locales` with `name`, `shortDescription`, `fullDescription`, `examplePhrases`, `privacyAndCompliance`,
  `mediaAssets`) and `integrations` (an MCP integration with an HTTPS endpoint).
- **Nothing was deployed or submitted.** The Alexa AI CLI was not used (FL-024).
- Every URL and image is a placeholder on `example.invalid`. The icons and the carousel image do not exist yet.
- `distributionCountries` is `["US"]`, as in Amazon's example. Whether other countries such as IN are allowed is an
  open question (FR-008).
- Where the documented description left the exact JSON shape open, this draft chose one: `locales` is an object keyed
  by locale code, and `icons.light` and `carouselImages` are arrays of objects. Check these against the Developer
  Console before any real use.
- Only the field names, counts and length limits are checked, by `tests/harness/test_addon_draft.py` and by
  `python tasks.py readiness`. That is not an Amazon validation.
- The text was written from facts already stated in this repository's README and docs, and the four example phrases are phrases the
  `get_help` tool gives. It claims nothing that is not verified there (the add-on has not run on an Alexa+ device).

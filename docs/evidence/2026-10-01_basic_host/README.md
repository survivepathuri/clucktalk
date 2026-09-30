# MCP Apps host test: ext-apps basic-host against CluckTalk (part 1: setup + plain-HTTP checks)

Status: **setup and HTTP-level checks done; the four cards have NOT yet been looked at in a browser.** Nothing below
claims a card renders in basic-host. Part 2 (by eye) fills in the "Still to check" table.

## What was run (Windows 11, outside this repo)

| Item | Value |
|---|---|
| Host under test | `modelcontextprotocol/ext-apps`, `examples/basic-host` (package 2.0.3) |
| ext-apps commit | `82221c0c8ce7661efa6771c9d461511b1650495f` ("Bump version to 2.0.3 (#794)", 2026-09-25), shallow clone |
| Clone location | `%TEMP%\ext-apps-host` (never inside this repo, never committed) |
| Node / npm | 24.15.0 / 11.12.1 |
| bun | 1.3.10 (the repo's own devDependency `bun ^1.2.21`; needed by its build and its `serve` script) |
| Its MCP client | `@modelcontextprotocol/client` 2.0.0 |
| CluckTalk | commit `6962e16` (extra-origin + CORS layer), `python tasks.py serve`, mock mode, 127.0.0.1:8765 |

Commands (PowerShell shown; cmd users set the variables with `set NAME=value` instead):

```
git clone --depth 1 https://github.com/modelcontextprotocol/ext-apps $env:TEMP\ext-apps-host
cd $env:TEMP\ext-apps-host
npm ci --ignore-scripts --no-audit --no-fund
#   bun's own postinstall is the only install script that was run (see "Deviations")
cd node_modules\bun ; node install.js ; cd ..\..
npm run build                                   # root library (schemas, snippets, bun build)
cd examples\basic-host
$env:NODE_ENV='development' ; npm run build     # tsc --noEmit + vite builds (index.html, sandbox.html)
# in the CluckTalk repo, terminal 1:
$env:MOCK_BEDROCK='true'
$env:CLUCKTALK_ALLOWED_ORIGINS='http://localhost:8080,http://127.0.0.1:8080'   # this test only, never a default
python tasks.py serve
# terminal 2, in examples\basic-host:
$env:SERVERS='["http://127.0.0.1:8765/mcp"]'
npm run serve                                   # = bun --watch serve.ts ; host :8080, sandbox :8081
```

No `AWS_*` variables were set in the shell; the one credential-like variable (`CLAUDE_CODE_MESSAGING_TOKEN`) was
removed from the environment of every npm/node/bun process. No `-g` installs, no admin rights.

### Deviations from "documented" (and why)
- The documented `npm install` runs the root `prepare` script and bun's postinstall. I used `--ignore-scripts` first.
  The build then failed: `@modelcontextprotocol/ext-apps` resolves to the repo root (an unbuilt workspace link) and
  the build needs `bun`, whose npm package refuses to run without its postinstall ("Bun's postinstall script was not
  run"). So I ran **only** `node_modules/bun/install.js` (official oven-sh script; it just puts the already-installed
  platform binary in place) and then `npm run build`. The root `prepare` script and husky were not run.
- `npm run serve` is the documented start (`bun --watch serve.ts`); nothing else was changed in the clone
  (`npm run build` regenerates schema files inside the clone only).

## Checked over plain HTTP (no browser), origin `http://localhost:8080`

- Basic-host: `GET :8080/index.html` 200, `GET :8080/api/servers` returns `["http://127.0.0.1:8765/mcp"]`,
  `GET :8081/sandbox.html` 200. CluckTalk listens on 127.0.0.1:8765 only (`netstat`).
- Preflight from the allowed origin: `204`, `access-control-allow-origin: http://localhost:8080` (exact origin),
  `vary: Origin`, methods `POST, GET, DELETE, OPTIONS`, headers
  `content-type, accept, authorization, mcp-session-id, mcp-protocol-version`, no credentials header.
- `initialize` from the allowed origin: `200`, `mcp-session-id` present, `access-control-expose-headers: Mcp-Session-Id`.
- A disallowed origin (`http://evil.example`): `403 Invalid Origin header`, no CORS headers, for both the POST and the preflight.
- `server/discover` with `MCP-Protocol-Version: 2026-07-28` from the allowed origin: `400` (by design, CluckTalk targets
  2025-11-25) and the 400 carries the CORS headers, so a browser client can read it.

### Expected, read from the client's source (not yet seen in a browser)
The basic-host client first probes the stateless 2026-07-28 protocol with `server/discover`, sending the headers
`mcp-method` (and `mcp-name`), which our strict preflight does not allow. A browser will therefore block that probe
with an opaque `TypeError` and log a CORS error in the console. In
`@modelcontextprotocol/client/dist/index.mjs` (`classifyNetworkError`, line ~2397) a browser `TypeError` during the
probe is classified as "legacy", so the client falls back to the `initialize` handshake. **This CORS console error
is expected, not a failure**, but it needs confirming by eye. If the connection fails instead, the fix is to add
`mcp-method, mcp-name` to the allowed headers (a one-line change plus test).

## Still to check by eye (part 2)

Open `http://localhost:8080/`, choose server "CluckTalk", then per card: tool, arguments, **Call Tool**.
Pass means: the card renders its bilingual content; the Telugu font shows; the console shows no CSP errors from the
card; a tap that calls a tool works; the card follows the host's light/dark toggle.

| Card | Tool | Arguments | Seen OK? | Screenshot |
|---|---|---|---|---|
| Farm status | `get_farm_status` | `{}` | not yet | |
| Sell-day plan | `plan_sale` | `{"house": "shed 3"}` | not yet | |
| Daily briefing | `get_daily_briefing` | `{}` | not yet | |
| Health check | `start_health_check` | `{"house": "shed 2", "signs": ["coughing", "sneezing"]}` | not yet | |

Known risk to look at: basic-host's sandbox CSP versus the card's inlined `data:` font (friction log FL-007 found the
reference host allows `data:` fonts).

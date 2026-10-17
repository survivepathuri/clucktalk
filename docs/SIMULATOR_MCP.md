# How the Simulator speaks MCP

Hand-written (not generated). Part of the CluckTalk docs; the claims table is in the README.

The Simulator is a web app in two parts. The **browser page** (`src/clucktalk/simulator/static/app.js`) never speaks MCP: it posts the farmer's words to the Simulator's own backend (`app.js:333`, `fetch("/api/turn", ...)`). The **backend** is the MCP client. It sends `initialize` with protocolVersion 2025-11-25, then `notifications/initialized` and `tools/list` (`src/clucktalk/simulator/mcp_client.py:84-122`, class `McpClient.connect`), and a `tools/call` for each turn (`src/clucktalk/simulator/app.py:652`), as raw JSON-RPC over Streamable HTTP to `/mcp`. It stops with an error if the server negotiates any other version (`mcp_client.py:108`). The Simulator's developer panel shows the same wire.

Captured on 2026-10-17 on Windows by running `McpClient` (the Simulator's own client class) against `python tasks.py serve` in demo mode. Lines are shortened with `...`; the server also returned an `mcp-session-id` header on `initialize`, which the client sends on every later call.

```
POST /mcp  -> 200, 37 ms
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25",
 "capabilities":{"extensions":{"io.modelcontextprotocol/ui":{"mimeTypes":["text/html;profile=mcp-app"]}}},
 "clientInfo":{"name":"CluckTalk Simulator","version":"0.1.0"}}}
<- {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2025-11-25","capabilities":{"tools":{"listChanged":false},...},
 "serverInfo":{"name":"CluckTalk","title":"CluckTalk","version":"0.1.0"},"instructions":"CluckTalk is a voice farm manager ..."}}

POST /mcp  {"jsonrpc":"2.0","method":"notifications/initialized"}  -> 202

POST /mcp  -> 200, 8 ms
{"jsonrpc":"2.0","id":2,"method":"tools/list"}
<- {"jsonrpc":"2.0","id":2,"result":{"tools":[{"name":"get_farm_status","title":"Farm status",
 "_meta":{"ui":{"resourceUri":"ui://clucktalk/farm-status.html"}},...}, ...]}}      (14 tools)

POST /mcp  -> 200, 53 ms
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"get_farm_status","arguments":{"house":"shed two"}}}
<- {"jsonrpc":"2.0","id":3,"result":{"content":[{"type":"text","text":"House 2 needs attention now. Day 23, 3,883 birds, ..."}],
 "isError":false,"structuredContent":{"text_en":"...","text_te":"...",...}}}
```

The timings are one localhost run in demo mode, not a measurement; the latency figures are in `docs/RESULTS.md`, section 5.

## Voice input in the Simulator

Voice input uses the browser's built-in Web Speech API (`SpeechRecognition` or `webkitSpeechRecognition`, `src/clucktalk/simulator/static/app.js:62-69`) with the recognition language set to `en-IN`; the code does not request Telugu recognition, the browser sends the audio to its own online speech service, and the code lists no supported browsers (the microphone button is disabled where the API is missing). The transcript fills the text box and is sent as a normal turn. Builder-tested manually, not covered by automated tests; no recognition accuracy is claimed.

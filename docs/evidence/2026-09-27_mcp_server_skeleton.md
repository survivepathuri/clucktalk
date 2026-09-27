# MCP server skeleton: evidence (2026-09-27)

Real runs against `python tasks.py serve` on this machine (Windows 11, Python 3.13.15, `mcp==2.2.0`). Output pasted unedited except where marked.
Inspector: `@modelcontextprotocol/inspector@2.8.0` CLI mode (`mcp-inspector --cli`), installed outside the repo.

## 1. Server start (`python tasks.py serve`)
```
serve: MOCK_BEDROCK not set, so starting in DEMO DATA mode (MOCK_BEDROCK=true).
INFO:     Started server process [8724]
INFO:     Waiting for application startup.
INFO mcp.server.streamable_http_manager: StreamableHTTP session manager started
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8765 (Press CTRL+C to quit)
```
## 2. Bound to localhost only (`netstat -ano`)
```
TCP    127.0.0.1:8765         0.0.0.0:0              LISTENING       8724
```
## 3. Inspector: `tools/list --strict` (exit code in brackets)
```json
{
  "tools": [
    {
      "name": "get_help",
      "title": "What can you do?",
      "description": "Use when the farmer asks what CluckTalk can do, how to use it, or says 'help'. Takes no input. Returns a short spoken introduction and example questions for the farm tools that are available right now.",
      "inputSchema": {
        "type": "object",
        "properties": {},
        "title": "get_helpArguments"
      },
      "outputSchema": {
        "type": "object",
        "properties": {
          "text_en": {
            "title": "Text En",
            "type": "string"
          },
          "text_te": {
            "title": "Text Te",
            "type": "string"
          },
          "capabilities": {
            "items": {
              "$ref": "#/$defs/CapabilityOut"
            },
            "title": "Capabilities",
            "type": "array"
          }
        },
        "required": [
          "text_en",
          "text_te",
          "capabilities"
        ],
        "$defs": {
          "CapabilityOut": {
            "additionalProperties": false,
            "properties": {
              "tool_name": {
                "title": "Tool Name",
                "type": "string"
              },
              "title_en": {
                "title": "Title En",
                "type": "string"
              },
              "title_te": {
                "title": "Title Te",
                "type": "string"
              },
              "example_en": {
                "title": "Example En",
                "type": "string"
              }
            },
            "required": [
              "tool_name",
              "title_en",
              "title_te",
              "example_en"
            ],
            "title": "CapabilityOut",
            "type": "object"
          }
        },
        "additionalProperties": false,
        "title": "GetHelpOutput"
      },
      "annotations": {
        "readOnlyHint": true,
        "idempotentHint": true,
        "openWorldHint": false
      }
    }
  ]
}
[exit 0]
```
## 4. Inspector: `tools/call get_help`
```json
{
  "content": [
    {
      "type": "text",
      "text": "I'm CluckTalk, your poultry farm helper. My farm tools are still being set up, so right now I can only explain what I do."
    }
  ],
  "structuredContent": {
    "text_en": "I'm CluckTalk, your poultry farm helper. My farm tools are still being set up, so right now I can only explain what I do.",
    "text_te": "నేను కోడి మిత్ర, మీ కోళ్ల ఫారం సహాయకుడిని. నా ఫారం పనిముట్లు ఇంకా సిద్ధమవుతున్నాయి, కాబట్టి ప్రస్తుతం నేను ఏమి చేస్తానో మాత్రమే చెప్పగలను.",
    "capabilities": []
  },
  "isError": false
}
[exit 0]
```
## 5. Inspector forced to the stateless 2026-07-28 era is refused (CluckTalk targets 2025-11-25)
```
{"error":{"code":"error","message":"Version negotiation failed: the server did not offer pinned protocol version 2026-07-28 via server/discover (no fallback in pin mode)"}}
[exit 1]
```
## 6. Raw `initialize` (curl): negotiated version and session header (`instructions` shortened)
```
HTTP/1.1 200 OK
content-type: application/json
mcp-session-id: 79db1afafe844ae894241ee2899ce78a
{"jsonrpc":"2.0","id":1,"result":{"capabilities":{"experimental":{},"prompts":{"listChanged":false},"resources":{"listChanged":false,"subscribe":false},"tools":{"listChanged":false}},"instructions":"CluckTalk is a voice farm manager for po…","protocolVersion":"2025-11-25","serverInfo":{"name":"CluckTalk","title":"CluckTalk","version":"0.1.0"}}}
```
## 7. Transport rejections
```
foreign Origin (http://evil.example):        HTTP 403
other localhost port Origin (:6666):         HTTP 403
allowed Origin (http://localhost:8765):      HTTP 200
unknown Mcp-Session-Id:                      HTTP 404
MCP-Protocol-Version: 2026-07-28:            HTTP 400  {"jsonrpc": "2.0", "id": null, "error": {"code": -32600, "message": "Unsupported MCP-Protocol-Version. This server uses 2025-11-25 via initialize."}}
```
## 8. Error contract on the wire: `get_help` with bad arguments
```json
{"jsonrpc":"2.0","id":5,"result":{"content":[{"type":"text","text":"Sorry, I didn't catch all the details for that. Please say that again with a little more detail."}],"structuredContent":{"error":{"message_en":"Sorry, I didn't catch all the details for that.","message_te":"క్షమించండి, దానికి కావలసిన వివరాలు పూర్తిగా అందలేదు.","next_step_en":"Please say that again with a little more detail.","next_step_te":"దయచేసి కొంచెం ఎక్కువ వివరాలతో మళ్ళీ చెప్పండి."}},"isError":true}}
```

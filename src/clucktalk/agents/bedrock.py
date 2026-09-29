"""Live engine: Amazon Nova via the Bedrock Runtime ``Converse`` API (boto3; docs/VERSIONS.md).

One forced tool call per request (``toolConfig.toolChoice.tool``), ``temperature 0``, the agent's own
``maxTokens``. Verified against Nova 2 Lite on 2026-09-29 before use (docs/AWS_SETUP.md §5.3, FRICTION_LOG
FL-020): the forced tool call works with text and with image input.
"""

from __future__ import annotations

import logging
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from clucktalk.agents.model import ModelError, ModelReply, ModelRequest

logger = logging.getLogger("clucktalk.agents")


class NovaModel:
    engine = "nova"

    def __init__(self, client: Any, model_id: str) -> None:
        """``client`` is a boto3 ``bedrock-runtime`` client (tests pass one wrapped in a botocore Stubber)."""
        self._client = client
        self.model_id = model_id

    def invoke(self, request: ModelRequest) -> ModelReply:
        try:
            resp = self._client.converse(
                modelId=self.model_id,
                system=[{"text": request.system}],
                messages=[{"role": "user", "content": [{"text": request.user_text}]}],
                toolConfig={
                    "tools": [
                        {
                            "toolSpec": {
                                "name": request.tool_name,
                                "description": request.tool_description,
                                "inputSchema": {"json": request.schema},
                            }
                        }
                    ],
                    "toolChoice": {"tool": {"name": request.tool_name}},
                },
                inferenceConfig={"maxTokens": request.max_tokens, "temperature": 0},
            )
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "ClientError")
            raise ModelError(f"Bedrock {code} for agent {request.agent}") from exc
        except BotoCoreError as exc:
            raise ModelError(f"Bedrock call failed for agent {request.agent}: {type(exc).__name__}") from exc
        usage = resp.get("usage", {})
        content = resp.get("output", {}).get("message", {}).get("content", [])
        tool_uses = [c["toolUse"] for c in content if "toolUse" in c and c["toolUse"].get("name") == request.tool_name]
        if not tool_uses:
            raise ModelError(
                f"no tool call in the reply for agent {request.agent} (stopReason {resp.get('stopReason')})"
            )
        return ModelReply(
            data=tool_uses[0].get("input"),
            engine=self.engine,
            model_id=self.model_id,
            input_tokens=int(usage.get("inputTokens", 0)),
            output_tokens=int(usage.get("outputTokens", 0)),
            latency_ms=int(resp.get("metrics", {}).get("latencyMs", 0)),
        )

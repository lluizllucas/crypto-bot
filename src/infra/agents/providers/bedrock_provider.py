"""
Provedor AWS Bedrock — wraps boto3 converse API para uso pelo trade_agent.
"""

import json
import logging

import boto3

from src.config import BEDROCK_MODEL_ID, BEDROCK_REGION

log = logging.getLogger("bot")

_bedrock = boto3.client("bedrock-runtime", region_name=BEDROCK_REGION)


def to_bedrock_tools(openai_tools: list) -> list:
    """Converte schemas de tools no formato OpenAI para o formato Bedrock."""
    result = []
    for t in openai_tools:
        fn = t["function"]
        result.append({
            "toolSpec": {
                "name":        fn["name"],
                "description": fn.get("description", ""),
                "inputSchema": {"json": fn["parameters"]},
            }
        })
    return result


def sanitize(text: str) -> str:
    """Sanitiza caracteres Unicode problematicos em mensagens de log."""
    replacements = {
        "‑": "-", "‒": "-", "–": "-", "—": "-",
        "‘": "'", "’": "'", "“": '"', "”": '"',
        "…": "...", "·": ".",
    }
    for char, rep in replacements.items():
        text = text.replace(char, rep)
    return text


class BedrockProvider:
    """Wrapper sobre boto3 Bedrock converse API."""

    def __init__(self, max_tokens: int = 2048, temperature: float = 0.3):
        self.max_tokens = max_tokens
        self.temperature = temperature

    def converse(
        self,
        system:  str,
        messages: list,
        tools:   list,
    ) -> dict:
        """
        Chama a API Bedrock converse e retorna o response dict completo.
        Raises on error — caller handles retries.
        """
        return _bedrock.converse(
            modelId=BEDROCK_MODEL_ID,
            system=[{"text": system}],
            messages=messages,
            toolConfig={"tools": tools},
            inferenceConfig={
                "maxTokens":   self.max_tokens,
                "temperature": self.temperature,
            },
        )


class BedrockToolCall:
    """Adapta tool use do Bedrock para a interface esperada por parse_tool_calls."""

    class _Function:
        def __init__(self, name: str, arguments: str):
            self.name = name
            self.arguments = arguments

    def __init__(self, tool_use: dict):
        self.function = self._Function(
            name=tool_use["name"],
            arguments=json.dumps(tool_use["input"]),
        )

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from typing import Any
from urllib.request import Request, urlopen


class LLMProvider(ABC):
    @abstractmethod
    def structured_completion(self, system: str, prompt: str) -> dict[str, Any]:
        raise NotImplementedError


class MockLLMProvider(LLMProvider):
    def structured_completion(self, system: str, prompt: str) -> dict[str, Any]:
        return {"mode": "mock", "instruction": "Use the deterministic Investigator service for evidence and RCA."}


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self) -> None:
        self.base_url = os.environ["LLM_BASE_URL"].rstrip("/")
        self.api_key = os.environ["LLM_API_KEY"]
        self.model = os.environ["LLM_MODEL"]

    def structured_completion(self, system: str, prompt: str) -> dict[str, Any]:
        request = Request(f"{self.base_url}/chat/completions", data=json.dumps({
            "model": self.model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
        }).encode(), headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"})
        with urlopen(request, timeout=30) as response:
            return json.loads(json.loads(response.read())["choices"][0]["message"]["content"])


def get_llm_provider() -> LLMProvider:
    if os.getenv("MOCK_LLM", "true").lower() == "true" or not os.getenv("LLM_API_KEY"):
        return MockLLMProvider()
    return OpenAICompatibleProvider()
from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any


class ModelClient:
    """Small center.model-compatible client with mock and Ollama backends."""

    def __init__(self, profiles_path: Path, profile: str = "novel_write") -> None:
        self.profiles = json.loads(profiles_path.read_text(encoding="utf-8"))
        self.profile_name = profile
        self.profile = self.profiles[profile]
        self.active_model = self.profile.get("model", "mock")

    def generate(self, prompt: str, system: str = "") -> str:
        backend = self.profile.get("backend", "mock")
        if backend == "ollama":
            return self._generate_ollama(prompt, system)
        return self._generate_mock(prompt, system)

    def _generate_ollama(self, prompt: str, system: str) -> str:
        base_url = self.profile.get("base_url", "http://127.0.0.1:11434").rstrip("/")
        payload = {
            "model": self.profile["model"],
            "prompt": prompt,
            "system": system,
            "stream": False,
            "options": self.profile.get("options", {}),
        }
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{base_url}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.profile.get("timeout_sec", 120)) as response:
            result = json.loads(response.read().decode("utf-8"))
        return result.get("response", "")

    def _generate_mock(self, prompt: str, system: str) -> str:
        return f"[mock-generation]\nSYSTEM:\n{system[:240]}\n\nPROMPT:\n{prompt[:1200]}"


def load_prompt(path: Path, **values: Any) -> str:
    template = path.read_text(encoding="utf-8")
    return template.format(**values)

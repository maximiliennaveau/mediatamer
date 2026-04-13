import os
import time
import requests
import subprocess
from typing import Optional, Dict, Any

import ollama


class OllamaClient:
    """Singleton client for Ollama interaction with performance optimizations."""

    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(OllamaClient, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        if self._initialized and config is None:
            return

        self.config = config or {}
        self.api_url = self.config.get("ollama-api-url", "http://localhost:11434")
        self.api_key = self.config.get("ollama-api-key")
        self.models_path = self.config.get("ollama-models-path")
        self.model = self.config.get("ollama-model")

        host = self.api_url if self.api_url else os.environ.get("OLLAMA_HOST")
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        self.client = ollama.Client(host=host, headers=headers)
        self.server_verified = False
        self.verified_models = set()
        self._initialized = True

    def ensure_server_running(self):
        """Check if Ollama server is running, and start it if not. Cached."""
        if self.server_verified:
            return

        try:
            # Quick probe
            requests.get(f"{self.api_url.rstrip('/')}/api/tags", timeout=2)
            self.server_verified = True
            return
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            pass

        print(f"Ollama server not found at {self.api_url}. Starting 'ollama serve'...")

        if not self.models_path:
            raise ValueError("Ollama models path not found in config.")
        if not self.api_key:
            raise ValueError("Ollama app key not found in config.")

        env = os.environ.copy()
        env["OLLAMA_MODELS"] = self.models_path
        env["OLLAMA_API_KEY"] = self.api_key

        try:
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                env=env,
            )

            # Wait for the server to become ready
            max_retries = 30
            for i in range(max_retries):
                try:
                    requests.get(f"{self.api_url.rstrip('/')}/api/tags", timeout=1)
                    print("Ollama server is now running.")
                    self.server_verified = True
                    return
                except requests.exceptions.RequestException:
                    time.sleep(1)
            print("Warning: Timed out waiting for Ollama server to start.")
        except Exception as e:
            print(f"Error starting Ollama server: {e}")

    def ensure_model_exists(self, model: str):
        """Ensure the model exists locally, pull it if not. Cached."""
        if model in self.verified_models:
            return

        self.ensure_server_running()

        try:
            resp = self.client.list()
            models = resp.models if hasattr(resp, "models") else resp.get("models", [])

            for m in models:
                m_name = getattr(m, "model", None) or getattr(m, "name", None)
                if not m_name and isinstance(m, dict):
                    m_name = m.get("model") or m.get("name")

                if m_name and (m_name == model or m_name.startswith(f"{model}:")):
                    self.verified_models.add(model)
                    return

            print(f"Model '{model}' not found. Pulling...")
            for progress in self.client.pull(model=model, stream=True):
                status = (
                    progress.get("status")
                    if isinstance(progress, dict)
                    else getattr(progress, "status", None)
                )
                if status:
                    print(f"Pulling {model}: {status}")
            self.verified_models.add(model)
        except Exception as e:
            print(f"Ollama Model Verification Error: {e}")

    def chat(
        self,
        prompt: str,
        model: Optional[str] = None,
        json_mode: bool = False,
        num_ctx: int = 16384,
        keep_alive: Any = -1,
    ) -> str:
        """Run a chat completion."""
        target_model = model or self.model
        if not target_model:
            raise ValueError("No model specified for AI execution.")

        self.ensure_model_exists(target_model)

        try:
            response = self.client.chat(
                model=target_model,
                messages=[{"role": "user", "content": prompt}],
                format="json" if json_mode else None,
                options={
                    "temperature": 0,
                    "num_ctx": num_ctx,
                },
                keep_alive=keep_alive,
            )
            return response["message"]["content"]
        except Exception as e:
            print(f"Ollama Library Error: {e}")
            # Fallback to direct request if library fails
            return self._generate_fallback(prompt, target_model, json_mode, num_ctx, keep_alive)

    def _generate_fallback(
        self, prompt: str, model: str, json_mode: bool, num_ctx: int, keep_alive: Any
    ) -> str:
        """Requests-based fallback for AI generation."""
        try:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            payload = {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "format": "json" if json_mode else None,
                "options": {"temperature": 0, "num_ctx": num_ctx},
                "keep_alive": keep_alive,
            }
            endpoint = f"{self.api_url.rstrip('/')}/api/generate"

            resp = requests.post(endpoint, json=payload, headers=headers, timeout=300)
            resp.raise_for_status()
            return resp.json().get("response", "")
        except Exception as e:
            print(f"Ollama Fallback Error: {e}")
            return ""


def run_ai(
    prompt: str,
    config: dict,
    json_mode: bool = False,
    num_ctx: int = 16384,
    keep_alive: Any = -1,
) -> str:
    """Entry point for running AI analysis. Uses optimized singleton client."""
    client = OllamaClient(config)
    return client.chat(
        prompt=prompt,
        json_mode=json_mode,
        num_ctx=num_ctx,
        keep_alive=keep_alive,
    )


def ensure_ollama_server_running(config: dict):
    """Compatibility wrapper for ensuring server is running."""
    OllamaClient(config).ensure_server_running()


def ensure_model_exists(model: str, client: Any = None, api_url: str = None):
    """Compatibility wrapper for ensuring model exists."""
    # If called with legacy arguments, we still try to use the singleton if possible
    OllamaClient().ensure_model_exists(model)


__all__ = ["run_ai", "OllamaClient", "ensure_ollama_server_running", "ensure_model_exists"]


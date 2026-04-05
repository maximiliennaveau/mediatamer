import os
import json
import time
import requests
import subprocess

from mediatamer.config import load_config

import ollama


def ensure_model_exists(model: str, client: ollama.Client = None, api_url: str = None):
    """Ensure the model exists locally in Ollama, pull it if not."""
    # Try via library if client is provided
    if client:
        try:
            resp = client.list()
            # Handle both ListResponse object and dict (older library versions)
            models = resp.models if hasattr(resp, "models") else resp.get("models", [])

            for m in models:
                # Handle both Model object and dict
                m_name = getattr(m, "model", None) or getattr(m, "name", None)
                if not m_name and isinstance(m, dict):
                    m_name = m.get("model") or m.get("name")

                if m_name and (m_name == model or m_name.startswith(f"{model}:")):
                    return

            print(f"Model '{model}' not found via library. Pulling...")
            for progress in client.pull(model=model, stream=True):
                status = (
                    progress.get("status")
                    if isinstance(progress, dict)
                    else getattr(progress, "status", None)
                )
                if status:
                    print(f"Pulling {model}: {status}")
            return
        except Exception as e:
            print(f"Ollama Library Check/Pull Error: {e}")

    # Fallback via Requests API
    if api_url:
        try:
            endpoint = api_url.rstrip("/")
            resp = requests.get(f"{endpoint}/api/tags", timeout=10)
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                if not any(
                    m["name"] == model or m["name"].startswith(f"{model}:")
                    for m in models
                ):
                    print(f"Model '{model}' not found via API. Pulling...")
                    pull_resp = requests.post(
                        f"{endpoint}/api/pull",
                        json={"name": model},
                        stream=True,
                        timeout=None,
                    )
                    for line in pull_resp.iter_lines():
                        if line:
                            data = json.loads(line)
                            status = data.get("status")
                            if status:
                                print(f"Pulling {model}: {status}")
            else:
                print(f"Failed to check models at {api_url}: {resp.status_code}")
        except Exception as e:
            print(f"Ollama API Check/Pull Error: {e}")


def ensure_ollama_server_running(
    api_url: str, models_path: str = None, api_key: str = None
):
    """Check if Ollama server is running, and start it if not."""
    try:
        # Quick probe to see if server responds
        requests.get(f"{api_url.rstrip('/')}/api/tags", timeout=1)
        return
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        pass

    print(f"Ollama server not found at {api_url}. Starting 'ollama serve'...")

    if not models_path:
        raise ValueError("Ollama models path not found in config.")
    if not api_key:
        raise ValueError("Ollama app key not found in config.")

    # Setup environment for the server
    env = os.environ.copy()
    print(f"Using models path from config: {models_path}")
    env["OLLAMA_MODELS"] = models_path

    print("Using API/App Key for authentication.")
    # If OLLAMA_APP_KEY is used in config, also set it for the subprocess env
    env["OLLAMA_API_KEY"] = api_key

    try:
        # Start the server in the background.
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            env=env,
        )

        # Wait for the server to become ready
        max_retries = 20
        for i in range(max_retries):
            try:
                requests.get(f"{api_url.rstrip('/')}/api/tags", timeout=1)
                print("Ollama server is now running.")
                return
            except requests.exceptions.RequestException:
                time.sleep(1)
        print("Warning: Timed out waiting for Ollama server to start.")
    except Exception as e:
        print(f"Error starting Ollama server: {e}")


def run_ai(prompt: str, json_mode: bool = False) -> str:
    """Run AI analysis using Ollama (library or requests fallback) and return raw string response.

    If json_mode is True, it sets the format to 'json' for Ollama.
    """
    # Load configuration
    config = load_config()

    model = config.get("ollama-model")
    api_url = config.get("ollama-api-url")
    api_key = config.get("ollama-api-key")
    models_path = config.get("ollama-models-path")

    # Ensure server is running
    ensure_ollama_server_running(
        api_url=api_url, models_path=models_path, api_key=api_key
    )

    # Ensure model exists
    host = api_url if api_url else os.environ.get("OLLAMA_HOST")
    try:
        # Client handles OLLAMA_API_KEY env var automatically in recent versions,
        # but we can also pass it in headers for maximum compatibility.
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        client = ollama.Client(host=host, headers=headers)
        ensure_model_exists(model, client=client)
        response = client.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            format="json" if json_mode else None,
            options={"temperature": 0, "num_ctx": 32768},
        )
        return response["message"]["content"]
    except Exception as e:
        print(f"Ollama Library Error: {e}")
        # If client creation failed or chat failed, try API fallback
        ensure_model_exists(model, api_url=api_url)

    try:
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "format": "json" if json_mode else None,
            "options": {"temperature": 0, "num_ctx": 32768},
        }
        endpoint = api_url.rstrip("/")
        if not endpoint.endswith("/api/generate"):
            endpoint = f"{endpoint}/api/generate"

        resp = requests.post(endpoint, json=payload, headers=headers, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        return data.get("response", "")
    except Exception as e:
        print(f"Ollama Requests Fallback Error: {e}")
        return ""


__all__ = ["run_ai"]

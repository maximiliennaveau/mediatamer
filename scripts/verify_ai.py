#!/usr/bin/env python3
import os
import sys

# Add project root to sys.path to allow importing mediatamer
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mediatamer.ai import run_ai
from mediatamer.config import load_config


def main():
    print("--- AI Verification Script ---")

    # Load configuration
    config = load_config()
    print(f"DEBUG: Config keys found: {list(config.keys())}")

    # Check settings (prioritize env vars over config)
    model = os.environ.get("OLLAMA_MODEL") or config.get("ollama-model", "llama3.1")
    api_url = os.environ.get("OLLAMA_API_URL") or config.get(
        "ollama-api-url", "http://localhost:11434"
    )
    api_key = (
        os.environ.get("OLLAMA_API_KEY")
        or config.get("ollama-app-key")
        or config.get("ollama-api-key")
    )
    models_path = os.environ.get("OLLAMA_MODELS") or config.get("ollama-models-path")

    print(f"Configured Model: {model}")
    print(f"Configured API URL: {api_url}")
    if models_path:
        print(f"Configured Models Path: {models_path}")
    if api_key:
        suffix_len = min(len(api_key), 4)
        print(
            f"Configured API/App Key: {'*' * (len(api_key) - suffix_len) + api_key[-suffix_len:]}"
        )
    else:
        print("Configured API/App Key: [Not Set]")
    print("-" * 30)

    prompt = "Hello! Please reply with exactly 'AI is online and working!' to verify connection."
    print(f"Sending prompt: {prompt}")
    print(
        "NOTE: If the Ollama server is not running, it will be started automatically."
    )

    # Example of setting OLLAMA_MODELS from Python:
    # os.environ["OLLAMA_MODELS"] = "/path/to/your/models"

    try:
        response = run_ai(prompt)
        if response:
            print(f"AI Response: {response.strip()}")
            print("-" * 30)
            print("SUCCESS: AI integration is functional.")
        else:
            print("ERROR: AI returned an empty response.")
            print("-" * 30)
            sys.exit(1)
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        print("-" * 30)
        sys.exit(1)


if __name__ == "__main__":
    main()

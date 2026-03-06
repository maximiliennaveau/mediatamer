#!/usr/bin/env python3
import os
import sys

# Add project root to sys.path to allow importing mediatamer
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mediatamer.signals.ai import run_ai

def main():
    print("--- AI Verification Script ---")
    
    # Check environment variables
    model = os.environ.get("OLLAMA_MODEL", "llama3.1")
    api_url = os.environ.get("OLLAMA_API_URL", "http://localhost:11434")
    
    print(f"Configured Model: {model}")
    print(f"Configured API URL: {api_url}")
    print("-" * 30)
    
    prompt = "Hello! Please reply with exactly 'AI is online and working!' to verify connection."
    print(f"Sending prompt: {prompt}")
    print("NOTE: If the Ollama server is not running, it will be started automatically.")
    
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

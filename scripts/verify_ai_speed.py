import time
import sys
from mediatamer.ai import run_ai
from mediatamer.config import load_config

def verify_ai_performance():
    config = load_config()
    model = config.get("ollama-model")
    print(f"Using model: {model}")

    print("\n--- Call 1 (Initialization + Model Load) ---")
    start = time.time()
    resp1 = run_ai("Say 'Ready'", config)
    end = time.time()
    print(f"Response: {resp1}")
    print(f"Time taken: {end - start:.2f}s")

    print("\n--- Call 2 (Cached Check + In-Memory Model) ---")
    start = time.time()
    resp2 = run_ai("Say 'Swift'", config)
    end = time.time()
    print(f"Response: {resp2}")
    print(f"Time taken: {end - start:.2f}s")

    print("\n--- Call 3 (Verification of Speed) ---")
    start = time.time()
    resp3 = run_ai("Say 'Done'", config)
    end = time.time()
    print(f"Response: {resp3}")
    print(f"Time taken: {end - start:.2f}s")

if __name__ == "__main__":
    verify_ai_performance()

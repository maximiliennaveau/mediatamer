import os
import json
import requests
from typing import List, Dict

import ollama


def run_ai(prompt: str) -> str:
    """Run AI analysis using Ollama (library or requests fallback) and return raw string response."""
    model = os.environ.get("OLLAMA_MODEL", "llama3")
    api_url = os.environ.get("OLLAMA_API_URL", "http://localhost:11434")

    try:
        host = api_url if api_url else os.environ.get("OLLAMA_HOST")
        client = ollama.Client(host=host)
        response = client.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0},
        )
        return response["message"]["content"]
    except Exception as e:
        print(f"Ollama Library Error: {e}")

    try:
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0},
        }
        endpoint = api_url.rstrip("/")
        if not endpoint.endswith("/api/generate"):
            endpoint = f"{endpoint}/api/generate"

        resp = requests.post(endpoint, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        return data.get("response", "")
    except Exception as e:
        print(f"Ollama Requests Fallback Error: {e}")
        return ""


def discriminate_episodes(
    subtitle_content: str, episodes: List[Dict]
) -> Dict[int, float]:
    """
    Compare subtitles against all candidate episodes at once.
    Returns a mapping of episode_number -> score (0.0 to 1.0).
    """
    if not subtitle_content or not episodes:
        return {}

    # 1. Prepare candidate overviews
    candidates_text = ""
    for ep in episodes:
        num = ep.get("episode_number", "?")
        name = ep.get("name", "Unknown")
        overview = ep.get("overview", "No description available.")
        candidates_text += f"Candidate {num} ({name}): {overview}\n\n"

    # 2. Build Prompt
    prompt = f"""You are an expert TV show episode matcher. I will provide you with the full content of extracted subtitles from a video file and a list of candidate episode descriptions.
Your task is to determine which candidate(s) match the subtitles.

Subtitle Content:
---
{subtitle_content[:100000]}
---

Candidate Episodes:
---
{candidates_text}
---

Return a JSON object where keys are the Candidate numbers (as integers) and values are similarity scores between 0.0 and 1.0. 
Example: {{"1": 0.9, "2": 0.1}}
Return ONLY the JSON object."""

    # 3. Run AI
    response = run_ai(prompt)
    try:
        # Clean up response in case of markdown blocks
        clean_response = response.strip()
        if clean_response.startswith("```json"):
            clean_response = clean_response[7:-3].strip()
        elif clean_response.startswith("```"):
            clean_response = clean_response[3:-3].strip()

        data = json.loads(clean_response)
        # Convert keys to int and values to float
        return {int(k): float(v) for k, v in data.items()}
    except Exception as e:
        print(f"Discrimination Parse Error: {e}\nResponse: {response}")
        return {}


__all__ = ["run_ai", "discriminate_episodes"]

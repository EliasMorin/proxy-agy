import json
import sys
import time
import urllib.request
import urllib.error

BASE_URL = "http://127.0.0.1:8000/v1"


def test_auth():
    print("\n--- 1. Testing GET /v1/auth/status ---")
    req = urllib.request.Request(f"{BASE_URL}/auth/status")
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            print(f"Status: {resp.status}")
            print(f"Auth Result: authenticated={data.get('authenticated')}, status={data.get('status')}")
            if data.get("login_url"):
                print(f"Login URL: {data.get('login_url')}")
    except urllib.error.URLError as e:
        print(f"Failed to connect to proxy: {e}")
        return False
    return True


def test_models():
    print("\n--- 2. Testing GET /v1/models ---")
    req = urllib.request.Request(f"{BASE_URL}/models")
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            print(f"Status: {resp.status}")
            models = [m["id"] for m in data.get("data", [])]
            print(f"Total models available: {len(models)}")
            print(f"Sample models: {models[:6]}")
    except urllib.error.URLError as e:
        print(f"Failed to connect to proxy: {e}")
        return False
    return True


def test_non_streaming():
    print("\n--- 3. Testing Non-Streaming POST /v1/chat/completions ---")
    payload = {
        "model": "gemini-3.7-flash-low",
        "messages": [
            {"role": "user", "content": "用一句话简单问好"}
        ],
        "stream": False
    }
    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            cost = time.time() - start
            print(f"Status: {resp.status} (took {cost:.2f}s)")
            content = data["choices"][0]["message"]["content"]
            print(f"Assistant Response:\n{content}")
            print(f"Usage: {data.get('usage')}")
    except urllib.error.URLError as e:
        print(f"Request failed: {e}")
        return False
    return True


def test_streaming():
    print("\n--- 4. Testing Streaming POST /v1/chat/completions ---")
    payload = {
        "model": "gemini-3.7-flash-low",
        "messages": [
            {"role": "system", "content": "You are a concise AI assistant."},
            {"role": "user", "content": "倒数 3 个数字 (3, 2, 1)"}
        ],
        "stream": True
    }
    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    print("Stream Output: ", end="", flush=True)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            for line in resp:
                line_str = line.decode("utf-8").strip()
                if not line_str or line_str.startswith(":"):
                    continue
                if line_str.startswith("data: "):
                    data_str = line_str[6:]
                    if data_str == "[DONE]":
                        print("\n[STREAM DONE]")
                        break
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk["choices"][0].get("delta", {})
                        if "content" in delta and delta["content"]:
                            print(delta["content"], end="", flush=True)
                    except json.JSONDecodeError:
                        pass
    except urllib.error.URLError as e:
        print(f"\nStream request failed: {e}")
        return False
    return True


if __name__ == "__main__":
    print("Testing Antigravity CLI OpenAI Proxy...")
    if not test_auth():
        print("\nPlease make sure the server is running on http://127.0.0.1:8000 (run `python3 main.py`)")
        sys.exit(1)
    test_models()
    test_non_streaming()
    test_streaming()
    print("\nAll tests completed successfully!")

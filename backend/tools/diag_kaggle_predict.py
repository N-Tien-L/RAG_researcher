"""Diagnostic helper: POST a /predict request to the Kaggle LitServe tunnel and print full response."""
import os
import sys
import json
import httpx


def main():
    url = os.getenv("KAGGLE_LLM_URL")
    api_key = os.getenv("KAGGLE_LLM_API_KEY")

    if not url:
        print("KAGGLE_LLM_URL is not set", file=sys.stderr)
        sys.exit(2)

    post_url = url.rstrip("/") + "/predict"
    payload = {
        "messages": [{"role": "user", "content": "Hello, what is your name?"}],
        "max_tokens": 64,
        "temperature": 0.2,
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    print(f"POST {post_url}")
    print("Payload:", json.dumps(payload))

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(post_url, json=payload, headers=headers)
            print("Status:", resp.status_code)
            print("Response headers:")
            for k, v in resp.headers.items():
                print(f"  {k}: {v}")
            print("Body:")
            try:
                print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
            except Exception:
                print(resp.text)
    except Exception as exc:
        print("Request failed:", exc, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

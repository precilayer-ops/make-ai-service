import asyncio
import json
import os
import sys

# Ensure make-ai-service directory is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from starlette.testclient import TestClient
from server import app


def test_root_endpoint():
    print("[1/5] Testing GET / ...")
    with TestClient(app) as client:
        res = client.get("/")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        data = res.json()
        assert data["service"] == "Make AI Service"
        assert "endpoints" in data
        assert data["endpoints"]["chat"] == "/api/v1/ai/chat"
        print("  [OK] Root endpoint passed:", data)


def test_health_endpoint():
    print("\n[2/5] Testing GET /health ...")
    with TestClient(app) as client:
        res = client.get("/health")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        data = res.json()
        assert data["status"] == "healthy"
        assert "services" in data
        print("  [OK] Health endpoint passed:", data)


def test_chat_non_streaming():
    print("\n[3/5] Testing POST /api/v1/ai/chat (Request/Response) ...")
    with TestClient(app) as client:
        # 1. Validation test (empty body should return 400 or 422)
        res_empty = client.post("/api/v1/ai/chat", json={})
        assert res_empty.status_code in (400, 422), f"Expected 400/422, got {res_empty.status_code}"
        print("  [OK] Validation for empty payload passed (status", res_empty.status_code, ")")

        # 2. Single prompt test
        res = client.post("/api/v1/ai/chat", json={
            "prompt": "What is CNC milling tolerance?",
            "temperature": 0.5
        })
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        data = res.json()
        assert "text" in data
        assert "latency_ms" in data
        assert data["instance"] in ("PIPL", "NDCS")
        print(f"  [OK] Single prompt response (latency: {data['latency_ms']}ms):")
        print("    Response text snippet:", data["text"][:120].replace("\n", " ") + "...")

        # 3. Multi-turn conversation test
        res_multiturn = client.post("/api/v1/ai/chat", json={
            "messages": [
                {"role": "user", "content": "Hello, I am asking about aluminum 6061."},
                {"role": "assistant", "content": "Aluminum 6061 is a versatile precipitation-hardened aluminum alloy."},
                {"role": "user", "content": "What is its standard machining speed?"}
            ],
            "system_instruction": "You are a CNC manufacturing quoting engineer."
        })
        assert res_multiturn.status_code == 200, f"Expected 200, got {res_multiturn.status_code}"
        multiturn_data = res_multiturn.json()
        assert "text" in multiturn_data
        print(f"  [OK] Multi-turn history response (latency: {multiturn_data['latency_ms']}ms):")
        print("    Response text snippet:", multiturn_data["text"][:120].replace("\n", " ") + "...")


def test_chat_stream():
    print("\n[4/5] Testing POST /api/v1/ai/chat/stream (SSE Streaming) ...")
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/ai/chat/stream",
            json={"prompt": "Stream test: Quote for 50 pieces of SS304 shaft"}
        )
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")

        chunks = []
        full_text = ""
        done_seen = False

        for line in response.iter_lines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("data: "):
                payload = json.loads(line[6:])
                chunks.append(payload)
                full_text += payload.get("text", "")
                if payload.get("done") is True:
                    done_seen = True

        assert len(chunks) > 0, "No stream chunks received"
        assert done_seen, "Did not receive done: true termination chunk"
        print(f"  [OK] SSE streaming passed! Received {len(chunks)} chunks.")
        print("    Streamed text snippet:", full_text[:120].replace("\n", " ") + "...")


def test_chat_stream_get_test():
    print("\n[5/5] Testing GET /api/v1/ai/chat/stream/test (Browser GET SSE) ...")
    with TestClient(app) as client:
        response = client.get("/api/v1/ai/chat/stream/test?prompt=Quick+stream+check")
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")

        has_data = False
        for line in response.iter_lines():
            if line.startswith("data: "):
                has_data = True
                break

        assert has_data, "No SSE data received from GET endpoint"
        print("  [OK] GET SSE test endpoint passed!")


if __name__ == "__main__":
    print("=" * 65)
    print("RUNNING MAKE AI SERVICE INTEGRATION TEST SUITE")
    print("=" * 65)
    test_root_endpoint()
    test_health_endpoint()
    test_chat_non_streaming()
    test_chat_stream()
    test_chat_stream_get_test()
    print("\n" + "=" * 65)
    print("ALL 5 TESTS PASSED SUCCESSFULLY!")
    print("=" * 65)

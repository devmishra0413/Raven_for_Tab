import sys
import os
import time

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from fastapi.testclient import TestClient

import api.routes.chat as chat_module
from api.server import app
from api.store import PendingMessage
from llm.cloud_client import ChatResult


class MockCloudClient:
    def __init__(self):
        self.call_count = 0

    def chat(self, payload):
        self.call_count += 1
        return ChatResult(content="Mock LLM response text.", model="mock-model")


def setup_function():
    chat_module._session = None
    mock_cloud = MockCloudClient()
    chat_module.set_cloud_client(mock_cloud)


def test_health_and_validation():
    client = TestClient(app, base_url="http://127.0.0.1:8000")

    r_health = client.get("/api/health")
    assert r_health.status_code == 200
    assert r_health.json()["ok"] is True

    r_empty = client.post("/api/chat/message", json={"text": ""})
    assert r_empty.status_code == 400
    assert r_empty.json()["code"] == "INVALID_INPUT"

    r_long = client.post("/api/chat/message", json={"text": "A" * 2001})
    assert r_long.status_code == 400
    assert r_long.json()["code"] == "INVALID_INPUT"


def test_preview_valid_send_and_duplicate_rejection():
    client = TestClient(app, base_url="http://127.0.0.1:8000")
    mock_cloud = MockCloudClient()
    chat_module.set_cloud_client(mock_cloud)

    r_prev = client.post("/api/chat/message", json={"text": "Hello assistant, please write a poem."})
    assert r_prev.status_code == 200
    data = r_prev.json()
    assert data["status"] == "preview"
    msg_id = data["message_id"]
    p_hash = data["preview"]["hash"]
    assert mock_cloud.call_count == 0

    # Wrong hash send
    r_bad_hash = client.post("/api/chat/send", json={"message_id": msg_id, "hash": "bad_hash_val"})
    assert r_bad_hash.status_code == 400
    assert r_bad_hash.json()["code"] == "HASH_MISMATCH"
    assert mock_cloud.call_count == 0

    # Valid send
    r_send = client.post("/api/chat/send", json={"message_id": msg_id, "hash": p_hash})
    assert r_send.status_code == 200
    assert r_send.json()["status"] == "sent"
    assert mock_cloud.call_count == 1

    # Duplicate send
    r_dup = client.post("/api/chat/send", json={"message_id": msg_id, "hash": p_hash})
    assert r_dup.status_code == 400
    assert r_dup.json()["code"] == "INVALID_STATE"
    assert mock_cloud.call_count == 1


def test_blocked_message_zero_cloud():
    client = TestClient(app, base_url="http://127.0.0.1:8000")
    mock_cloud = MockCloudClient()
    chat_module.set_cloud_client(mock_cloud)

    r_blocked = client.post("/api/chat/message", json={"text": "my password is secret123"})
    assert r_blocked.status_code == 200
    assert r_blocked.json()["status"] == "blocked"
    assert mock_cloud.call_count == 0


def test_cancellation_and_expiration():
    client = TestClient(app, base_url="http://127.0.0.1:8000")

    r_prev = client.post("/api/chat/message", json={"text": "Message to cancel"})
    msg_id = r_prev.json()["message_id"]

    r_canc = client.post("/api/chat/cancel", json={"message_id": msg_id})
    assert r_canc.status_code == 200
    assert r_canc.json()["status"] == "cancelled"

    r_send_canc = client.post("/api/chat/send", json={"message_id": msg_id, "hash": "any"})
    assert r_send_canc.status_code == 404

    # Expired message test
    store = chat_module.get_pending_store()
    sess = chat_module.get_session()
    pm_exp = PendingMessage(
        message_id="expired_id",
        clean_text="Expired text",
        payload={"messages": []},
        payload_hash="exp_hash",
        vault=sess.vault,
        status="preview",
        created_at=time.time() - 400,
        needs_permission=False
    )
    store.put(pm_exp)
    store.cleanup_expired()

    r_exp_send = client.post("/api/chat/send", json={"message_id": "expired_id", "hash": "exp_hash"})
    assert r_exp_send.status_code == 404


def test_permission_flow():
    client = TestClient(app, base_url="http://127.0.0.1:8000")
    mock_cloud = MockCloudClient()
    chat_module.set_cloud_client(mock_cloud)

    sess = chat_module.get_session()
    sess.vault.config = {"topics": {"health": {"keywords": ["doctor"], "action": "ask"}}}

    r_perm = client.post("/api/chat/message", json={"text": "I went to see my doctor."})
    assert r_perm.status_code == 200
    p_data = r_perm.json()
    assert p_data["status"] == "needs_permission"
    perm_id = p_data["message_id"]
    assert mock_cloud.call_count == 0

    # Permit allow=True
    r_allow = client.post("/api/chat/permit", json={"message_id": perm_id, "allow": True})
    assert r_allow.status_code == 200
    assert r_allow.json()["status"] == "preview"
    p_hash = r_allow.json()["preview"]["hash"]

    # Send permitted message
    r_send = client.post("/api/chat/send", json={"message_id": perm_id, "hash": p_hash})
    assert r_send.status_code == 200
    assert r_send.json()["status"] == "sent"
    assert mock_cloud.call_count == 1


def test_masked_history():
    client = TestClient(app, base_url="http://127.0.0.1:8000")
    r_hist = client.get("/api/chat/history")
    assert r_hist.status_code == 200
    assert "history" in r_hist.json()

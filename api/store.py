import json
import time
import uuid
import hashlib
import threading

from dataclasses import dataclass


@dataclass
class PendingMessage:
    message_id: str
    clean_text: str
    payload: list
    payload_hash: str
    vault: object
    status: str
    created_at: float
    needs_permission: bool


class PendingStore:
    """In-memory store for pending chat messages.

    The store is fully thread‑safe, keeps up to ``MAX_SIZE`` messages, and
    automatically removes entries older than ``TTL`` seconds when a new
    message is added.
    """

    TTL = 300  # seconds
    MAX_SIZE = 20

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # mapping: message_id -> PendingMessage
        self._store: dict[str, PendingMessage] = {}

    # ---------------------------------------------------------------------
    def _compute_hash(self, payload: list) -> str:
        """Return SHA‑256 hex digest of ``json.dumps(payload, sort_keys=True)``."""
        dump = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(dump).hexdigest()

    # ---------------------------------------------------------------------
    def put(self, msg: PendingMessage) -> None:
        """Insert or replace a message.

        Calls `_cleanup_expired` to enforce TTL and capacity.
        """
        with self._lock:
            now = time.time()
            self._cleanup_expired(now)
            # If the store is already at capacity, remove the oldest entry
            if len(self._store) >= self.MAX_SIZE:
                # deterministic removal: oldest ``created_at``
                oldest_id = min(self._store, key=lambda k: self._store[k].created_at)
                del self._store[oldest_id]
            self._store[msg.message_id] = msg

    # ---------------------------------------------------------------------
    def get(self, message_id: str) -> PendingMessage | None:
        with self._lock:
            msg = self._store.get(message_id)
            if msg is None:
                return None
            # TTL check: if expired, delete and return None
            if time.time() - msg.created_at >= self.TTL:
                del self._store[message_id]
                return None
            return msg

    # ---------------------------------------------------------------------
    def delete(self, message_id: str) -> None:
        with self._lock:
            self._store.pop(message_id, None)

    # ---------------------------------------------------------------------
    def cleanup_expired(self) -> None:
        """Public entry point for manual cleanup (though `put` does it automatically)."""
        with self._lock:
            now = time.time()
            self._cleanup_expired(now)

    def _cleanup_expired(self, now: float) -> None:
        # internal helper expects time already fetched
        to_delete = [mid for mid, msg in self._store.items() if now - msg.created_at >= self.TTL]
        for mid in to_delete:
            del self._store[mid]


# ------------------------------------------------------------------------
# Factory helper – creates a PendingMessage with the proper hash and id.


def create_pending_message(clean_text: str, payload: list, vault: object,
                            status: str, needs_permission: bool = False) -> PendingMessage:
    msg_id = str(uuid.uuid4())
    pm = PendingMessage(
        message_id=msg_id,
        clean_text=clean_text,
        payload=payload,
        payload_hash="",
        vault=vault,
        status=status,
        created_at=time.time(),
        needs_permission=needs_permission,
    )
    # compute hash now – should match stored payload
    pm.payload_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    return pm


# The rest of the application will use PendingStore and the create_pending_message function.

#__all__ = ["PendingStore", "PendingMessage", "create_pending_message"]

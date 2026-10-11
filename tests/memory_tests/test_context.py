# Tests for context privacy boundary (leak prevention)

import pytest
from memory.context import build_cloud_context
from memory.manager import MemoryManager
from privacy.vault import Vault


class TestCloudContext:
    def test_safe_context(self, mm):
        mm.add("Rahul's birthday is January 5", category="event")
        mm.add("My secret is 123456", sensitivity=1)

        ctx = build_cloud_context(mm, query="birthday")

        assert len(ctx) == 1
        assert "January 5" in ctx[0]
        assert "123456" not in " ".join(ctx), "Sensitive fact must not leak"

    def test_sanitize_integration(self, mm):
        mm.add_entity("Rahul", type="person", aliases=["राहुल"])
        mm.add("Rahul is my friend")

        ctx = build_cloud_context(mm, query="Rahul")

        assert len(ctx) > 0
        assert "Rahul" not in ctx[0], "Entity must be masked in context"
        assert "[PERSON_1]" in ctx[0]

    def test_vault_consistency(self, mm):
        mm.add_entity("Rahul", type="person", aliases=["राहुल"])
        mm.add("Rahul is my friend")
        shared_vault = Vault()

        # Build context
        ctx = build_cloud_context(mm, query="Rahul", vault=shared_vault)
        # Manually mask query with the same vault
        query_masked = shared_vault.mask("PERSON", "Rahul")

        assert "[PERSON_1]" in ctx[0]
        assert "[PERSON_1]" == query_masked, "Placeholders must be consistent"

    def test_blocked_context_fact(self, mm):
        # A fact that triggers topic guard should be dropped completely
        mm.add("Discussing a large personal loan", sensitivity=0)  # reaches sanitize() -> blocked
        
        ctx = build_cloud_context(mm, query="loan")
        assert len(ctx) == 0, "Blocked fact must be dropped, not masked"

    def test_sensitivity_leak_prevention(self, mm):
        # Add tons of facts, some sensitive, some not
        for i in range(10):
            mm.add(f"Non-sensitive fact {i}", sensitivity=0)
            mm.add(f"Sensitive secret {i}", sensitivity=1)
        
        ctx = build_cloud_context(mm, query="fact")
        
        ctx_text = " ".join(ctx)
        for i in range(10):
            assert f"Sensitive secret {i}" not in ctx_text

    def test_max_chars_limit(self, mm):
        for i in range(20):
            mm.add(f"This is a long fact that should fit in context budget {i}")
            
        ctx = build_cloud_context(mm, query="fact", max_chars=100)
        
        ctx_text = " ".join(ctx)
        assert len(ctx_text) <= 100
        # ensure we didn't cut a placeholder
        assert not any(part.count('[') > part.count(']') for part in ctx)
    def test_leak_scan(self, mm):
        """Scan all context for any raw value from the fake test data."""
        raw_values = ["Rahul", "9876543210", "123456"]
        mm.add_entity("Rahul", type="person")
        mm.add("My friend Rahul has phone 9876543210", sensitivity=0)  # must be masked
        mm.add("Note: secret 123456 friend", sensitivity=1)  # must be dropped

        ctx = build_cloud_context(mm, query="friend")
        
        ctx_text = " ".join(ctx)
        for v in raw_values:
            assert v not in ctx_text, f"Potential leak of raw value {v}!"

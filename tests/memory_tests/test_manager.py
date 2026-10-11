# Tests for MemoryManager - CRUD, dedupe, sensitivity, pending/confirmed

import pytest
from memory.manager import MemoryManager
from memory.exceptions import MemoryStoreError, FactNotFound, EntityNotFound, ValidationError


class TestAdd:
    def test_add_basic(self, mm):
        f = mm.add("Rahul's birthday is January 5")
        assert f.id > 0
        assert f.content == "Rahul's birthday is January 5"
        assert f.category == "other"
        assert f.status == "confirmed"
        assert f.source == "user"

    def test_add_with_category(self, mm):
        f = mm.add("Likes chai over coffee", category="preference")
        assert f.category == "preference"

    def test_add_with_explicit_sensitivity(self, mm):
        f = mm.add("Test fact", sensitivity=1)
        assert f.sensitivity == 1

    def test_add_auto_sensitivity_health(self, mm):
        f = mm.add("I take diabetes medicine daily")
        assert f.sensitivity == 1, "Health topic should auto-mark sensitive"

    def test_add_auto_sensitivity_phone(self, mm):
        f = mm.add("My phone is 9876543210")
        assert f.sensitivity == 1, "Phone number should auto-mark sensitive"

    def test_add_auto_sensitivity_normal(self, mm):
        f = mm.add("I like reading books")
        assert f.sensitivity == 0, "Normal content should not be sensitive"

    def test_add_explicit_overrides_auto(self, mm):
        # Explicitly set sensitivity=0 even for sensitive content
        f = mm.add("I take medicine daily", sensitivity=0)
        assert f.sensitivity == 0

    def test_add_pending(self, mm):
        f = mm.add("Auto-extracted fact", status="pending", source="auto")
        assert f.status == "pending"
        assert f.source == "auto"

    def test_add_empty_raises(self, mm):
        with pytest.raises(ValidationError):
            mm.add("")

    def test_add_whitespace_only_raises(self, mm):
        with pytest.raises(ValidationError):
            mm.add("   \n\t  ")

    def test_add_too_long_raises(self, mm):
        with pytest.raises(ValidationError):
            mm.add("x" * 501)

    def test_add_configurable_max_length(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        m = MemoryManager(db_path=db_path, config={"max_content_length": 100})
        with pytest.raises(ValidationError):
            m.add("x" * 101)
        f = m.add("x" * 100)
        assert len(f.content) == 100
        m.close()

    def test_add_invalid_category_raises(self, mm):
        with pytest.raises(ValidationError):
            mm.add("test", category="invalid_cat")

    def test_add_invalid_status_raises(self, mm):
        with pytest.raises(ValidationError):
            mm.add("test", status="invalid")

    def test_add_invalid_source_raises(self, mm):
        with pytest.raises(ValidationError):
            mm.add("test", source="invalid")


class TestDedupe:
    def test_same_content_returns_same_fact(self, mm):
        f1 = mm.add("The sky is blue")
        f2 = mm.add("The sky is blue")
        assert f1.id == f2.id

    def test_dedupe_case_insensitive(self, mm):
        f1 = mm.add("Hello World")
        f2 = mm.add("hello world")
        assert f1.id == f2.id

    def test_dedupe_strips_whitespace(self, mm):
        f1 = mm.add("test fact")
        f2 = mm.add("  test   fact  ")
        assert f1.id == f2.id

    def test_dedupe_never_lowers_sensitivity(self, mm):
        f1 = mm.add("My doctor said...", sensitivity=1)
        assert f1.sensitivity == 1
        f2 = mm.add("My doctor said...", sensitivity=0)
        assert f2.sensitivity == 1, "Dedupe must never lower sensitivity"

    def test_dedupe_can_raise_sensitivity(self, mm):
        f1 = mm.add("Some fact", sensitivity=0)
        assert f1.sensitivity == 0
        f2 = mm.add("Some fact", sensitivity=1)
        assert f2.sensitivity == 1, "Dedupe should raise sensitivity if new is higher"


class TestGet:
    def test_get_existing(self, mm):
        f = mm.add("Test fact")
        got = mm.get(f.id)
        assert got.content == "Test fact"

    def test_get_missing_raises(self, mm):
        with pytest.raises(FactNotFound):
            mm.get(99999)


class TestUpdate:
    def test_update_content(self, mm):
        f = mm.add("Old content")
        updated = mm.update(f.id, content="New content")
        assert updated.content == "New content"

    def test_update_category(self, mm):
        f = mm.add("Some fact")
        updated = mm.update(f.id, category="preference")
        assert updated.category == "preference"

    def test_update_sensitivity(self, mm):
        f = mm.add("Neutral fact", sensitivity=0)
        updated = mm.update(f.id, sensitivity=1)
        assert updated.sensitivity == 1

    def test_update_missing_raises(self, mm):
        with pytest.raises(FactNotFound):
            mm.update(99999, content="x")

    def test_update_duplicate_content_raises(self, mm):
        mm.add("Fact A")
        f2 = mm.add("Fact B")
        with pytest.raises(ValidationError):
            mm.update(f2.id, content="Fact A")

    def test_update_no_changes(self, mm):
        f = mm.add("Fact")
        updated = mm.update(f.id)
        assert updated.content == "Fact"


class TestDelete:
    def test_delete_existing(self, mm):
        f = mm.add("To delete")
        mm.delete(f.id)
        with pytest.raises(FactNotFound):
            mm.get(f.id)

    def test_delete_missing_raises(self, mm):
        with pytest.raises(FactNotFound):
            mm.delete(99999)


class TestConfirm:
    def test_confirm_pending(self, mm):
        f = mm.add("Pending fact", status="pending")
        assert f.status == "pending"
        confirmed = mm.confirm(f.id)
        assert confirmed.status == "confirmed"

    def test_confirm_already_confirmed(self, mm):
        f = mm.add("Already confirmed")
        confirmed = mm.confirm(f.id)
        assert confirmed.status == "confirmed"

    def test_confirm_missing_raises(self, mm):
        with pytest.raises(FactNotFound):
            mm.confirm(99999)


class TestList:
    def test_list_all(self, mm):
        mm.add("Fact 1")
        mm.add("Fact 2")
        mm.add("Fact 3")
        facts = mm.list()
        assert len(facts) == 3

    def test_list_by_category(self, mm):
        mm.add("Pref 1", category="preference")
        mm.add("Task 1", category="task")
        mm.add("Pref 2", category="preference")
        prefs = mm.list(category="preference")
        assert len(prefs) == 2

    def test_list_by_status(self, mm):
        mm.add("Confirmed", status="confirmed")
        mm.add("Pending", status="pending")
        pending = mm.list(status="pending")
        assert len(pending) == 1

    def test_list_limit(self, mm):
        for i in range(10):
            mm.add(f"Fact number {i}")
        facts = mm.list(limit=3)
        assert len(facts) == 3

    def test_list_offset(self, mm):
        for i in range(10):
            mm.add(f"Fact number {i}")
        page1 = mm.list(limit=5, offset=0)
        page2 = mm.list(limit=5, offset=5)
        assert len(page1) == 5
        assert len(page2) == 5
        ids1 = {f.id for f in page1}
        ids2 = {f.id for f in page2}
        assert not ids1.intersection(ids2)

    def test_list_empty(self, mm):
        facts = mm.list()
        assert facts == []


class TestRepr:
    def test_fact_repr_hides_content(self, mm):
        f = mm.add("My secret phone is 9876543210")
        r = repr(f)
        assert "secret" not in r
        assert "9876543210" not in r
        assert "Fact(id=" in r

    def test_fact_str_hides_content(self, mm):
        f = mm.add("My salary is 50000")
        assert "50000" not in str(f)

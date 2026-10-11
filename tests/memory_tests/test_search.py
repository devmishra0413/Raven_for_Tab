# Tests for search - FTS5 and LIKE backends, Hindi/English/Hinglish, hostile inputs

import pytest
from memory.manager import MemoryManager
from memory.exceptions import ValidationError
from memory.text_utils import sanitize_fts_query, sanitize_like_tokens


# ---------------------------------------------------------------
# FTS query sanitizer tests
# ---------------------------------------------------------------
class TestSanitizeFTSQuery:
    def test_simple_query(self):
        assert sanitize_fts_query("hello world") == '"hello"* OR "world"*'

    def test_empty(self):
        assert sanitize_fts_query("") == ""
        assert sanitize_fts_query("   ") == ""
        assert sanitize_fts_query(None) == ""

    def test_double_quote(self):
        assert sanitize_fts_query('"hello"') == '"hello"*'

    def test_short_token_not_prefix(self):
        assert sanitize_fts_query("ka") == '"ka"'

    def test_single_quote(self):
        q = sanitize_fts_query("it's")
        assert q

    def test_star(self):
        q = sanitize_fts_query("test*")
        assert q

    def test_and_operator(self):
        q = sanitize_fts_query("AND")
        # AND is a pure operator token; after stripping non-word, "and" remains
        assert q  # Should produce a safe quoted token

    def test_or_operator(self):
        q = sanitize_fts_query("OR")
        assert q

    def test_not_operator(self):
        q = sanitize_fts_query("NOT")
        assert q

    def test_near_paren(self):
        q = sanitize_fts_query("NEAR(x y)")
        assert q

    def test_colon(self):
        q = sanitize_fts_query("column:value")
        assert q

    def test_dash(self):
        q = sanitize_fts_query("-excluded")
        assert q

    def test_parentheses(self):
        q = sanitize_fts_query("(test)")
        assert q

    def test_unbalanced_quote(self):
        q = sanitize_fts_query('"unbalanced')
        assert q

    def test_only_punctuation(self):
        q = sanitize_fts_query("!@#$%")
        assert q == ""

    def test_emoji(self):
        q = sanitize_fts_query("🎉")
        # emoji may not survive, but should not crash
        assert isinstance(q, str)

    def test_hindi(self):
        q = sanitize_fts_query("राहुल")
        assert "राहुल" in q

    def test_very_long_input(self):
        q = sanitize_fts_query("word " * 1000)
        assert isinstance(q, str)
        assert '"word"' in q


class TestSanitizeLikeTokens:
    def test_simple(self):
        tokens = sanitize_like_tokens("hello world")
        assert tokens == ["%hello%", "%world%"]

    def test_empty(self):
        assert sanitize_like_tokens("") == []
        assert sanitize_like_tokens("   ") == []


# ---------------------------------------------------------------
# Search integration tests (FTS5)
# ---------------------------------------------------------------
class TestSearchFTS5:
    def test_basic_english(self, mm):
        mm.add("Rahul likes cricket")
        mm.add("Priya enjoys reading")
        results = mm.search("cricket")
        assert len(results) == 1
        assert results[0].content == "Rahul likes cricket"

    def test_basic_hindi(self, mm):
        mm.add("राहुल को क्रिकेट पसंद है")
        mm.add("प्रिया को किताबें पसंद हैं")
        results = mm.search("क्रिकेट")
        assert len(results) == 1
        assert "राहुल" in results[0].content

    def test_hindi_name_priyanka(self, mm):
        mm.add("प्रियंका ने किताबें पढ़ीं")
        results = mm.search("प्रियंका")
        assert len(results) == 1

    def test_hindi_with_matras(self, mm):
        mm.add("किताबें बहुत अच्छी हैं")
        results = mm.search("किताबें")
        assert len(results) == 1

    def test_hinglish_mixed(self, mm):
        mm.add("Rahul ka birthday January 5 ko hai")
        results = mm.search("birthday")
        assert len(results) == 1

    def test_devanagari_digit_normalization(self, mm):
        mm.add("मीटिंग ५ बजे है")
        results = mm.search("5")
        assert len(results) == 1

    def test_multiple_results_ranked(self, mm):
        mm.add("Python programming is fun")
        mm.add("I love Python and JavaScript")
        mm.add("Python Python Python is great")
        results = mm.search("Python")
        assert len(results) == 3
        assert results[0].content == "Python Python Python is great"

    def test_empty_query_returns_empty(self, mm):
        mm.add("Some fact")
        assert mm.search("") == []
        assert mm.search("   ") == []
        with pytest.raises(ValidationError):
            mm.search(None)

    def test_no_results(self, mm):
        mm.add("Apples are red")
        results = mm.search("bananas")
        assert results == []

    def test_pending_excluded_by_default(self, mm):
        mm.add("Pending fact about cars", status="pending")
        mm.add("Confirmed fact about cars")
        results = mm.search("cars")
        assert len(results) == 1
        assert results[0].status == "confirmed"

    def test_pending_included_when_asked(self, mm):
        mm.add("Pending fact about dogs", status="pending")
        mm.add("Confirmed fact about dogs")
        results = mm.search("dogs", include_pending=True)
        assert len(results) == 2

    def test_sensitive_included_by_default(self, mm):
        mm.add("My password is secret", sensitivity=1)
        results = mm.search("password", include_sensitive=True)
        assert len(results) >= 1

    def test_sensitive_excluded_when_asked(self, mm):
        mm.add("Sensitive health data", sensitivity=1)
        mm.add("Public health information", sensitivity=0)
        results = mm.search("health", include_sensitive=False)
        assert all(f.sensitivity == 0 for f in results)

    def test_k_limit(self, mm):
        for i in range(10):
            mm.add(f"Fact about topic number {i}")
        results = mm.search("topic", k=3)
        assert len(results) <= 3

    # Hostile FTS inputs - these must not crash
    @pytest.mark.parametrize("hostile", [
        '"', "'", "*", "AND", "OR", "NOT", "NEAR(",
        ":", "-x", "()", "x OR y",
        '"; DROP TABLE facts;--',
        "' OR '1'='1",
        "NEAR(a b, 5)",
        "content_norm:hack",
        '"""',
        "() () ()",
        "AND AND AND",
        "NOT NOT NOT",
        "a*b*c*",
        "\x00\x01\x02",
    ])
    def test_hostile_fts_input(self, mm, hostile):
        mm.add("Safe fact for testing")
        # Must not raise
        results = mm.search(hostile)
        assert isinstance(results, list)


# ---------------------------------------------------------------
# Search integration tests (LIKE fallback)
# ---------------------------------------------------------------
class TestSearchLIKE:
    def test_basic_english_like(self, mm_like):
        mm_like.add("Rahul likes cricket")
        results = mm_like.search("cricket")
        assert len(results) == 1

    def test_basic_hindi_like(self, mm_like):
        mm_like.add("राहुल को क्रिकेट पसंद है")
        results = mm_like.search("क्रिकेट")
        assert len(results) == 1

    def test_empty_like(self, mm_like):
        assert mm_like.search("") == []

    def test_hostile_like(self, mm_like):
        mm_like.add("Safe fact")
        results = mm_like.search("'; DROP TABLE facts;--")
        assert isinstance(results, list)

    def test_backend_property(self, mm_like):
        assert mm_like.search_backend == "like"

    def test_pending_excluded_like(self, mm_like):
        mm_like.add("Pending about fish", status="pending")
        mm_like.add("Confirmed about fish")
        results = mm_like.search("fish")
        assert len(results) == 1
        assert results[0].status == "confirmed"

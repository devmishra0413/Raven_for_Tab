# tests/privacy/test_vault.py

import pytest
from privacy.vault import Vault


class TestVault:
    def test_mask_same_value_returns_same_placeholder(self):
        vault = Vault()
        p1 = vault.mask("PHONE", "9876543210")
        p2 = vault.mask("PHONE", "9876543210")
        assert p1 == p2 == "[PHONE_1]"

    def test_mask_different_values_get_different_placeholders(self):
        vault = Vault()
        p1 = vault.mask("PHONE", "9876543210")
        p2 = vault.mask("PHONE", "9876543211")
        assert p1 == "[PHONE_1]"
        assert p2 == "[PHONE_2]"

    def test_mask_different_kinds(self):
        vault = Vault()
        p1 = vault.mask("PHONE", "9876543210")
        p2 = vault.mask("EMAIL", "test@test.com")
        assert p1 == "[PHONE_1]"
        assert p2 == "[EMAIL_1]"

    def test_unmask_restores_original(self):
        vault = Vault()
        masked = vault.mask("PHONE", "9876543210")
        result = vault.unmask(f"My number is {masked}")
        assert result == "My number is 9876543210"

    def test_roundtrip_multiple_values(self):
        vault = Vault()
        a = vault.mask("PHONE", "9876543210")
        b = vault.mask("EMAIL", "test@test.com")
        original = "call 9876543210 or mail test@test.com"
        masked_text = original.replace("9876543210", a).replace("test@test.com", b)
        assert "9876543210" not in masked_text
        assert "test@test.com" not in masked_text
        assert vault.unmask(masked_text) == original

    def test_unmask_handles_spaces(self):
        vault = Vault()
        vault.mask("PHONE", "9876543210")
        assert "9876543210" in vault.unmask("[ PHONE_1 ]")

    def test_unmask_handles_lowercase(self):
        vault = Vault()
        vault.mask("PHONE", "9876543210")
        assert "9876543210" in vault.unmask("[phone_1]")

    def test_unmask_handles_markdown_bold(self):
        vault = Vault()
        vault.mask("PHONE", "9876543210")
        assert "9876543210" in vault.unmask("**[PHONE_1]**")

    def test_unmask_handles_trailing_punctuation(self):
        vault = Vault()
        vault.mask("PHONE", "9876543210")
        result = vault.unmask("Call [PHONE_1].")
        assert result == "Call 9876543210."

    def test_unmask_preserves_unknown_placeholders(self):
        vault = Vault()
        assert vault.unmask("[UNKNOWN_1]") == "[UNKNOWN_1]"

    def test_unmask_unknown_index_of_known_kind(self):
        vault = Vault()
        vault.mask("PHONE", "9876543210")
        assert vault.unmask("[PHONE_9]") == "[PHONE_9]"

    def test_clear(self):
        vault = Vault()
        vault.mask("PHONE", "9876543210")
        vault.clear()
        assert vault.is_empty
        assert vault.unmask("[PHONE_1]") == "[PHONE_1]"

    def test_repr_and_str_have_no_raw_values(self):
        vault = Vault()
        vault.mask("PHONE", "9876543210")
        vault.mask("EMAIL", "test@test.com")
        for s in (repr(vault), str(vault)):
            assert "9876543210" not in s
            assert "test@test.com" not in s

    def test_get_findings_returns_type_and_placeholder(self):
        vault = Vault()
        vault.mask("PHONE", "9876543210")
        vault.mask("EMAIL", "test@test.com")
        findings = vault.get_findings()
        assert len(findings) == 2
        assert any(f["type"] == "phone" and f["placeholder"] == "[PHONE_1]" for f in findings)
        assert any(f["type"] == "email" and f["placeholder"] == "[EMAIL_1]" for f in findings)

    def test_findings_never_contain_raw_values(self):
        vault = Vault()
        vault.mask("PHONE", "9876543210")
        assert "9876543210" not in str(vault.get_findings())

    def test_empty_value(self):
        vault = Vault()
        assert vault.mask("PHONE", "") == ""

    def test_surrounding_whitespace_maps_to_same_placeholder(self):
        vault = Vault()
        p1 = vault.mask("PHONE", "9876543210")
        p2 = vault.mask("PHONE", " 9876543210 ")
        assert p1 == p2
# tests/privacy/test_regex_filter.py

import pytest
from privacy.regex_filter import regex_filter, luhn_check, verhoeff_check
from privacy.normalize import normalize_for_detection
from privacy.vault import Vault


def run(text, entities=None, vault=None):
    vault = vault or Vault()
    result, findings = regex_filter(text, vault)
    return result, findings, vault


class TestLuhnCheck:
    def test_valid_visa(self):
        assert luhn_check("4111111111111111") is True

    def test_valid_mastercard(self):
        assert luhn_check("5555555555554444") is True

    def test_invalid_luhn(self):
        assert luhn_check("1234567890123456") is False

    def test_too_short(self):
        assert luhn_check("1234") is False


class TestVerhoeffCheck:
    def test_valid_aadhaar(self):
        assert verhoeff_check("234123412346") is True

    def test_invalid_aadhaar(self):
        assert verhoeff_check("123456789012") is False

    def test_invalid_length(self):
        assert verhoeff_check("12345") is False
        assert verhoeff_check("1234567890123") is False

    def test_non_digits(self):
        assert verhoeff_check("abcd12345678") is False


class TestMustMask:
    @pytest.mark.parametrize("text,raw,placeholder", [
        ("My number is 9876543210", "9876543210", "[PHONE_1]"),
        ("Call me at +91 98765 43210", "98765 43210", "[PHONE_1]"),
        ("Call me at +91-98765-43210", "98765-43210", "[PHONE_1]"),
        ("Number: 09876543210", "9876543210", "[PHONE_1]"),
        ("Email me at user@example.com", "user@example.com", "[EMAIL_1]"),
        ("Aadhaar: 2341 2341 2346", "2341 2341 2346", "[AADHAAR_1]"),
        ("Aadhaar: 234123412346", "234123412346", "[AADHAAR_1]"),
        ("PAN: ABCDE1234F", "ABCDE1234F", "[PAN_1]"),
        ("Card: 4111 1111 1111 1111", "4111 1111 1111 1111", "[CARD_1]"),
        ("Pay to user@paytm", "user@paytm", "[UPI_1]"),
        ("IFSC: SBIN0001234", "SBIN0001234", "[IFSC_1]"),
        ("OTP is 123456", "123456", "[OTP_1]"),
        ("123456 is your OTP", "123456", "[OTP_1]"),
        ("PIN code 110001", "110001", "[PIN_1]"),
        ("Account number 1234567890", "1234567890", "[ACCOUNT_1]"),
        ("Passport: A1234567", "A1234567", "[PASSPORT_1]"),
        ("Vehicle: MH12AB1234", "MH12AB1234", "[VEHICLE_1]"),
        ("Server IP 192.168.1.1", "192.168.1.1", "[IP_1]"),
    ])
    def test_masks(self, text, raw, placeholder):
        result, findings, _ = run(text)
        assert placeholder in result
        assert raw not in result

    def test_secret_at_start_and_end(self):
        result, _, _ = run("9876543210 is my number, mail user@example.com")
        assert "9876543210" not in result
        assert "user@example.com" not in result

    def test_repeated_secret_same_placeholder(self):
        result, _, _ = run("9876543210 and again 9876543210")
        assert result.count("[PHONE_1]") == 2
        assert "[PHONE_2]" not in result

    def test_multiple_secrets(self):
        result, _, vault = run("Phone 9876543210, email user@test.com, PAN ABCDE1234F")
        assert "[PHONE_1]" in result
        assert "[EMAIL_1]" in result
        assert "[PAN_1]" in result
        for raw in ("9876543210", "user@test.com", "ABCDE1234F"):
            assert raw not in result
        assert len(vault.get_findings()) == 3

    def test_devanagari_digits_in_phone(self):
        text = normalize_for_detection("मेरा नंबर ९८७६५४३२१० है")
        result, _, _ = run(text)
        assert "[PHONE_1]" in result
        assert "9876543210" not in result

    def test_aadhaar_with_bad_checksum_but_keyword_still_masked(self):
        result, _, _ = run("my aadhaar is 123456789012")
        assert "123456789012" not in result

    def test_upi_and_email_both_detected(self):
        result, _, _ = run("UPI: user@paytm, Email: user@example.com")
        assert "[UPI_1]" in result
        assert "[EMAIL_1]" in result
        assert "user@paytm" not in result
        assert "user@example.com" not in result

    def test_url_with_token_is_masked(self):
        result, _, _ = run("Visit https://api.example.com?token=abc123")
        assert "abc123" not in result

    def test_findings_never_contain_raw_values(self):
        _, findings, _ = run("Phone 9876543210, email user@test.com")
        assert "9876543210" not in str(findings)
        assert "user@test.com" not in str(findings)

    def test_mask_then_unmask_roundtrip(self):
        text = "Phone 9876543210, email user@test.com"
        result, _, vault = run(text)
        assert vault.unmask(result) == text


class TestMustNotMask:
    @pytest.mark.parametrize("text", [
        "Year 2026 is coming",
        "Price is ₹1,50,000",
        "Laptop 2026 me 1,50,000 rupaye ka liya",
        "Mujhe 1500 rupaye chahiye",
        "Meeting 5 baje hai",
        "Order 12 items ka hai",
        "Python 3.12.1 install karo",
        "Score was 85% in 2024",
        "Date 03/10/2026 ko milte hain",
    ])
    def test_unchanged(self, text):
        result, findings, _ = run(text)
        assert result == text
        assert findings == []
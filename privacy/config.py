# RAVEN Privacy Core - Configuration

import copy
from typing import Any

DEFAULT_SENSITIVE_TOPICS = {
    "health": {
        "keywords_hi": ["स्वास्थ्य", "बीमारी", "दवा", "दवाई", "आयुर्वेद", "इलाज", "अस्पताल", "डॉक्टर", "मेडिकल", "ब्लड प्रेशर", "रक्तचाप", "शुगर", "डायबिटीज", "कैंसर", "टीबी"],
        "keywords_en": ["health", "medical", "doctor", "hospital", "medicine", "disease", "illness", "treatment", "prescription", "diagnosis", "blood pressure", "diabetes", "cancer", "tuberculosis"],
        "keywords_hinglish": ["bimari", "bimaari", "dawa", "dawai", "ilaj", "checkup", "sugar level"],
        "action": "permission",
    },
    "loan": {
        "keywords_hi": ["ऋण", "कर्ज", "कर्ज़", "लोन", "EMI", "ब्याज", "किश्त", "किस्त", "गारंटर", "होम लोन", "पर्सनल लोन", "कार लोन"],
        "keywords_en": ["loan", "debt", "EMI", "installment", "lender", "borrower", "mortgage", "home loan", "personal loan", "car loan", "gold loan"],
        "keywords_hinglish": ["lone", "karz", "karza", "byaj", "kisht", "kist"],
        "action": "permission",
    },
    "salary": {
        "keywords_hi": ["वेतन", "तनख्वाह", "तनख़्वाह", "सैलरी", "इनकम", "कमाई", "मासिक आय", "CTC", "पेंशन"],
        "keywords_en": ["salary", "monthly income", "wage", "wages", "CTC", "pension", "earnings", "take home"],
        "keywords_hinglish": ["salary", "payscale", "tankhwah", "kamaai", "kamai"],
        "action": "permission",
    },
    "legal": {
        "keywords_hi": ["कानूनी", "वकील", "कोर्ट", "मुकदमा", "FIR", "एफआईआर", "पुलिस", "गवाह", "साक्ष्य", "जमानत"],
        "keywords_en": ["legal", "lawyer", "court", "FIR", "police", "lawsuit", "evidence", "witness", "bail", "arrest"],
        "keywords_hinglish": ["vakil", "mukadma", "mukadma", "police case", "court case", "jamanat"],
        "action": "permission",
    },
    "passwords": {
        "keywords_hi": ["पासवर्ड", "सीक्रेट", "गोपनीय", "ओटीपी", "OTP", "CVV", "एटीएम पिन", "यूपीआई पिन"],
        "keywords_en": ["password", "passcode", "OTP", "CVV", "security code", "private key", "API key", "access token", "credentials", "ATM PIN", "UPI PIN"],
        "keywords_hinglish": ["password", "otp", "cvv", "atm pin", "upi pin", "secret code"],
        "action": "block",
    },
    "bank": {
        "keywords_hi": ["बैंक", "बैंक खाता", "खाता संख्या", "अकाउंट नंबर", "IFSC", "UPI", "डेबिट कार्ड", "क्रेडिट कार्ड", "बैलेंस", "मिनिमम बैलेंस"],
        "keywords_en": ["bank", "bank account", "account number", "IFSC", "UPI", "debit card", "credit card", "balance", "minimum balance", "banking"],
        "keywords_hinglish": ["bank", "bank account", "account number", "UPI", "debit card", "credit card", "balance"],
        "action": "permission",
    },
}

DEFAULT_THRESHOLDS = {
    "digit_run_length": 6,
    "min_name_length": 3,
    "fuzzy_distance": 0,  # fuzzy abhi implemented nahi, isliye off
}

DEFAULT_POLICY = {
    "sensitive_topic_action": "permission",
    "block_on_failsafe": True,
    "mask_entity_type": "placeholder",
}

DEFAULT_CONFIG = {
    "sensitive_topics": DEFAULT_SENSITIVE_TOPICS,
    "thresholds": DEFAULT_THRESHOLDS,
    "policy": DEFAULT_POLICY,
}


def _deep_merge(base: dict, overrides: dict) -> dict:
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = copy.deepcopy(value)
    return base


def merge_config(overrides: dict | None = None) -> dict:
    """Merge user overrides into a deep copy of defaults (defaults never mutated)."""
    config = copy.deepcopy(DEFAULT_CONFIG)
    if overrides:
        _deep_merge(config, overrides)
    return config
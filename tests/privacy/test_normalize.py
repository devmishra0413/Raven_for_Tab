from privacy.normalize import normalize_for_detection, normalize_spoken_digits


def test_devanagari_digits():
    assert normalize_for_detection("मेरा नंबर ९८७६५४३२१० है") == "मेरा नंबर 9876543210 है"

def test_mixed_digits():
    assert normalize_for_detection("9८76 5४32 1०") == "9876 5432 10"

def test_length_preserved():
    t = "नंबर ९८७"
    assert len(normalize_for_detection(t)) == len(t)

def test_preserves_text():
    assert normalize_for_detection("Hello १२३ World") == "Hello 123 World"

def test_empty():
    assert normalize_for_detection("") == ""
    assert normalize_spoken_digits("") == ""

def test_spoken_hinglish():
    assert normalize_spoken_digits("nau aath saat chhe paanch") == "98765"

def test_spoken_devanagari():
    assert normalize_spoken_digits("नौ आठ सात छह पांच") == "98765"

def test_spoken_english():
    assert normalize_spoken_digits("one two three four") == "1234"

def test_short_phrase_untouched():
    assert normalize_spoken_digits("ek din do log") == "ek din do log"
    assert normalize_spoken_digits("do teen char") == "do teen char"
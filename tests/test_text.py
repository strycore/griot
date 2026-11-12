from griot.text import chunk, split_sentences


def test_sentences_split_on_terminal_punctuation_and_newlines():
    assert split_sentences("One. Two! Three?\nFour") == ["One.", "Two!", "Three?", "Four"]


def test_decimal_points_do_not_split():
    assert split_sentences("It took 1.2 seconds. Fine.") == ["It took 1.2 seconds.", "Fine."]


def test_first_sentence_stands_alone_and_the_rest_are_packed():
    text = "Hi. " + "Short one. " * 6
    chunks = chunk(text, max_chars=35)
    assert chunks[0] == "Hi."
    assert chunks[1:] == ["Short one. Short one. Short one."] * 2
    assert " ".join(chunks) == text.strip()


def test_an_overlong_sentence_is_left_whole():
    long = "word " * 30 + "end."
    assert chunk(f"Hi. {long}", max_chars=20) == ["Hi.", long]


def test_blank_text_yields_nothing():
    assert chunk("  \n ", max_chars=100) == []

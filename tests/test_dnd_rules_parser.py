from pipeline.rules.dnd_rules_parser import chunk_segments


def test_chunk_segments_splits_long_single_paragraph() -> None:
    sentence = "A referee frames the next decision clearly so the party can react with intent."
    long_paragraph = " ".join(sentence for _ in range(80))

    chunks = chunk_segments([("Action Economy", long_paragraph)], max_chars=300, overlap=60)

    assert len(chunks) > 1
    assert all(len(text) <= 300 for _heading, text in chunks)


def test_chunk_segments_handles_long_unbroken_text() -> None:
    long_token_stream = "x" * 950

    chunks = chunk_segments([("Hazards", long_token_stream)], max_chars=200, overlap=40)

    assert len(chunks) >= 5
    assert all(len(text) <= 200 for _heading, text in chunks)


def test_chunk_segments_prefers_sentence_breaks_when_possible() -> None:
    sentences = [
        "The first ruling explains how the referee frames a scene before the players respond with intent.",
        "The second ruling resolves a risky action and leaves a clear consequence for the table to react to.",
        "The third ruling closes the exchange and gives the next player an obvious opening for their turn.",
    ]
    long_paragraph = " ".join(sentences)

    chunks = chunk_segments([("Flow", long_paragraph)], max_chars=140, overlap=0)

    assert len(chunks) == 3
    assert all(text.endswith(".") for _heading, text in chunks)
    assert all(len(text) <= 140 for _heading, text in chunks)

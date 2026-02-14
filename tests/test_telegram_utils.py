from src.utils.telegram import split_message


def test_split_message_single_chunk() -> None:
    message = "short message"
    chunks = split_message(message, max_len=50)
    assert chunks == ["short message"]


def test_split_message_multiple_chunks() -> None:
    message = "A" * 45 + "\n" + "B" * 45
    chunks = split_message(message, max_len=50)
    assert len(chunks) == 2
    assert chunks[0] == "A" * 45
    assert chunks[1] == "B" * 45

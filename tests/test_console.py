"""Console output never stops a command over a character it cannot show."""

import io

from capstone.console import safe_console


def windows_file_stream():
    """Output to a file on Windows: the cp1252 code page, which has no arrow."""
    return io.TextIOWrapper(io.BytesIO(), encoding="cp1252")


def test_an_unencodable_character_is_escaped_not_fatal():
    stream = windows_file_stream()
    safe_console(stream)
    print("vibration 3.6 → 4.56 mm/s", file=stream, flush=True)
    stream.seek(0)
    escaped = "\\" + "u2192"  # a backslash, then the code point
    assert stream.read() == f"vibration 3.6 {escaped} 4.56 mm/s\n"


def test_without_it_the_same_print_raised():
    """What stopped `experiment run` on 2026-10-21."""
    stream = windows_file_stream()
    try:
        print("→", file=stream, flush=True)
    except UnicodeEncodeError:
        return
    raise AssertionError("cp1252 was expected to refuse the arrow")


def test_a_stream_that_cannot_be_reconfigured_is_left_alone():
    capture = io.StringIO()  # no reconfigure, like some test captures
    safe_console(capture)
    print("→", file=capture)
    assert capture.getvalue() == "→\n"

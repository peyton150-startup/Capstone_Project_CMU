# Printing that never stops a command.
# Responsibility: make the console streams replace characters they cannot show.
"""Console output that cannot crash a long run.

On Windows, output sent to a file or a pipe uses the system code page
(cp1252), which has no "→" or "≥". A model's conclusion can contain them,
and printing it raised UnicodeEncodeError (seen live on 2026-10-21), which
stopped `python -m capstone.experiment run` after the case's record was
saved, so the remaining cases never ran. `safe_console()` keeps each
stream's encoding and only changes what happens to a character it cannot
encode: it is written as an escape such as "\\u2192" instead.
"""

import sys
from typing import TextIO


def safe_console(*streams: TextIO) -> None:
    """Replace, never refuse, characters a stream cannot encode.

    With no arguments, standard output and standard error. A stream that
    cannot be reconfigured (a test's capture, for example) is left as it is.
    """
    for stream in streams or (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="backslashreplace")

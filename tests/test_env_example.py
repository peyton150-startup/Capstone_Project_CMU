"""`.env.example` lists every setting, and a copy of it loads."""

import re

from capstone.settings import REPO_ROOT, Settings

EXAMPLE = REPO_ROOT / ".env.example"


def named():
    """Every NAME=... line, commented out or not."""
    text = EXAMPLE.read_text(encoding="utf-8")
    return set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]+)=", text, flags=re.MULTILINE))


def test_every_setting_is_listed():
    settings = {field.validation_alias for field in Settings.model_fields.values()}
    assert settings - named() == set()


def test_nothing_is_listed_that_the_code_does_not_read():
    settings = {field.validation_alias for field in Settings.model_fields.values()}
    assert named() - settings == set()


def test_a_copy_of_the_example_loads_with_the_defaults(monkeypatch):
    for name in named():
        monkeypatch.delenv(name, raising=False)
    copied = Settings(_env_file=EXAMPLE)
    assert copied == Settings(_env_file=None)

"""Unit tests for filename handling and the file service helpers."""
from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.core.errors import ValidationError
from app.services.file_service import sanitize_filename, validate_content_type


@pytest.mark.parametrize("raw,expected", [
    ("report.pdf", "report.pdf"),
    ("../../etc/passwd", "passwd"),
    ("..\\..\\windows\\system32\\evil.exe", "evil.exe"),
    ("/absolute/path/file.txt", "file.txt"),
    ("  spaced name.txt  ", "spaced name.txt"),
    ("weird\x00name.txt", "weirdname.txt"),
    ("...hidden.txt", "hidden.txt"),
])
def test_sanitize_filename(raw, expected):
    assert sanitize_filename(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "..", "...", "/", "\\"])
def test_sanitize_filename_rejects_empty_results(raw):
    with pytest.raises(ValidationError):
        sanitize_filename(raw)


def test_sanitize_filename_truncates_but_keeps_extension():
    name = "a" * 400 + ".txt"
    result = sanitize_filename(name)
    assert len(result) <= 200
    assert result.endswith(".txt")


@pytest.mark.parametrize("value,expected", [
    ("text/plain", "text/plain"),
    ("image/png", "image/png"),
    ("application/vnd.ms-excel", "application/vnd.ms-excel"),
    (None, "application/octet-stream"),
    ("", "application/octet-stream"),
    ("evil/type\r\nX-Injected: 1", "application/octet-stream"),
    ("nonsense", "application/octet-stream"),
])
def test_validate_content_type(value, expected):
    assert validate_content_type(value) == expected


def test_register_schema_validation_rules():
    from app.schemas.auth import RegisterRequest

    with pytest.raises(PydanticValidationError):
        RegisterRequest(username="ab", password="Passw0rd!")
    with pytest.raises(PydanticValidationError):
        RegisterRequest(username="validname", password="allletters")
    assert RegisterRequest(username="validname", password="Passw0rd!").username == "validname"

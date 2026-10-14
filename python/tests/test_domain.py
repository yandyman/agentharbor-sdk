import pytest

from agentharbor import InvalidDomain, validate_domain


@pytest.mark.parametrize("value,expected", [
    ("example.com", "example.com"),
    ("Example.COM", "example.com"),
    ("  mailchimp.com  ", "mailchimp.com"),
    ("example.com.", "example.com"),
    ("sub.example.co.uk", "sub.example.co.uk"),
    ("xn--bcher-kva.example", "xn--bcher-kva.example"),
    ("example.xn--p1ai", "example.xn--p1ai"),
    ("a-b.io", "a-b.io"),
])
def test_valid_domains(value, expected):
    assert validate_domain(value) == expected


@pytest.mark.parametrize("value", [
    "", "   ", "example", "https://example.com", "example.com/path", "example.com:443",
    "user@example.com", "127.0.0.1", "127.1", "0x7f.1", "localhost", "printer.local",
    "db.internal", "-bad.com", "bad-.com", "exa mple.com", "bücher.de", "example.c0m",
    "a" * 64 + ".com", ("a" * 62 + ".") * 5 + "com", "example..com", "[::1]", None, 42,
])
def test_invalid_domains(value):
    with pytest.raises(InvalidDomain):
        validate_domain(value)


def test_invalid_domain_is_a_value_error():
    with pytest.raises(ValueError):
        validate_domain("http://x.com")

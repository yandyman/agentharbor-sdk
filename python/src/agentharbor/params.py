"""Client-side checks for the public-data routes, so a bad input fails before any request.

Mirrors the query-parameter schemas the gateway publishes in /openapi.json for /sec-company,
/recalls, /package-check and /pdf-extract (harbor-data products). The server checks again and
answers 422 (not charged) for anything these checks let through.
"""
from __future__ import annotations

import re
from typing import Any

from .errors import InvalidInput

RECALL_CATEGORIES = ("consumer", "vehicle", "food", "drug", "device")
ECOSYSTEMS = ("pypi", "npm", "go", "cargo", "maven", "nuget", "rubygems")

_TICKER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-]{0,9}$")
_CIK = re.compile(r"^[0-9]{1,10}$")
_YEAR = re.compile(r"^[0-9]{4}$")
_PAGES = re.compile(r"^[0-9]+(-[0-9]+)?(,[0-9]+(-[0-9]+)?)*$")


def _text(name: str, value: Any, max_len: int, *, min_len: int = 1) -> str:
    if not isinstance(value, str):
        raise InvalidInput(f"{name} must be a string")
    v = value.strip()
    if not min_len <= len(v) <= max_len:
        raise InvalidInput(f"{name} must be {min_len}-{max_len} characters")
    return v


def _int(name: str, value: Any, lo: int, hi: int) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, str)) or not str(value).strip().isdigit():
        raise InvalidInput(f"{name} must be a whole number {lo}-{hi}")
    n = int(str(value).strip())
    if not lo <= n <= hi:
        raise InvalidInput(f"{name} must be {lo}-{hi}")
    return str(n)


def _drop_none(params: dict[str, str | None]) -> dict[str, str]:
    return {k: v for k, v in params.items() if v is not None}


def sec_company_params(ticker: str | None, cik: str | int | None, filings: int | str | None,
                       forms: str | None) -> dict[str, str]:
    if (ticker is None) == (cik is None):
        raise InvalidInput("give exactly one of ticker (e.g. AAPL) or cik")
    t = c = None
    if ticker is not None:
        t = _text("ticker", ticker, 10)
        if not _TICKER.match(t):
            raise InvalidInput(f"{ticker!r} is not a stock ticker such as AAPL or BRK.B")
    if cik is not None:
        c = str(cik).strip() if isinstance(cik, (int, str)) and not isinstance(cik, bool) else ""
        if not _CIK.match(c):
            raise InvalidInput("cik must be 1-10 digits")
    return _drop_none({
        "ticker": t, "cik": c,
        "filings": None if filings is None else _int("filings", filings, 0, 25),
        "forms": None if forms is None else _text("forms", forms, 120),
    })


def recalls_params(category: str, query: str | None, make: str | None, model: str | None,
                   year: int | str | None, limit: int | str | None) -> dict[str, str]:
    category = category.strip().lower() if isinstance(category, str) else category
    if category not in RECALL_CATEGORIES:
        raise InvalidInput("category must be one of " + ", ".join(RECALL_CATEGORIES))
    vehicle_args = (make, model, year)
    if category == "vehicle":
        if query is not None:
            raise InvalidInput("vehicle recalls take make, model and year, not query")
        if make is None or model is None or year is None:
            raise InvalidInput("vehicle recalls need make, model and year")
        y = str(year).strip()
        if not _YEAR.match(y):
            raise InvalidInput("year must be a model year such as 2020")
        out = {"make": _text("make", make, 50), "model": _text("model", model, 50), "year": y}
    else:
        if any(a is not None for a in vehicle_args):
            raise InvalidInput("make, model and year are for category='vehicle' only")
        if query is None:
            raise InvalidInput(f"category={category!r} needs a query (product or brand text)")
        out = {"query": _text("query", query, 100, min_len=2)}
    return {"category": category, **out,
            **({} if limit is None else {"limit": _int("limit", limit, 1, 25)})}


def package_check_params(ecosystem: str, name: str, version: str | None) -> dict[str, str]:
    ecosystem = ecosystem.strip().lower() if isinstance(ecosystem, str) else ecosystem
    if ecosystem not in ECOSYSTEMS:
        raise InvalidInput("ecosystem must be one of " + ", ".join(ECOSYSTEMS))
    return _drop_none({
        "ecosystem": ecosystem, "name": _text("name", name, 214),
        "version": None if version is None else _text("version", version, 100),
    })


def pdf_extract_params(url: str, pages: str | None) -> dict[str, str]:
    u = _text("url", url, 2048)
    if not re.match(r"^https?://[^\s/]+", u, re.IGNORECASE):
        raise InvalidInput("url must be a public http(s) URL of a PDF")
    p = None
    if pages is not None:
        p = _text("pages", pages, 80).replace(" ", "")
        if not _PAGES.match(p):
            raise InvalidInput("pages must look like 1-10 or 1,3,5-7")
    return _drop_none({"url": u, "pages": p})

"""The public-data routes: inputs checked before any request, sent as the gateway's query parameters."""
import asyncio

import httpx
import pytest

from agentharbor import AgentHarbor, AgentHarborSync, InvalidDomain, InvalidInput, NotCharged, PriceTooHigh

from helpers import ACCOUNT, FakeGateway, fake_payer, payment_required, requirement


def run(coro):
    return asyncio.run(coro)


def echo(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"path": request.url.path, "params": dict(request.url.params)})


def make(gw, **kw):
    return AgentHarbor(transport=gw.transport(), base_url="https://gw.test", account=ACCOUNT, **kw)


def call(method, *args, **kw):
    gw = FakeGateway(paid=echo)
    with fake_payer() as payers:
        r = run(getattr(make(gw), method)(*args, **kw))
    assert payers[0].signed == 1
    return r, gw


@pytest.mark.parametrize("method,args,kw,path,params", [
    ("sec_company", ("AAPL",), {"filings": 5}, "/sec-company", {"ticker": "AAPL", "filings": "5"}),
    ("sec_company", (), {"cik": 320193, "forms": "10-K,8-K"}, "/sec-company", {"cik": "320193", "forms": "10-K,8-K"}),
    ("recalls", ("consumer", "stroller"), {"limit": 3}, "/recalls",
     {"category": "consumer", "query": "stroller", "limit": "3"}),
    ("recalls", ("vehicle",), {"make": "honda", "model": "civic", "year": 2020}, "/recalls",
     {"category": "vehicle", "make": "honda", "model": "civic", "year": "2020"}),
    ("package_check", ("pypi", "requests", "2.25.0"), {}, "/package-check",
     {"ecosystem": "pypi", "name": "requests", "version": "2.25.0"}),
    ("package_check", ("NPM", "@types/node"), {}, "/package-check", {"ecosystem": "npm", "name": "@types/node"}),
    ("domain_verify", ("Mailchimp.com",), {}, "/domain-verify", {"domain": "mailchimp.com"}),
    ("pdf_extract", ("https://www.irs.gov/pub/irs-pdf/fw9.pdf",), {"pages": "1-2"}, "/pdf-extract",
     {"url": "https://www.irs.gov/pub/irs-pdf/fw9.pdf", "pages": "1-2"}),
])
def test_each_route_gets_its_query_parameters(method, args, kw, path, params):
    r, gw = call(method, *args, **kw)
    assert r["path"] == path and r["params"] == params
    assert {q.url.path for q in gw.requests} == {path}


@pytest.mark.parametrize("method,args,kw", [
    ("sec_company", (), {}),                                  # neither ticker nor cik
    ("sec_company", ("AAPL",), {"cik": "320193"}),            # both
    ("sec_company", ("AAPL inc",), {}),
    ("sec_company", (), {"cik": "12a"}),
    ("sec_company", ("AAPL",), {"filings": 26}),
    ("recalls", ("toys", "lego"), {}),
    ("recalls", ("consumer",), {}),                           # no query
    ("recalls", ("consumer", "x"), {}),                       # too short
    ("recalls", ("consumer", "stroller"), {"make": "honda"}),
    ("recalls", ("vehicle", "civic"), {}),
    ("recalls", ("vehicle",), {"make": "honda", "model": "civic"}),
    ("recalls", ("vehicle",), {"make": "honda", "model": "civic", "year": "20"}),
    ("recalls", ("food", "flour"), {"limit": 0}),
    ("package_check", ("pip", "requests"), {}),
    ("package_check", ("pypi", ""), {}),
    ("pdf_extract", ("ftp://example.com/a.pdf",), {}),
    ("pdf_extract", ("https://example.com/a.pdf",), {"pages": "one"}),
])
def test_bad_inputs_fail_before_any_request(method, args, kw):
    gw = FakeGateway(paid=echo)
    with pytest.raises(InvalidInput) as e:
        run(getattr(make(gw), method)(*args, **kw))
    assert e.value.charged is False and isinstance(e.value, ValueError)
    assert gw.requests == []


def test_domain_verify_rejects_a_url_with_invalid_domain():
    gw = FakeGateway(paid=echo)
    with pytest.raises(InvalidDomain):
        run(make(gw).domain_verify("https://example.com/"))
    assert gw.requests == [] and issubclass(InvalidDomain, InvalidInput)


def test_budget_guard_applies_to_the_new_routes():
    gw = FakeGateway(quote=payment_required(requirement("10000")), paid=echo)   # $0.01
    with fake_payer() as payers:
        with pytest.raises(PriceTooHigh):
            run(make(gw, max_price_usd=0.005).pdf_extract("https://example.com/a.pdf"))
    assert payers[0].signed == 0


def test_not_found_is_not_charged():
    detail = {"error": "unknown_ticker", "message": "ZZZZ is not in SEC's ticker table", "charged": False}
    gw = FakeGateway(paid=httpx.Response(422, json={"detail": detail}))
    with fake_payer():
        with pytest.raises(NotCharged) as e:
            run(make(gw).sec_company("ZZZZ"))
    assert e.value.status_code == 422 and e.value.detail == detail


def test_sync_wrapper_has_the_new_methods():
    gw = FakeGateway(paid=echo)
    with fake_payer():
        client = AgentHarborSync(transport=gw.transport(), base_url="https://gw.test", account=ACCOUNT)
        assert client.recalls("drug", "ibuprofen", limit=2)["params"] == {
            "category": "drug", "query": "ibuprofen", "limit": "2"}
        assert client.package_check("cargo", "serde")["path"] == "/package-check"

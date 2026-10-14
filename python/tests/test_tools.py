import asyncio
import json
import sys
import types

import pytest

from agentharbor import PRICES_USD, TOOL_SPECS, AgentHarbor, AgentHarborSync

from helpers import ACCOUNT, FakeGateway, fake_payer

GATEWAY_PRICES = {"/scrape": "0.01", "/enrich": "0.05", "/audit": "0.05", "/company": "0.005", "/ai-crawlers": "0.01"}


def test_prices_match_the_gateway():
    assert PRICES_USD == GATEWAY_PRICES


def test_descriptions_are_honest_about_price_and_charging():
    names = [s.name for s in TOOL_SPECS]
    assert len(set(names)) == len(names) == 5
    for s in TOOL_SPECS:
        assert f"${s.price_usd}." in s.description, s.name
        assert "not charged" in s.description and "USDC on Base" in s.description
        assert len(s.description) < 1024
        assert s.name == "agentharbor_" + s.method
    # content_safety is only returned by /scrape, /enrich and /company
    with_scan = {s.path for s in TOOL_SPECS if "content_safety" in s.description}
    assert with_scan == {"/scrape", "/enrich", "/company"}


def _fake_langchain():
    """A minimal langchain_core.tools stand-in, used only when langchain-core is not installed."""
    mod = types.ModuleType("langchain_core.tools")

    class ToolException(Exception):
        pass

    class StructuredTool:
        def __init__(self, **kw):
            self.__dict__.update(kw)

        @classmethod
        def from_function(cls, **kw):
            return cls(**kw)

        async def ainvoke(self, args):
            try:
                return await self.coroutine(**args)
            except ToolException as e:
                if self.handle_tool_error is True:
                    return str(e)
                raise

    mod.StructuredTool, mod.ToolException = StructuredTool, ToolException
    pkg = types.ModuleType("langchain_core")
    pkg.tools = mod
    return {"langchain_core": pkg, "langchain_core.tools": mod}


@pytest.fixture
def lc():
    pytest.importorskip("pydantic")
    try:
        import langchain_core.tools  # noqa: F401
        yield
        return
    except ImportError:
        pass
    fakes = _fake_langchain()
    sys.modules.update(fakes)
    try:
        yield
    finally:
        for k in fakes:
            sys.modules.pop(k, None)


def test_get_tools_metadata(lc):
    from agentharbor.langchain import get_tools
    tools = get_tools(AgentHarbor(account=ACCOUNT))
    assert [t.name for t in tools] == [s.name for s in TOOL_SPECS]
    assert [t.description for t in tools] == [s.description for s in TOOL_SPECS]
    schema = tools[0].args_schema.model_json_schema()
    assert schema["required"] == ["domain"] and "example.com" in schema["properties"]["domain"]["description"]
    assert [t.name for t in get_tools(AgentHarborSync(), include=["company", "agentharbor_audit"])] == [
        "agentharbor_company", "agentharbor_audit"]


def test_tool_call_returns_json_and_surfaces_errors(lc):
    from agentharbor.langchain import get_tools
    gw = FakeGateway()
    with fake_payer():
        tools = {t.name: t for t in get_tools(AgentHarbor(account=ACCOUNT, transport=gw.transport()))}
        out = asyncio.run(tools["agentharbor_scrape"].ainvoke({"domain": "example.com"}))
        assert json.loads(out)["domain"] == "example.com"
        err = asyncio.run(tools["agentharbor_scrape"].ainvoke({"domain": "http://bad"}))
    assert "InvalidDomain (not charged)" in str(err)

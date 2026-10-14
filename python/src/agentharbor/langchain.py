"""LangChain tools: ``get_tools(client)`` returns one StructuredTool per paid route.

Requires ``pip install "agentharbor[langchain]"`` (and the ``x402`` extra to pay).
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Iterable

from ._tools import DOMAIN_DESCRIPTION, TOOL_SPECS, ToolSpec
from .client import AgentHarbor, AgentHarborSync
from .errors import AgentHarborError


def format_error(err: AgentHarborError) -> str:
    """The message an agent sees when a call fails or is refused."""
    charged = {False: "not charged", None: "charge status unknown"}.get(err.charged, "charged")
    return f"{type(err).__name__} ({charged}): {err}"


def _run_sync(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    coro.close()
    raise RuntimeError("called the sync tool inside an event loop; use ainvoke()")


def get_tools(client: AgentHarbor | AgentHarborSync, *, include: Iterable[str] | None = None) -> list:
    """LangChain StructuredTools for the paid routes.

    Args:
        client: an :class:`AgentHarbor` (or :class:`AgentHarborSync`) with a wallet configured.
            Its ``max_price_usd`` budget guard applies to every tool call.
        include: optional tool names (``agentharbor_company``) or methods (``company``) to keep.
    """
    try:
        from langchain_core.tools import StructuredTool, ToolException
        from pydantic import BaseModel, Field
    except ImportError as e:
        raise ImportError('LangChain tools need: pip install "agentharbor[langchain]"') from e

    async_client = client.client if isinstance(client, AgentHarborSync) else client
    wanted = set(include) if include is not None else None

    class DomainInput(BaseModel):
        domain: str = Field(description=DOMAIN_DESCRIPTION)

    def build(spec: ToolSpec):
        async def coroutine(domain: str) -> str:
            try:
                result = await getattr(async_client, spec.method)(domain)
            except AgentHarborError as e:
                raise ToolException(format_error(e)) from e
            return json.dumps(result, ensure_ascii=False)

        def func(domain: str) -> str:
            return _run_sync(coroutine(domain))

        return StructuredTool.from_function(
            func=func, coroutine=coroutine, name=spec.name, description=spec.description,
            args_schema=DomainInput, handle_tool_error=True)

    return [build(s) for s in TOOL_SPECS if wanted is None or s.name in wanted or s.method in wanted]

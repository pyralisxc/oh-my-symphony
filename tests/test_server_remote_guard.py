import asyncio

import pytest
from aiohttp import web

from symphony.server import run_server
from symphony.webapi import API_TOKEN_ENV


def test_remote_bind_without_api_token_fails_closed(monkeypatch):
    monkeypatch.delenv(API_TOKEN_ENV, raising=False)
    with pytest.raises(RuntimeError, match="refusing unauthenticated non-loopback bind"):
        asyncio.run(run_server(web.Application(), "0.0.0.0", 0))

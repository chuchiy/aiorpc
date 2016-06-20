import pytest
from aiorpc import Server, Client
import logging
from aiorpc.agent import keepalive
#logging.basicConfig(level=logging.DEBUG)
logging.basicConfig(level=logging.INFO)

@pytest.fixture
def keepalive_server(event_loop):
    agt = keepalive.KeepAliveAgent()
    srv = Server(('127.0.0.1', 0), agt, loop=event_loop)
    srv.start()
    return srv

@pytest.fixture
def keepalive_cli(event_loop, keepalive_server):
    cli = Client(keepalive_server.get_listener(), loop=event_loop)
    return cli

@pytest.fixture
def rpc_server_client(event_loop, rpc_app):
    """loop.run_until_complete can not run inside @pytest.mark.asyncio decor
    """
    srv = Server(('127.0.0.1', 0), rpc_app, loop=event_loop)
    srv.start()
    cli = Client(srv.get_listener(), loop=event_loop)
    return srv, cli


import pytest
from aiorpc.sample.foo import Foo
from aiorpc import client
import asyncio

@pytest.fixture
def rpc_app():
    return Foo()

@pytest.fixture
def dead_client(event_loop):
    return client.Client(('127.0.0.1', 1), loop=event_loop, dead_wait_retry_sec=0.1)

@pytest.mark.asyncio
def test_reflection(rpc_server_client):
    srv, c = rpc_server_client
    r = yield from c.request(b'\0reflection')
    assert [b'a', b'b', {b'name': b'c', b'default': None}, {b'name': b'd', b'default': 1}] == r[b'methods'][b'default_params']
    c.stop()
    srv.stop()

@pytest.mark.asyncio
def test_echo(rpc_server_client):
    srv, c = rpc_server_client
    p = [b'foo', b'bar']
    r = yield from c.request('echo', p)
    assert r == p
    c.stop()
    srv.stop()

@pytest.mark.asyncio
def test_dead_client(dead_client):
    assert False == dead_client.is_dead()
    for _ in range(client.DEFAULT_CONNECTION_ERROR_LIMIT):
        try:
            yield from dead_client.request('echo')
        except ConnectionError:
            pass
        assert False == dead_client.is_dead()
    try:
        yield from dead_client.request('echo')
    except ConnectionError:
        pass
    assert True == dead_client.is_dead()
    yield from asyncio.sleep(0.11)
    assert False == dead_client.is_dead()

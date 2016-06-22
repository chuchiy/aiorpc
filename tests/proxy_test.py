import pytest
from aiorpc import Server, Client
from aiorpc.sample.foo import Foo
from aiorpc.agent import proxy
import asyncio
import logging
log = logging.getLogger(__name__)

SERVER_APP_NUM = 3

@pytest.yield_fixture
def proxy_server(event_loop, keepalive_server):
    agt = proxy.ProxyAgent(keepalive_server.get_listener(), keepalive_update_interval=0.01)
    srv = Server(('127.0.0.1', 0), agt, loop=event_loop)
    srv.start()
    yield srv
    if event_loop.is_running():
        srv.stop()

@pytest.fixture
def proxy_cli(event_loop, proxy_server):
    cli = proxy.ProxyClient(proxy_server.get_listener(), loop=event_loop)
    return cli

@pytest.fixture
def foo_servers(event_loop, keepalive_server):
    srvs = []
    for _ in range(SERVER_APP_NUM):
        agt = Foo(keepalive_endp=keepalive_server.get_listener())
        srv = Server(('127.0.0.1', 0), agt, loop=event_loop)
        srv.start()
        srvs.append(srv)
    srvs = sorted(srvs, key=lambda s: s.get_listener())
    log.debug("foo srvs: %s", [s.get_listener() for s in srvs])
    return srvs

@pytest.mark.asyncio
def test_proxy_batch_invoke(proxy_cli, foo_servers, proxy_server, event_loop):
    yield from asyncio.sleep(0.02, loop=event_loop)
    batches = {'batches': [['sample.foo', 'echo', [i]] for i in range(10)]}
    r = yield from proxy_cli.request('batch_invoke', batches)
    assert [[i] for i in range(10)] == r

@pytest.mark.asyncio
def test_proxy_client_invoke(proxy_cli, foo_servers, proxy_server, event_loop):
    yield from asyncio.sleep(0.02, loop=event_loop)
    r = yield from proxy_cli.invoke('sample.foo', 'echo', ['a', 'b'])
    assert [b'a', b'b'] == r
    batches = proxy_cli.create_batch_invoke()
    batches.add('sample.foo', 'echo', ['a', 'b'])
    batches.add('sample.foo', 'add', 200, hint=1)
    batches.add('sample.foo', 'add', 20, hint=1)
    batches.add('sample.foo', 'add', 20, hint=2)
    r = yield from batches.execute()
    assert 4 == len(r)
    assert [b'a', b'b'] == r[0]
    assert 200 == r[1]
    assert 220 == r[2]
    assert 20 == r[3]


@pytest.mark.asyncio
def test_proxy_invoke(proxy_cli, foo_servers, proxy_server, event_loop):
    yield from asyncio.sleep(0.02, loop=event_loop)
    for i in range(len(foo_servers)):
        p = {'key': 'foo', 'val': i}
        r = yield from proxy_cli.request('invoke', {'method': 'set_cache', 'service': 'sample.foo', 'params': p})
        assert r == True
    for i, srv in enumerate(foo_servers):
        assert i == srv.get_app().cache[b'foo']
    #yield from proxy_cli.stop()
    #yield from keepalive_cli.stop()
    proxy_server.get_app().stop()
    

@pytest.mark.asyncio
def test_proxy_hint_invoke(proxy_cli, foo_servers, proxy_server, event_loop):
    yield from asyncio.sleep(0.02, loop=event_loop)
    cum = 0
    for cnt in range(10):
        r = yield from proxy_cli.request('invoke', {'method': 'add', 'service': 'sample.foo', 'params': [cnt], '__hint__': 100})
        cum += cnt
        assert r == cum
    proxy_server.get_app().stop()

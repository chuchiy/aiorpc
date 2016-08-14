# aiorpc: msgpack-rpc implementation based on python3 asyncio

## Features

- Full featured msgpack-rpc implementation(parallel pipeline, sync/async rpc call, etc). 
- Client pool for better server-2-server rpc call and connection management
- Convenience rpc spec extension with backward compatibile. such as request context, agent control command and named arguments support
- Builtin service-proxy and keepalive server for large scale services deployment

## Installation

```bash
$ python3 setup.py install
```

## Getting Started

### Server

```python
from aiorpc import Server

class Foo:
    """
    all method name do not start with `_` will be exposed as rpc method
    """
    def echo(self, message):
        return message

Server(('127.0.0.1', 10010), Foo()).run_forever()
``` 

### Client

```python
from aiorpc import Client
import asyncio

def call(c):
    r = yield from c.call('echo', 'foobar')
    return r

loop = asyncio.get_event_loop()
c = Client(('127.0.0.1', 10010), loop=loop)
print('call result:', loop.run_until_complete(call(c)))
loop.run_until_complete(c.stop())
```

## Service Agent

### Client Pool And Named Parameters

AgentMixin gives you client management in server agent

```python
from aiorpc import Server, AgentMixin

class Bar(AgentMixin):

    def aggregation(self, city, district=None):
        city_finder = self._get_client(('127.0.0.1', 10030)) #client getter from AgentMixin 
        item_finder = self._get_client(('127.0.0.1', 10040))
        items = yield from city_finder.request('items_in_city', {'city': city, 'district': district})
        items_data = [yield from item_finder.request('get_item', [item['id']]) for item in items]
        return items_data
    
    def context_holder(context, message):
        peer_endp = context('peername')
        client_ident = context('ident') 
        return peer_endp, message
```

for client code

```python
c.request('context_holder', {'message': 'Hello', '__ident__': 'test'})
```

aiorpc support named arugments expansion, you can use argument dict instead of argument list when invoke rpc request. When the first argument of service agent method is `context` or `ctx`, a callable would be assign to `context`. You can get value by calling context with key which asyncio transport **get_extra_info** supported and all dict param name starts/ends 
with __

### Control Method

When request method starts with `\0`, aiorpc server will consider it as control command. Currently only `reflection` command 
is supported, which return all the method info in the service agent

```python
c.request('\0reflection') #will return {'methodname': ['arg0', 'arg1', {'name': 'arg2', 'default': 'abc'}], ...}
```

## Proxy And KeepAlive Service Agent

aiorpc comes with some built-in agent server:

### KeepAlive Server

`aiorpc.agent.keepalive` is a register and discovery server. 

```bash
$ python3 -m aiorpc.agent.keepalive
```
rpc server can use `HeartbeatMixin` for handy register to keepalive server.

```python
from ..agent.keepalive import HeartbeatMixin

class Foo(HeartbeatMixin):

    def __init__(self, *, keepalive_endp=None, service_name='sample.foo'):
        self._service_name = service_name
        self._keepalive_endp = keepalive_endp

    def _activated(self, listener):
        if self._keepalive_endp:
            #start heartbeat fiber to keepalive
            self._activate_heartbeat(self._keepalive_endp, self._service_name, listener[1])
```

KeepAlive service expose two rpc method:

```
# service registration and heartbeat
heartbeat(name, host, port, ident=None) 
# get all activated service
get_services() -> {"service_name": [{"ident": "srv1", "endpoint": ["8.8.8.8", 6000]}, ...], "service_name2": .... }
```

### Proxy Server

`aioprc.agent.proxy` is a rpc request proxy/routing/load-balance server usually bind at local port.  
Proxy agent will periodically load all the rpc service current alive from keepalive server.
Local application/service could call remote rpc service by registered name through proxy

```bash
$ python3 -m aiorpc.agent.proxy endpoint_to_keepalive_server
```
Proxy serviec expose two rpc method

```
# call rpc method by service name registered at keepalive server
# you can use __hint__ in params to indicate request goes to specific server if you register multi server for a same service
invoke(service, method, params)

# parallel call multi rpc method and get results
# batches is list of [service, method, params] or [service, method, params, hint]
batch_invoke(batches)
```
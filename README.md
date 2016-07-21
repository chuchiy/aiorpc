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

aiorpc support named arugments expand, you can use argument dict instead of argument list when invoke rpc request. 
When the first argument of service agent method is `context` or `ctx`, a callable would be assign to `context`. You can
get value by calling context with key which asyncio transport **get_extra_info** supported and all dict param name starts/ends 
with __

### Control Method

When request method starts with `\0`, aiorpc server will consider it as control command. Currently only `reflection` command 
is supported, which return all the method info in the service agent

```python
c.request('\0reflection') #will return {'methodname': ['arg0', 'arg1', {'name': 'arg2', 'default': 'abc'}], ...}
```

## Proxy And KeepAlive Service Agent

aiorpc comes with some built-in agent server:

- `aiorpc.agent.proxy`: request proxy/routing/load-balance.
- `aiorpc.agent.keepalive`: agent register and discovery.


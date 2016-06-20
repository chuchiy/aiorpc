# aiorpc: python3 asyncio powered msgpack-rpc implementation 

## Features

- Full featured msgpack-rpc implementation(parallel pipeline, sync/async rpc call, etc). 
- Real-world client pool for better server-2-server rpc call and connection management
- Convenience backward compatibile rpc spec extension. such as request context, agent control command and named arguments support
- Builtin service-proxy and keepalive server for production ready rpc services deployment

## Getting Started

### Server

```python
from aiorpc import Server

class Foo(object):

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

## Installation

```bash
$ python3 setup.py install
```



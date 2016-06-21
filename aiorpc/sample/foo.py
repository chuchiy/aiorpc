from ..server import Server
from ..agent.keepalive import HeartbeatMixin
from ..agent import utils
import asyncio
import logging

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())

class Foo(HeartbeatMixin, object):

    def __init__(self, *, keepalive_endp=None, service_name='sample.foo'):
        self._service_name = service_name
        self._keepalive_endp = keepalive_endp
        self.cache = {}
        self.val = 0

    def _activated(self, listener):
        if self._keepalive_endp:
            self._activate_heartbeat(self._keepalive_endp, self._service_name, listener[1])

    def default_params(self, a, b, c=None, d=1):
        return a,b,c,d

    def set_cache(self, key, val):
        self.cache[key] = val
        return True

    def echo(self, *args, **kwargs):
        return args or kwargs

    def notify(self, txt):
        log.info('notify: %s', txt)

    def sleep(self, sec):
        yield from asyncio.sleep(sec, loop=self._get_aio_loop())
        return True

    def add(self, val):
        self.val += val
        return self.val

def run(cmd_args=None):
    import argparse
    parser = argparse.ArgumentParser(description='test foo server')
    parser.add_argument('--keepalive', help="host:port of keepalive server")
    parser.add_argument("-b", "--bind", default='127.0.0.1:0', help="host:port to listened for server")
    with utils.set_common_command_args(parser, cmd_args) as args:
        if args.keepalive:
            assert ':' in args.keepalive, 'keepalive server address is host:port'
        assert ':' in args.bind, "proxy bind address should be host:port"
        app = Foo(keepalive_endp=args.keepalive.split(':', 1) if args.keepalive else None)
        srv = Server(args.bind.split(':', 1), app)
        srv.start()
    srv.run_forever()

if __name__ == '__main__':
    run()

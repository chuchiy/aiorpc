from ..server import Server, AgentMixin, run
from ..client import Client
import asyncio
import logging
import itertools
from . import utils

log = logging.getLogger(__name__)

class ProxyAgent(AgentMixin, object):

    def __init__(self, keepalive_endp, keepalive_update_interval=3):
        self._keepalive_endp = keepalive_endp
        self._keepalive_update_interval = keepalive_update_interval
        self._keepalive = None
        self._services = {}
        self._services_cycle = {}
        self._services_update_task = None

    def _activated(self, listener):
        self._keepalive = Client(self._keepalive_endp, loop=self._get_aio_loop())
        self._services_update_task = asyncio.async(self._get_services(), loop=self._get_aio_loop())

    def _get_services(self):
        while True:
            if not self._get_aio_loop().is_running():
                log.info('event loop is not running. exit')
                return
            try:
                services = yield from self._keepalive.request('get_services')
                log.debug("get services %s", services)
                if self._services != services:
                    log.debug("update services %s", self._services)
                    self._services = services
                    self._services_cycle = {srvn:itertools.cycle(endps) for srvn, endps in services.items()}
            except KeyboardInterrupt:
                raise
            except:
                log.exception("update services error")
            if self._get_aio_loop() and self._get_aio_loop().is_running():
                log.debug('get services sleep %s for aio loop %s', self._keepalive_update_interval, self._get_aio_loop())
                yield from asyncio.sleep(self._keepalive_update_interval, loop=self._get_aio_loop())
    
    def invoke(self, ctx, service, method, params):
        client = self._get_client_by_service(service, ctx('__hint__'))
        return client.request(method, params)

    def batch_invoke(self, ctx, batches):
        futures = []
        for (service, method, params) in batches:
            future = yield from self._get_client_by_service(service, ctx('__hint__')).send_quest(method, params) 
            futures.append(future)
        results = yield from asyncio.gather(*futures, loop=self._get_aio_loop())
        return results

    def stop(self):
        log.info("stop agent with loop %s", self._get_aio_loop())
        self._services_update_task.cancel()
        self._set_aio_loop(None)

    def _get_client_by_service(self, service, hint=None):
        endps = self._services[service]
        cycle_endps = self._services_cycle[service]
        entry = next(cycle_endps) if not hint else endps[hint % len(endps)]
        return self._get_client(entry[b'endpoint'])

def run(cmd_args=None):
    import argparse
    parser = argparse.ArgumentParser(description='aiorpc service proxy')
    parser.add_argument('keepalive', help="host:port of keepalive server")
    parser.add_argument("-b", "--bind", default='127.0.0.1:9999', help="host:port to listened for proxy")
    parser.add_argument("--workers", default='0', help="num of workers to start. default is 0, do not use multi process", type=int)
    with utils.set_common_command_args(parser, cmd_args) as args:
        assert ':' in args.keepalive, 'keepalive server address is host:port'
        assert ':' in args.bind, "proxy bind address should host:port"
        app = ProxyAgent(args.keepalive.split(':', 1))
        srv = Server(args.bind.split(':', 1), app)
        srv.start()
    srv.run_forever()


if __name__ == '__main__':
    run()
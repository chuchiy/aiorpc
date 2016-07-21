from ..server import Server, AgentMixin, run, socket_bind
from ..client import Client
import asyncio
import logging
import itertools
from . import utils

log = logging.getLogger(__name__)

class BatchInvokeTask(object):

    def __init__(self, client):
        self._client = client
        self._batches = []
        self._results = None

    def add(self, service, method, params, hint=None):
        assert not hint or isinstance(hint, int), 'hint value should be int'
        self._batches.append((service, method, params, hint))
        idx = len(self._batches) - 1
        def get_result():
            return self._results[idx]
        return get_result

    def execute(self):
        self._results = yield from self._client.request('batch_invoke', {"batches": self._batches})
        return self._results

class ProxyClient(Client):

    def invoke(self, service, method, params, hint=None):
        p = {'service': service, 'method': method, 'params': params}
        assert not hint or isinstance(hint, int), 'hint value should be int'
        if hint:
            p['__hint__'] = hint
        return self.request('invoke', p)

    def create_batch_invoke(self):
        return BatchInvokeTask(self)

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
            except asyncio.CancelledError as e:
                log.warning("request task is cancelled")
                break
            except:
                log.exception("update services error")

            if self._get_aio_loop() and self._get_aio_loop().is_running():
                log.debug('get services sleep %s for aio loop %s', self._keepalive_update_interval, self._get_aio_loop())
                yield from asyncio.sleep(self._keepalive_update_interval, loop=self._get_aio_loop())
    
    def invoke(self, ctx, service, method, params):
        client = self._get_client_by_service(service, ctx('__hint__'))
        return client.request(method, params)

    def batch_invoke(self, batches):
        futures = []
        for item in batches:
            hint = None
            if len(item) == 4:
                service, method, params, hint = item
            elif len(item) == 3:
                service, method, params = item
            else:
                raise RuntimeError("invalid batch invoke item: {}".format(item))
            future = yield from self._get_client_by_service(service, hint).send_quest(method, params) 
            futures.append(future)
        results = yield from asyncio.gather(*futures, loop=self._get_aio_loop())
        return results

    def stop(self):
        log.info("stop agent with loop %s", self._get_aio_loop())
        self._keepalive.stop()
        self._services_update_task.cancel()
        self._set_aio_loop(None)

    def _get_client_by_service(self, service, hint=None):
        endps = self._services[service]
        cycle_endps = self._services_cycle[service]
        entry = next(cycle_endps) if not hint else endps[hint % len(endps)]
        return self._get_client(entry['endpoint'])

def server_run_forever(*args, **kwargs):
    def wrap(**wkwargs):
        kwargs.update(wkwargs)
        Server(*args, **kwargs).run_forever()
        
    return wrap

def run(cmd_args=None):
    import argparse
    from ..multiproc import Supervisor
    parser = argparse.ArgumentParser(description='aiorpc service proxy')
    parser.add_argument('keepalive', help="host:port of keepalive server", type=utils.type_endp)
    parser.add_argument("-b", "--bind", default='127.0.0.1:9999', help="host:port to listened for proxy", type=utils.type_endp)
    parser.add_argument("--workers", default='0', help="num of workers to start. default is 0, do not use multi process", type=int)
    with utils.set_common_command_args(parser, cmd_args) as args:
        app = ProxyAgent(args.keepalive)
        if args.workers:
            listen_sock = socket_bind(args.bind[0], args.bind[1])
        else:
            srv = Server(args.bind, app)
            srv.start()

    if args.workers:
        Supervisor(args.workers, server_run_forever(listen_sock, app)).start()
    else:
        srv.run_forever()

if __name__ == '__main__':
    run()

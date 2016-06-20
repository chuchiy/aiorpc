from ..server import AgentMixin, Server
import time
import asyncio
import logging
import operator
from collections import defaultdict
from . import utils

log = logging.getLogger(__name__)

class HeartbeatMixin(AgentMixin):

    def _activate_heartbeat(self, keepalive_endp, service_name, agent_port, agent_host=None, agent_ident=None, keepalive_interval=3):
        keepalive = self._get_client(keepalive_endp)
        @asyncio.coroutine
        def keepalive_task():
            while True:
                try:
                    params = [service_name, agent_host, agent_port, agent_ident]
                    yield from keepalive.request('heartbeat', params)
                    log.debug("keepalive send heartbeat %s", params)
                except KeyboardInterrupt:
                    raise
                except:
                    log.exception("keepalive heartbeat error")
                yield from asyncio.sleep(keepalive_interval, loop=self._get_aio_loop())

        asyncio.async(keepalive_task(), loop=self._get_aio_loop())

class KeepAliveAgent(AgentMixin, object):

    def __init__(self, hearbeat_timeout=30, service_check_interval=5):
        self._services = defaultdict(dict)
        self._hearbeat_timeout = hearbeat_timeout
        self._service_check_interval = service_check_interval

    def _activated(self, listener):
        self._set_service_check_task()

    def _set_service_check_task(self):
        self._get_aio_loop().call_later(self._service_check_interval, self._check_service)
    
    def _check_service(self):
        log.debug('start check service status')
        services = defaultdict(dict) 
        now = time.time() 
        for name, srvconf in self._services.items(): 
            for endp, conf in srvconf.items(): 
                if now - conf['mtime'] <= self._hearbeat_timeout: 
                    services[name][endp] = conf 
                else: 
                    log.info('remove timeout service %s %s %s', name, endp, conf)
        self._services = services
        self._set_service_check_task()

    def get_services(self):
        """ -> {"service_name": [{"ident": "srv1", "endpoint": ["8.8.8.8", 6000]}, {"ident": "srv2", "endpoint": ["9.9.9.9", 6000]}], "service_name2": .... }
        """
        return {name:[{"ident": endp_rec["ident"], "endpoint":endp} for endp, endp_rec in sorted(conf.items(), key=operator.itemgetter(0))] for name, conf in self._services.items()}

    def heartbeat(self, ctx, name, host, port, ident=None):
        peerip, peerport = ctx('peername')
        now = time.time()
        host = host or peerip
        endp = (host, port) 
        self._services[name][endp] = {'ident': ident, 'mtime': int(now)} 
        return True

def run(cmd_args=None):
    import argparse
    parser = argparse.ArgumentParser(description='keepalive server')
    parser.add_argument("-b", "--bind", default='0.0.0.0:7999', help="host:port to listened for server")
    with utils.set_common_command_args(parser, cmd_args) as args:
        assert ':' in args.bind, "server bind address should be host:port"
        app = KeepAliveAgent()
        srv = Server(args.bind.split(':', 1), app)
        srv.start()
    srv.run_forever()

if __name__ == '__main__':
    run()


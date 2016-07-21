import asyncio
import logging
from . import message
import socket
from .utils import packet_unpacker, packet_pack
import msgpack
log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())

DEFAULT_CLIENT_REQUEST_TIMEOUT = 10
DEFAULT_CLIENT_DEAD_RETRY_SEC = 5
DEFAULT_CONNECTION_ERROR_LIMIT = 3

class ReplyError(RuntimeError):
    pass


class NaiveClient(object):

    def __init__(self, endpoint):
        self._endpoint = endpoint
        self._msgid = 0
        self._unpacker = packet_unpacker()
        self._sock = None

    def connect(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        log.debug("socket connect to %s", self._endpoint)
        sock.connect(self._endpoint)
        self._sock = sock

    def call(self, method, *args, **kwargs):
        if args and kwargs:
            raise RuntimeError('*args and *kwargs should not be both given for rpc call')
        return self.request(method, args or kwargs or None)

    def request(self, method, params=None):
        if not self._sock:
            self.connect()
        rmsgid = self._msgid
        self._msgid += 1
        quest = [message.TYPE_REQUEST, rmsgid, method, params]
        log.debug("send %s", quest)
        dat = packet_pack(quest)
        self._sock.sendall(dat)
        while True:
            dat = self._sock.recv(4096*4)
            self._unpacker.feed(dat)
            try:
                resp = self._unpacker.unpack()
                break
            except msgpack.exceptions.OutOfData as ex:
                continue
        log.debug("recv %s", resp)
        assert resp[0] == message.TYPE_RESPONSE, 'recv msg is not response msg'
        assert resp[1] == rmsgid, 'resp msg id {} is not equal to request msg id {}'.format(resp[1], rmsgid)
        if resp[2]:
            raise ReplyError(*resp[2])
        else:
            return resp[3]

class Client:

    def __init__(self, endpoint, *, loop=None, request_timeout=None, dead_wait_retry_sec=None, conn_error_limit=None):
        self._loop = loop or asyncio.get_event_loop()
        self._endpoint = endpoint
        self._msgid = 0
        self._unpacker = packet_unpacker()
        self._futures = {}
        self._request_timeout = request_timeout or DEFAULT_CLIENT_REQUEST_TIMEOUT
        self.reader = self.writer = None
        self._conn_lock = asyncio.Lock(loop=self._loop)
        self._connected = False
        self._dead_wait_retry_sec = dead_wait_retry_sec or DEFAULT_CLIENT_DEAD_RETRY_SEC
        self._conn_error_limit = conn_error_limit or DEFAULT_CONNECTION_ERROR_LIMIT
        self._conn_error_count = 0 
        self._last_conn_error_time = None
        self.recv_task = None

    def endpoint(self):
        return self._endpoint

    def is_dead(self):
        if self._last_conn_error_time and self._loop.time() - self._last_conn_error_time >= self._dead_wait_retry_sec:
            self._conn_error_count = 0 
            self._last_conn_error_time = None
            return False
        else:
            if self._conn_error_count > self._conn_error_limit:
                return True
            else:
                return False

    def is_connected(self):
        return self._connected

    @asyncio.coroutine
    def connect(self):
        with (yield from self._conn_lock):
            if self.reader and self.writer:
                return
            log.debug("socket connect to %s", self._endpoint)
            host, port = self._endpoint
            try:
                self.reader, self.writer = yield from asyncio.open_connection(host, port, loop=self._loop)
                self._connected = True
                self.recv_task = asyncio.async(self.reader.read(32768), loop=self._loop)
                self.recv_task.add_done_callback(self.recv_reply)
            except ConnectionError as cerr:
                self._conn_error_count += 1
                self._last_conn_error_time = self._loop.time()
                raise

    def send_quest(self, method, params):
        if not self.reader or not self.writer:
            yield from self.connect()
        quest = [message.TYPE_REQUEST, self._msgid, method, params]
        log.debug("send %s", quest)
        dat = packet_pack(quest)
        self.writer.write(dat)
        future = asyncio.Future(loop=self._loop)
        self._futures[self._msgid] = future
        self._msgid += 1
        return asyncio.wait_for(future, self._request_timeout, loop=self._loop)

    def notify(self, method, params=None):
        if not self.reader or not self.writer:
            yield from self.connect()
        quest = [message.TYPE_NOTIFICATION, method, params]
        log.debug("send %s", quest)
        dat = packet_pack(quest)
        self.writer.write(dat)

    def call(self, method, *args, **kwargs):
        if args and kwargs:
            raise RuntimeError('*args and *kwargs should not be both given for rpc call')
        return self.request(method, args or kwargs or None)

    def request(self, method, params=None):
        f = yield from self.send_quest(method, params)
        try:
            reply = yield from asyncio.wait_for(f, self._request_timeout, loop=self._loop)
            return reply
        except asyncio.TimeoutError as e:
            raise TimeoutError('request exceed timeout limit {}s'.format(self._request_timeout))

#    @asyncio.coroutine
    def recv_reply(self, future):
#        dat = yield from self.reader.read(4096*4)
        if future.cancelled():
            return
        ex = future.exception()
        if ex:
            raise ex
        dat = future.result()
        if not dat:
            log.debug("recv reply from %s error. close connection", self._endpoint)
            self.writer.close()
            self.writer = self.reader = None
            return
        self._unpacker.feed(dat)
        try:
            for msg in self._unpacker:
                log.debug("recv %s", msg)
                assert msg[0] == message.TYPE_RESPONSE, 'recv msg is not response msg'
                if msg[1] not in self._futures:
                    log.error('recv unknown msgid %s %s', msg[1], msg)
                else:
                    fut = self._futures[msg[1]]
                    del self._futures[msg[1]]
                    if msg[2]:
                        fut.set_exception(ReplyError(*msg[2]))
                    else:
                        fut.set_result(msg[3])
            #self.recv_task = asyncio.async(self.recv_reply(), loop=self._loop)
            self.recv_task = asyncio.async(self.reader.read(32768), loop=self._loop)
            self.recv_task.add_done_callback(self.recv_reply)
        except:
            self.writer.close()
            self.writer = self.reader = None
            self._connected = False
            raise

    def stop(self):
        if self.writer:
            self.writer.close()
        if self.recv_task:
            self.recv_task.cancel()
        self.reader = self.writer = None

#    def __del__(self):
#        if self.reader and self.writer:
#            self.stop()

class ClientPool(object):

    def __init__(self, loop, client_class=Client, request_timeout=None, raise_when_dead=True):
        self._clients = {}
        self._loop = loop
        self._client_class = client_class 
        self._request_timeout = request_timeout
        self._raise_when_dead = raise_when_dead

    def get(self, endpoint, client_class=None):
        endpoint = tuple(endpoint)
        c = self._clients.get(endpoint)
        if not c:
            client_class = client_class or self._client_class
            c = client_class(endpoint, loop=self._loop, request_timeout=self._request_timeout)
            self._clients[endpoint] = c
        if self._raise_when_dead and c.is_dead():
            raise RuntimeError('client {} for {} is dead. try later'.format(c, c.endpoint()))
        return c

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)

    def run(c):
        message = ['Foo', 'Bar', 'Hello World!']
        r = yield from c.request('echo', message)
        print("Reply:", r)
        d = yield from c.call('echo', 'a', 'b')
        print("Reply:", d)
        try:
            yield from c.request('echo1', message)
        except ReplyError as e:
            print("Error:", e)

    def call_single(c):
        yield from c.notify('recv_notify', {'txt': 'foobar'})
        try:
            yield from c.request('sleep', 11)
        except TimeoutError as e:
            print("TimeoutError:", e)


    loop = asyncio.get_event_loop()
    c = Client(('127.0.0.1', 8888), loop=loop)
    tasks = [run(c) for _ in range(10)]
    tasks.append(call_single(c))
    loop.run_until_complete(asyncio.wait(tasks))
#    loop.run_until_complete(call_single(c))
    loop.run_until_complete(c.stop())

import asyncio
from asyncio import streams
from . import client
from . import server
import os
import logging
import signal

log = logging.getLogger(__name__)

class PipeClient(client.Client):

    def __init__(self, reader, writer, **kwargs):
        super().__init__(None, **kwargs)
        self.reader = reader
        self.writer = writer
        #self.recv_task = asyncio.async(self.recv_reply(), loop=self._loop)
        self.recv_task = asyncio.async(self.reader.read(32768), loop=self._loop)
        self.recv_task.add_done_callback(self.recv_reply)

    def stop(self):
        self.recv_task.cancel()

    @asyncio.coroutine
    def connect(self):
        raise RuntimeError('{} does not support connect'.format(__class__))

class PipeServer(server.BaseServer):

    def __init__(self, reader, writer, app, **kwargs):
        self.reader = reader
        self.writer = writer
        self._task = None
        super().__init__(app, **kwargs)

    def start(self):
        self._task = asyncio.async(self._handler(self.reader, self.writer), loop=self._loop)

    def run_forever(self):
        if not self._task:
            self.start()
        self._loop.run_until_complete(self._task)

class PipeStream:

    def __init__(self, read_fd, write_fd, loop):
        self._read_fd = read_fd
        self._write_fd = write_fd
        self._read_file = os.fdopen(read_fd, 'rb')
        self._write_file = os.fdopen(write_fd, 'wb')
        self._loop = loop

    def close(self):
        #os.close(self._read_fd)
        #os.close(self._write_fd)
        pass

    def make_stream_pair(self):
        self._read_stream = streams.StreamReader(loop=self._loop)
        def read_proto_factory():
            return streams.StreamReaderProtocol(self._read_stream, loop=self._loop)
        self._read_transport, self._read_protocol = yield from self._loop.connect_read_pipe(read_proto_factory, self._read_file)
        self._write_transport, self._write_protocol = yield from self._loop.connect_write_pipe(asyncio.Protocol, self._write_file)
        self._write_stream = streams.StreamWriter(self._write_transport, self._read_protocol, self._read_stream, self._loop) 
        return self._read_stream, self._write_stream

class PingAgent:

    def ping(self):
        return 'pong'

class Worker:

    def __init__(self, loop, server, *, heartbeat_check_interval=2):
        self._loop = loop
        self._server = server
        self._started = False
        self._halt = False
        self._hb_check_interval = heartbeat_check_interval
        self.start()

    def do_heartbeat(self):
        while True:
            try:
                r = yield from self._hb_client.call('ping')
                assert r == 'pong'
                yield from asyncio.sleep(self._hb_check_interval, loop=self._loop)
            except GeneratorExit:
                log.warning('heartbeat coro stop')
                return
            except:
                if not self._halt:
                    log.exception('parent of child {} heartbeat error. re-fork child'.format(self._child_pid))
                else:
                    log.exception('parent of child {} heartbeat error.'.format(self._child_pid))
                break
        if not self._halt:
            self.kill_child()
            self.start()

    def kill_child(self):
        self._started = False
        self._pipe_stream.close() 
        os.kill(self._child_pid, signal.SIGKILL)

    def get_child_pid(self):
        return self._child_pid

    def parent_heartbeat(self, read_fd, write_fd):
        pstream = PipeStream(read_fd, write_fd, self._loop)
        stream_reader, stream_writer = yield from pstream.make_stream_pair()
        self._hb_client = PipeClient(stream_reader, stream_writer, loop=self._loop)
        self._pipe_stream = pstream
        self._hb_task = asyncio.async(self.do_heartbeat(), loop=self._loop)

    def child_heartbeat(self, read_fd, write_fd):
        app = PingAgent()
        pstream = PipeStream(read_fd, write_fd, self._loop)
        stream_reader, stream_writer = self._loop.run_until_complete(pstream.make_stream_pair())
        self._hb_srv = PipeServer(stream_reader, stream_writer, app, loop=self._loop)
        self._hb_srv.start()
        self._pipe_stream = pstream

    def start(self):
        assert not self._started
        self._started = True

        read_from_parent, write_to_child = os.pipe()
        read_from_child, write_to_parent = os.pipe()

        pid = os.fork()
        if pid:
            # parent
            log.info('create subprocess %s', pid)
            self._child_pid = pid
            os.close(read_from_parent)
            os.close(write_to_parent)
            asyncio.async(self.parent_heartbeat(read_from_child, write_to_child), loop=self._loop)
        else:
            # child
            os.close(read_from_child)
            os.close(write_to_child)

            log.info('enter subprocess')
            # cleanup after fork
            asyncio.set_event_loop(None)
            self._loop = asyncio.new_event_loop()
            self.child_heartbeat(read_from_parent, write_to_parent)
            self._server(loop=self._loop)

    def halt(self):
        self._halt = True
        self._hb_task.cancel()
        self._hb_client.stop()

class Supervisor:

    def __init__(self, worker_number, server_starter):
        self._worker_number = worker_number
        self._server_starter = server_starter
        self._workers = []
        self.loop = asyncio.get_event_loop()
    
    def stop(self):
        self.loop.remove_signal_handler(signal.SIGTERM)
        workers = self._workers
        self._workers = []
        for wkr in workers:
            wkr.halt()
            log.info('kill subporcess %s', wkr.get_child_pid())
            os.kill(wkr.get_child_pid(), signal.SIGTERM) 

        for task in asyncio.Task.all_tasks():
            task.cancel()

        self.loop.close()

    def start(self):

        # start processes
        for idx in range(self._worker_number): 
            log.debug("start new process %s", idx)
            self._workers.append(Worker(self.loop, self._server_starter)) 

#        self.loop.add_signal_handler(signal.SIGINT, self.stop) 
        self.loop.add_signal_handler(signal.SIGTERM, self.stop) 
        try:
            self.loop.run_forever()
        except KeyboardInterrupt as ex:
            pass

        self.stop()

if __name__ == '__main__':
    from .server import Server, socket_bind
    from .sample import foo
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)-6s %(levelname)s %(process)s %(name)s.%(funcName)s:%(lineno)d : %(message)s')

    def server_run_forever(*args, **kwargs):
        def wrap(**wkwargs):
            kwargs.update(wkwargs)
            if not kwargs.get('loop'):
                loop = asyncio.new_event_loop()
                kwargs['loop'] = loop
            Server(*args, **kwargs).run_forever()
            
        return wrap

    class SubProcApp(foo.Foo):

        def get_pid(self):
            return os.getpid()

    app = SubProcApp()
    sock = socket_bind('127.0.0.1', 19900)
    Supervisor(4, server_run_forever(sock, app)).start()

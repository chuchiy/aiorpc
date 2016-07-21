import msgpack
import functools

packet_pack = functools.partial(msgpack.packb, use_bin_type=True)
packet_unpacker = functools.partial(msgpack.Unpacker, encoding='utf-8')

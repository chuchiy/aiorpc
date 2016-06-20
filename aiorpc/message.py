from collections import namedtuple

TYPE_REQUEST = 0
TYPE_RESPONSE = 1
TYPE_NOTIFICATION = 2

Request = namedtuple('Request', ['mtype', 'mid', 'method', 'params'])
Response = namedtuple('Response', ['mtype', 'mid', 'error', 'result'])
Notification = namedtuple('Notification', ['mtype', 'method', 'params'])

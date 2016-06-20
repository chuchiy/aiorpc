from contextlib import contextmanager
import os
import pwd
import logging


@contextmanager
def set_common_command_args(parser, cmd_args=None):
    parser.add_argument("-u", "--user", help="set running user for process")
    parser.add_argument("--logfile", help="path of log file")
    parser.add_argument("--loglevel", default="info", help="logging level. debug/info/warning/error/critical. default is info")
    parser.add_argument("--pid", help="path of pid file")
    args = parser.parse_args(cmd_args)
    if args.user:
        uid = pwd.getpwnam(user).pw_uid
        os.setuid(uid)

    log_numeric_level = getattr(logging, args.loglevel.upper(), None)
    if not isinstance(log_numeric_level, int):
        raise ValueError('Invalid log level: %s' % args.loglevel)
    cfdict = {'level': log_numeric_level, 'format': '%(asctime)-6s %(levelname)s %(process)s %(name)s.%(funcName)s:%(lineno)d : %(message)s'}
    if args.logfile:
        cfdict['filename'] = args.logfile
    logging.basicConfig(**cfdict)
    yield args
    if args.pid:
        with open(args.pid, 'w+') as fp:
            fp.write(str(os.getpid()))

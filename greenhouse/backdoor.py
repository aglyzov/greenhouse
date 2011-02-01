"""
These functions enable running an additional server in greenhouse server
processes, which accepts connections and runs interactive python interpreters
on them, enabling entirely flexible and ad-hoc server administration at
runtime.

.. warning:: **backdoors are a gaping security hole**

    Make certain that you either use ``"127.0.0.1"`` as the host on which to
    listen for connections so that it will only accept connection requests made
    locally. If you must connect to it from another machine, at least make sure
    it is behind a firewall that will block the backdoor port.
"""
from __future__ import with_statement

import code
import contextlib
import socket
import sys
import traceback
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from greenhouse import io, scheduler


__all__ = ["run_backdoor", "backdoor_handler"]


PREAMBLE = "Python %s on %s" % (sys.version, sys.platform)
PS1 = getattr(sys, "ps1", ">>> ")
PS2 = getattr(sys, "ps2", "... ")


def run_backdoor(address, namespace=None):
    """start a server that runs python interpreters on connections made to it

    .. note::
        this function blocks effectively indefinitely -- it runs the listening
        socket loop in the current greenlet. to keep the current greenlet free,
        :func:`schedule<greenhouse.scheduler.schedule>` this function.

    :param address:
        the address on which to listen for backdoor connections, in the form of
        a two-tuple ``(host, port)``
    :type address: tuple
    :param namespace:
        an optional dictionary to use as the global namespace for connections.
        if this is provided, then it will be shared among all connections made
        to this server, unless the default value of ``None`` is used, in which
        case a distinct dictionary is created for every connection.
    :type namespace: dict or None
    """
    serversock = io.Socket()
    serversock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    serversock.bind(address)
    serversock.listen(socket.SOMAXCONN)

    while 1:
        clientsock, address = serversock.accept()
        scheduler.schedule(backdoor_handler, args=(clientsock, namespace))


def backdoor_handler(clientsock, namespace=None):
    """start an interactive python interpreter on an existing connection

    .. note::
        this function will block for as long as the connection remains alive.

    :param sock: the socket on which to serve the interpreter
    :type sock: :class:`Socket<greenhouse.io.sockets.Socket>`
    :param namespace:
        the local namespace dict for the interpreter, or None to have the
        function create its own empty namespace
    :type namespace: dict or None
    """
    console = code.InteractiveConsole({} if namespace is None else namespace)
    clientfile = clientsock.makefile('r')
    multiline_statement = []
    stdout, stderr = StringIO(), StringIO()

    clientsock.sendall(PREAMBLE + "\n" + PS1)

    for input_line in clientsock.makefile('r'):
        input_line = input_line.rstrip()
        source = '\n'.join(multiline_statement) + input_line
        response = ''

        with _wrap_stdio(stdout, stderr):
            result = console.runsource(source)

        response += stdout.getvalue()
        err = stderr.getvalue()
        if err:
            response += err

        if err or not result:
            multiline_statement = []
            response += PS1
        else:
            multiline_statement.append(input_line)
            response += PS2

        clientsock.sendall(response)


@contextlib.contextmanager
def _wrap_stdio(stdout, stderr):
    stdout.seek(0)
    stderr.seek(0)
    stdout.truncate()
    stderr.truncate()

    real_stdout = sys.stdout
    real_stderr = sys.stderr

    sys.stdout = stdout
    sys.stderr = stderr

    yield

    sys.stdout = real_stdout
    sys.stderr = real_stderr

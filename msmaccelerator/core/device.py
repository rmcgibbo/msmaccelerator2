"""
Base class for devices that connect to the msmaccelerator server that exposes
them as a configurable command-line app and provides the biolerplate for them
to get registered with the server and start their work.
"""

##############################################################################
# Imports
##############################################################################

import zmq
import uuid
import yaml

from IPython.utils.traitlets import Int, Unicode, Bytes

from .app import App
from ..core.message import Message, pack_message

##############################################################################
# Classes
##############################################################################


class Device(App):
    """Base class for MSMAccelerator devices. These are processes that request data
    from the server, and run on a ZMQ REQ port.

    Current subclasses include Simulator and Modeler.

    When the device boots up, it will send a message to the server with the
    msg_type 'register_{ClassName}', where ClassName is the name of the subclass
    of device that was intantiated. When it receives a return message, that
    the method on_startup_message() will be called.

    Note, if you want to interface directly with the ZMQ socket, it's just
    self.socket
    """

    name = 'device'
    path = 'msmaccelerator.core.device.Device'
    short_description = 'Base class for MSMAccelerator devices'
    long_description = '''Contains common code for processes that connect to
        the msmaccelerator server to request data and do stuff'''

    zmq_port = Int(12345, config=True, help='ZeroMQ port to connect to the server on')
    zmq_url = Unicode('127.0.0.1', config=True, help='URL to connect to server with')
    uuid = Bytes(help='Unique identifier for this device')

    def _uuid_default(self):
        return str(uuid.uuid4())

    aliases = dict(zmq_port='Device.zmq_port',
                   zmq_url='Device.zmq_url')

    @property
    def zmq_connection_string(self):
        return 'tcp://%s:%s' % (self.zmq_url, self.zmq_port)

    def start(self):
        self.ctx = zmq.Context()
        self.socket = self.ctx.socket(zmq.REQ)
        # we're using the uuid to set the identity of the socket
        # AND we're going to put it explicitly inside of the header of
        # the messages we send. Within the actual bytes that go over the wire,
        # this means that the uuid will actually be printed twice, but
        # its not a big deal. It makes it easier for the server application
        # code to have the sender of each message, and for the message json
        # itself to be "complete", insted of having the sender in a separate
        # data structure.
        self.socket.setsockopt(zmq.IDENTITY, self.uuid)
        self.socket.connect(self.zmq_connection_string)

        # send the "here i am message" to the server, and receive a response
        # we're using a "robust" send/recv pattern, basically retrying the
        # request a fixed number of times if no response is heard from the
        # server
        msg = self.send_recv(msg_type='register_%s' % self.__class__.__name__)
        self.on_startup_message(msg)

    def on_startup_message(self, msg_type, msg):
        """This method is called when the device receives its startup message
        from the server
        """
        raise NotImplementedError('This method should be overriden in a device subclass')

    def send_message(self, msg_type, content=None):
        """Send a message to the server asynchronously.

        Since we're using the request/reply pattern, after calling send
        you need to call recv to get the server's response. Consider instead
        using the send_recv method instead

        See Also
        --------
        send_recv
        """
        if content is None:
            content = {}
        self.socket.send_json(pack_message(msg_type=msg_type, content=content,
                                           sender_id=self.uuid))

    def recv_message(self):
        """Receive a message from the server.

        Note, this methos is not async -- it blocks the device until
        the server delivers a message
        """
        raw_msg = self.socket.recv()
        msg = yaml.load(raw_msg)
        return Message(msg)


    def send_recv(self, msg_type, content=None, timeout=3, retries=3):
        """Send a message to the server and receive a response

        This method inplementes the "Lazy-Pirate pattern" for
        relaible request/reply flows described in the ZeroMQ book.

        Parameters
        ----------
        msg_type : str
            The type of the message to send. This is an essential
            part of the MSMAccelerator messaging protocol.
        content : dict
            The contents of the message to send. This is an essential
            part of the MSMAccelerator messaging protocol.
        timeout : int, float, default=3
            The timeout, in seconds, to wait for a response from the
            server.
        retries : int, default=3
            If a response from the server is not received within `timeout`
            seconds, we'll retry sending our payload at most `retries`
            number of times. After that point, if no return message has
            been received, we'll throw an IOError.
        """
        timeout_ms = timeout * 1000

        poller = zmq.Poller()
        for i in range(retries):
            self.send_message(msg_type, content)
            poller.register(self.socket, zmq.POLLIN)
            if poller.poll(timeout_ms):
                return self.recv_message()
            else:
                self.log.error('No response received from server on'
                               'msg_type=%s. Retrying...', msg_type)
                poller.unregister(self.socket)
                self.socket.close()
                self.socket = self.ctx.socket(zmq.REQ)
                self.socket.connect(self.zmq_connection_string)

        raise IOError('Network timeout. Server is unresponsive.')

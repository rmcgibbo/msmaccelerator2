"""
Base class for devices that connect to the msmaccelerator server that exposes
them as a configurable command-line app and provides the biolerplate for them
to get registered with the server and start their work.
"""

##############################################################################
# Imports
##############################################################################

import uuid
import zmq

from IPython.utils.traitlets import Int, Unicode

from .app import App
from ..core.message import message

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

    aliases = dict(zmq_port='Device.zmq_port',
                   zmq_url='Device.zmq_url')
    
    def start(self):
        ctx = zmq.Context()
        self.socket = ctx.socket(zmq.REQ)
        self.uuid = uuid.uuid4()
        self.socket.connect('tcp://%s:%s' % (self.zmq_url, self.zmq_port))
        
        # send the "here i am message"
        self.socket.send_json(message(msg_type='register_%s' % self.__class__.__name__,
                              sender_id=self.uuid,
                              content={}))

        msg = self.recv_message()
        self.on_startup_message(msg['header']['msg_type'], msg)
    
    def on_startup_message(self, msg_type, msg):
        """This method is called when the device receives its startup message
        from the server
        """
        raise NotImplementedError('This method should be overriden in a device subclass')
    
    def send_message(self, msg_type, content, parent_header=None):
        """Send a message to the server
        """
        self.socket.send_json(message(msg_type=msg_type, content=content,
            parent_header=parent_header, sender_id=self.uuid))
    
    def recv_message(self):
        """Receive a message from the server.

        Note, this methos is not async -- it blocks the device until
        the serve delivers a message
        """
        msg = self.socket.recv_json()
        return msg

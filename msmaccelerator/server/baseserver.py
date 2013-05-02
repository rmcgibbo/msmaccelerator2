"""Base class for ZMQ server app.
"""
##############################################################################
# Imports
##############################################################################

import os
import yaml
import zmq
import uuid
from zmq.eventloop import ioloop
ioloop.install()  # this needs to come at the beginning
from zmq.eventloop.zmqstream import ZMQStream
from IPython.utils.traitlets import Unicode, Int, Bool

# local
from ..core.database import connect_to_sqlite_db
from ..core.app import App
from ..core.message import Message, pack_message


##############################################################################
# Classes
##############################################################################


class BaseServer(App):
    """Base class for a ZMQ server object that manages a ROUTER socket.

    When a new message arrives on the socket, ZMQ cals the _dispatch()
    method. After validating the message, dispatch() looks for a
    method on the class whose name corresponds to the 'msg_type' (in
    the message's header). This method then gets called as method(**msg),
    with three arguments, header, parent_header and content.

    The method should respond on the stream by calling send_message()
    """

    zmq_port = Int(12345, config=True, help='ZeroMQ port to serve on')
    db_path = Unicode('db.sqlite', config=True, help='''
        Path to the database (sqlite3 file)''')


    def start(self):
        url = 'tcp://*:%s' % int(self.zmq_port)

        self.uuid = str(uuid.uuid4())
        self.ctx = zmq.Context()
        s = self.ctx.socket(zmq.ROUTER)
        s.bind(url)
        self._stream = ZMQStream(s)
        self._stream.on_recv(self._dispatch)
        connect_to_sqlite_db(self.db_path)

    def send_message(self, client_id, msg_type, content=None):
        """Send a message out to a client

        Parameters
        ----------
        client_id : uuid
            Who do you want to send the message to? This is string that
            identifies the client to the ZMQ routing layer. Within our
            messaging protocol, when the server recieves a message, it can
            get the id of the sender from within the message's header -- but
            this is dependent on the fact that the device.Device() code
            puts the same string in the message header that it uses
            to identify the socket to zeromq, in the line
                setsockopt(zmq.IDENTITY, str(self.uuid))
        msg_type : str
            The type of the message
        content : dict
            Content of the message
        Notes
        -----
        For details on the messaging protocol, refer to message.py
        """
        if content is None:
            content = {}

        msg = pack_message(msg_type, self.uuid, content)
        self.log.info('SENDING MESSAGE: %s', msg)

        self._stream.send(client_id, zmq.SNDMORE)
        self._stream.send('', zmq.SNDMORE)
        self._stream.send_json(msg)

    def _validate_msg_dict(self, msg_dict):
        if 'header' not in msg_dict:
            raise ValueError('msg does not contain "header"')
        if 'content' not in msg_dict:
            raise ValueError('msg does not contain "content"')
        if 'sender_id' not in msg_dict['header']:
            raise ValueError('msg header does not contain "sender_id"')
        if 'msg_type' not in msg_dict['header']:
            raise ValueError('msg header does not contain "msg_type"')


    def _dispatch(self, frames):
        """Callback that responds to new messages on the stream

        This is the first point where new messages enter the system. Basically
        we just pack them up and send them on to the correct responder.

        Parameters
        ----------
        stream : ZMQStream
            The stream that we're responding too (probably self._stream)
        messages : list
            A list of messages that have arrived
        """
        if not len(frames) == 3:
            self.log.error('invalid message received. messages are expected to contain only three frames: %s', str(frames))

        client, _, raw_msg = frames
        # using the PyYaml loader is a hack force regular strings
        # instead of unicode, since you can't send unicode over zmq
        # since json is a subset of yaml, this works
        msg_dict = yaml.load(raw_msg)

        try:
            self._validate_msg_dict(msg_dict)
        except ValueError:
            # if we recieve an invalid message, we log it out error stream
            # and then return from this function, so it won't take the server
            # down
            self.log.exception('Invalid message: %s', msg_dict)
            return

        msg = Message(msg_dict)
        self.log.info('RECEIVING MESSAGE: %s', msg)

        try:
            responder = getattr(self, msg.header.msg_type)
        except AttributeError:
            self.log.critical('RESPONDER NOT FOUND FOR MESSAGE: %s',
                              msg.header.msg_type)
            return

        responder(msg.header, msg.content)


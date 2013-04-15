"""Server process for msmaccelerator

This module contains "Dispatch" classes that manage a ZMQ REP socket,
basically responding to "simulators" and "clusterers" that come online
asking for work to do. This process sends them work and then receives their
replies.

"""
#############################################################################
# Imports
##############################################################################

import os
import glob
import warnings
import yaml
import zmq
import uuid
from zmq.eventloop import ioloop
ioloop.install()  # this needs to come at the beginning
from zmq.eventloop.zmqstream import ZMQStream
import numpy as np

# local
from ..core.app import App
from ..core.message import Message, pack_message

# ipython
from IPython.utils.traitlets import Unicode, Int, Bool


##############################################################################
# Classes
##############################################################################


class ServerBase(App):
    """Base class for a ZMQ "dispatch" object that manages a REP socket.

    When a new message arrives on the socket, ZMQ cals the dispatch()
    method. After validating the message, dispatch() looks for a
    method on the class whose name corresponds to the 'msg_type' (in
    the message's header). This method then gets called as method(**msg),
    with three arguments, header, parent_header and content.

    The method should respond on the stream by calling send_message()
    """

    zmq_port = Int(12345, config=True, help='ZeroMQ port to serve on')
    mongo_url = Unicode('', config=True, help='''
        The url for mongodb. This can be either passed in or, if not
        supplied, it will be read from the environment variable
        MONGO_URL. It should be a string like:
            mongodb://<user>:<pass>@hatch.mongohq.com:10034/msmaccelerator
        ''')
    use_db = Bool(True, config=True, help='''
        Do you want to connect to a database to log the messages?''')
    db_name = Unicode('', config=True, help='''
        The name of the database to log to. If not supplied, its infered
        by chopping off the last bit of the mongo_url string, after the
        last "/". In the example above, that would be 'msmaccelerator''')
    collection_suffix = Unicode('', config=True, help='''
        We're going to log messages into the database under the 'messages'
        collection, but if you want not to get messages from one run
        of msmaccelerator confused with another run, supply this
        'message_suffix' string, and then we'll use a collection
        like "messages-{}".format(messasges_suffix)''')

    def start(self):
        url = 'tcp://*:%s' % int(self.zmq_port)

        self.uuid = str(uuid.uuid4())
        self.ctx = zmq.Context()
        s = self.ctx.socket(zmq.ROUTER)
        s.bind(url)
        self._stream = ZMQStream(s)
        self._stream.on_recv(self._dispatch)

        self.db = None
        if self.use_db:
            self._start_database()

    def _start_database(self):
        """Sets the attribute self.db, self.c_msgs
        """

        try:
            from pymongo import Connection
        except ImportError:
            print '#'*80
            print 'You need to install PyMongo, the MongoDB client.'
            print 'You can get it from here: https://pypi.python.org/pypi/pymongo/'
            print 'Or install it directly with your python package manager using'
            print '$ easy_install pymongo'
            print 'or '
            print '$ pip install pymongo'
            print '#'*80
            raise

        if self.mongo_url == '':
            self.mongo_url = os.environ.get('MONGO_URL', '')

        if self.mongo_url == '':
            warnings.warn('Could not connect to database. You need to '
                'add an env variable MONGO_URL with the url for the mongo '
                'instance. If you\'re running you own mongo server, then '
                'this will be some kind of localhost url. Its recommended '
                'instead that you use a cloud Database-as-a-service like '
                'MongoHQ or MongoLab. They will give you a url to connect to'
                'your db. See http://blog.mongohq.com/blog/2012/02/20/connecting-to-mongohq/ '
                'for some details')
            self.db = None
            return

        c = Connection(self.mongo_url)
        if self.db_name == '':
            # this gets the name of the db from the mongo url
            # we should do more validation here
            self.db_name = self.mongo_url.split('/')[-1]
            print 'PARSED DB NAME:', self.db_name

        self.db = getattr(c, self.db_name)  # database name
        self.c_msgs = getattr(self.db, 'messages' + self.collection_suffix)


    def send_message(self, client_id, msg_type, content):
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
        msg = pack_message(msg_type, self.uuid, content)
        print 'SENDING', msg
        if self.db is not None:
            db_entry = msg.copy()
            db_entry['client_id'] = client_id
            self.c_msgs.save(db_entry)

        self._stream.send(client_id, zmq.SNDMORE)
        self._stream.send_json(msg)

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
        client, raw_msg = frames
        # using the PyYaml loader is a hack force regular strings
        # instead of unicode, since you can't send unicode over zmq
        # since json is a subset of yaml, this works
        msg = Message(yaml.load(raw_msg))
        print 'RECEIVING', msg

        if self.db is not None:
            self.c_msgs.save(msg.copy())

        responder = getattr(self, msg.header.msg_type)
        responder(msg.header, msg.content)


class ToyMaster(ServerBase):

    name = 'serve'
    path = 'msmaccelerator.server.server.ToyMaster'
    short_description = 'Start up the MSMAccelerator work server'
    long_description = """This lightweight server manages the adaptive sampling
    workflow. Simulator and modeler processes connect to it, and receive either
    initial conditions to propagate (the simulators) or data with which to build
    an MSM.
    """
    # how long do we want trajectories to be?
    steps = Int(100, config=True, help='How many steps of MD to run on each simulator')

    # size of the grid we're simulating dynamics on
    box_size = Int(10, config=True, help='Size of the box to run MD on')


    aliases = dict(steps='ToyMaster.steps',
                   use_db='ToyMaster.use_db',
                   zmq_port='ServerBase.zmq_port',
                   collection_suffix='ServerBase.collection_suffix',
                   mongo_url='ServerBase.mongo_url')

    def start(self):
        super(ToyMaster, self).start()

        self.structures = None
        self.weights = None
        self.initialize_structures()

        self.round = 0
        self.traj_outdir = os.path.join(os.path.abspath(os.curdir), 'trajs')
        self.models_outdir = os.path.join(os.path.abspath(os.curdir), 'models')

        # create paths if need be
        for path in [self.traj_outdir, self.models_outdir]:
            if not os.path.exists(path):
                os.makedirs(path)

        ioloop.IOLoop.instance().start()

    def initialize_structures(self):
        """Create some random initial structures"""
        n_init_structures = 10

        # choose random coordinates from inside the box
        self.structures = 1.0*np.random.randint(self.box_size,
                                                size=(n_init_structures, 2))
        # uniform weights
        self.weights = np.ones(n_init_structures) / n_init_structures

    def select_structure(self):
        """Select a random structure

        The selection is done from self.structures() via the multinomial
        distibution in self.weights
        """
        l = np.where(np.random.multinomial(1, self.weights) == 1)[0][0]
        return [float(e) for e in self.structures[l]]

    ########################################################################
    # BEGIN HANDLERS FOR INCOMMING MESSAGES
    ########################################################################

    def register_Simulator(self, header, content):
        """Called at the when a Simulator device boots up. We give it
        starting conditions
        """
        self.send_message(header.sender_id, 'simulate', content={
            'starting_structure': self.select_structure(),
            'steps': self.steps,
            'box_size': self.box_size,
            'outdir': self.traj_outdir,
            'round': self.round,
        })

    def register_Modeler(self, header, content):
        """Called when a Modeler device boots up, asking for a path to data.
        """
        self.send_message(header.sender_id, 'cluster', content={
            'traj_fns': glob.glob(os.path.join(self.traj_outdir, '*.npy')),
            'outdir': self.models_outdir,
        })

    def similation_status(self, header, content):
        """Called at the end of a simulation job, saying that its finished
        """
        pass

    def cluster_status(self, header, content):
        """Called when a clustering job finishes, """
        if content.status == 'done':
            model = np.load(content.model_fn)
            self.round += 1
            self.structures = model['centers']
            self.weights = model['populations']

    ########################################################################
    # END HANDLERS FOR INCOMMING MESSAGES
    ########################################################################

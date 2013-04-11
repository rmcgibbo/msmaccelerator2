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
import json
import zmq
from zmq.eventloop import ioloop
from zmq.eventloop.zmqstream import ZMQStream
import numpy as np

# local
from ..core.message import message


##############################################################################
# Classes
##############################################################################


class DispatchBase(object):
    """Base class for a ZMQ "dispatch" object that manages a REP socket.

    When a new message arrives on the socket, ZMQ cals the dispatch()
    method. After validating the message, dispatch() looks for a
    method on the class whose name corresponds to the 'msg_type' (in
    the message's header). This method then gets called as method(**msg),
    with three arguments, header, parent_header and content.

    The method should respond on the stream by calling send_message()
    """
    ctx = zmq.Context()

    def __init__(self, ctx, url, use_db=True, mongo_url=None, db_name=None):
        """Initiaize the base class.

        This sets up the sockets and stuff

        Parameters
        ----------
        ctx : zmq.Context
            The zeromq context.
        url : string
            The zmq url that we should listen on. This should be fully
            qualified, like tcp://127.0.0.1:12345 or something
        use_db : bool
            Do you want to connect to a database to log the messages?
        mongo_url : string
            The url for the mongodb. This can be either passed in or
            read from the environment variable MONGO_URL. It should be a
            string like:
                mongodb://<user>:<pass>@hatch.mongohq.com:10034/msmaccelerator
        db_name : string
            The name of the database (or maybe collection?). If not supplied,
            its infered by chopping off the last bit of the mongo_url string,
            after the last "/".
        """
        s = ctx.socket(zmq.REP)
        s.bind(url)
        self._stream = ZMQStream(s)
        self._stream.on_recv_stream(self._dispatch)

        self.db = None
        if use_db:
            self._initialize_database(mongo_url, db_name)

    def _initialize_database(self, mongo_url=None, db_name=None):
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

        if mongo_url is None:
            mongo_url = os.getenv('MONGO_URL')

        if mongo_url is None:
            raise ValueError('Could not connect to database. You need to '
                'add an env variable MONGO_URL with the url for the mongo '
                'instance. If you\'re running you own mongo server, then '
                'this will be some kind of localhost url. Its recommended '
                'instead that you use a cloud Database-as-a-service like '
                'MongoHQ or MongoLab. They will give you a url to connect to'
                'your db. See http://blog.mongohq.com/blog/2012/02/20/connecting-to-mongohq/ '
                'for some details')

        c = Connection(mongo_url)
        if db_name is None:
            # this gets the name of the db from the mongo url
            # we should do more validation here
            db_name = mongo_url.split('/')[-1]
            print 'PARSED DB NAME:', db_name
        # database name
        self.db = getattr(c, db_name)


    def send_message(self, msg_type, content, parent_header=None):
        """Send a message out on the stream

        Parameters
        ----------
        msg_type : str
            The type of the message
        content : dict
            Content of the message
        parent_header : dict, optional
            In a chain of messages, the header from the parent is copied so
            that clients can track where messages come from.

        Notes
        -----
        For details on the messaging protocol, refer to message.py
        """
        msg = message(msg_type, content, parent_header=parent_header)
        print 'SENDING', msg
        if self.db is not None:
            self.db.messages.save(msg.copy())
        self._stream.send_json(msg)

    def _dispatch(self, stream, messages):
        """Callback that responds to new messages on the stream

        This is the first point where new messages enter the system. Here,
        we validate the messages and dispatch to correct handler based on the
        'msg_type'

        Parameters
        ----------
        stream : ZMQStream
            The stream that we're responding too (probably self._stream)
        messages : list
            A list of messages that have arrived
        """
        for raw_msg in messages:
            msg = json.loads(raw_msg)
            print 'RECEIVING', msg
            if self.db is not None:
                self.db.messages.save(msg.copy())
            self._validate_msg(msg)
            # _validate_msg checks to ensure this lookup succeeds
            responder = getattr(self, msg['header']['msg_type'])

            responder(**msg)

    def _validate_msg(self, msg):
        """Validate an incomming message

        Parameters
        ----------
        msg : dict
            The message dict
        """
        correct_keys = ['content', 'header', 'parent_header']
        if not (sorted(msg.keys()) == correct_keys):
            err = 'Keys ({}) in message are not correct. They should be {}'
            raise ValueError(err.format(msg.keys(), correct_keys))

        if not 'msg_type' in msg['header']:
            err = 'header must contain "msg_type". you gave {}'
            raise ValueError(err.format(msg))

        if not hasattr(self, msg['header']['msg_type']):
            err = 'I dont have a method to respond to msg_type={}'
            raise ValueError(err.format(msg['header']['msg_type']))


class ToyMaster(DispatchBase):

    # how long do we want trajectories to be?
    steps = 100

    # size of the grid we're simulating dynamics on
    box_size = 10

    def __init__(self, **kwargs):
        super(ToyMaster, self).__init__(**kwargs)

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
        return [float(e) for e in self.structures[np.random.randint(l)]]

    ########################################################################
    # BEGIN HANDLERS FOR INCOMMING MESSAGES
    ########################################################################

    def register_simulator(self, header, parent_header, content):
        """Called at the begining of a simulation job, requesting data
        """
        self.send_message('simulate', content={
            'starting_structure': self.select_structure(),
            'steps': self.steps,
            'box_size': self.box_size,
            'outdir': self.traj_outdir,
            'round': self.round,
        }, parent_header=header)

    def similation_status(self, header, parent_header, content):
        """Called at the end of a simulation job, saying that its finished
        """
        self.send_message('acknowledge_receipt', content={},
                          parent_header=header)

    def register_clusterer(self, header, parent_header, content):
        """Called when a clustering job starts up, asking for the path to
        data
        """
        self.send_message('cluster', content={
            'traj_fns': glob.glob(os.path.join(self.traj_outdir, '*.npy')),
            'outdir': self.models_outdir,
        }, parent_header=header)

    def cluster_status(self, header, parent_header, content):
        """Called when a clustering job finishes, """
        if content['status'] == 'done':
            model = np.load(content['model_fn'])
            self.round += 1
            self.structures = model['centers']
            self.weights = model['populations']

        self.send_message('acknowledge_receipt', content={},
                          parent_header=header)

    ########################################################################
    # END HANDLERS FOR INCOMMING MESSAGES
    ########################################################################


def main(port):
    # install the tornado event loop. this needs to be done first
    ioloop.install()
    ctx = zmq.Context()
    dispatch = ToyMaster(ctx=ctx, url='tcp://*:%s' % int(port))
    ioloop.IOLoop.instance().start()

if __name__ == '__main__':
    main()

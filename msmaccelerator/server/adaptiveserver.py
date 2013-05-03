"""Adaptive sampling server process for msmaccelerator
"""
##############################################################################
# Imports
##############################################################################
import os
from datetime import datetime
from zmq.eventloop import ioloop
ioloop.install()  # this needs to come at the beginning

# local
from .sampling import CountsSampler
from .openmm import OpenMMStateBuilder
from .baseserver import BaseServer
from ..core.database import session, Model, Trajectory

# ipython
from IPython.utils.traitlets import Unicode, Instance
##############################################################################
# Classes
##############################################################################

class AdaptiveServer(BaseServer):

    name = 'serve'
    path = 'msmaccelerator.server.adaptiveserver.AdaptiveServer'
    short_description = 'Start up the MSMAccelerator work server'
    long_description = """This lightweight server manages the adaptive sampling
    workflow. Simulator and modeler processes connect to it, and receive either
    initial conditions to propagate (the simulators) or data with which to build
    an MSM.
    """

    # configurables
    system_xml = Unicode('system.xml', config=True, help='''Path to the
        XML file containing the OpenMM system to propagate. This is required
        by the server to properly serialize the starting conformations.''')
    traj_outdir = Unicode('trajs/', config=True, help='''Directory on the local
        filesystem where output trajectories will be saved''')
    models_outdir = Unicode('models/', config=True, help='''Directory on
        the local filesystem where MSMs will be saved.''')
    starting_states_outdir = Unicode('starting_states', config=True,
        help=''''Directory on the local filesystem where starting structures
        will be stored''')
    topology_pdb = Unicode('ala5.pdb', config=True, help='''A PDB used to
        determine the system's topology. This is sent directly to the
        Simulator. Honestly, I'm not sure exactly why we need it. TODO:
        ask Peter about this.''')

    sampler = Instance('msmaccelerator.server.sampling.CentroidSampler')
    # this class attributes lets us configure the sampler on the command
    # line from this app. very convenient.
    classes = [CountsSampler]

    aliases = dict(use_db='AdaptiveServer.use_db',
                   zmq_port='BaseServer.zmq_port',
                   collection_suffix='BaseServer.collection_suffix',
                   system_xml='AdaptiveServer.system_xml',
                   seed_structures='BaseSampler.seed_structures',
                   beta='CountsSampler.beta')

    def start(self):
        # run the startup in the base class
        super(AdaptiveServer, self).start()
        # start our adaptive sampler
        self.initialize_sampler()

        # create paths on the local filesystem if need be
        for path in [self.traj_outdir, self.models_outdir, self.starting_states_outdir]:
            if not os.path.exists(path):
                os.makedirs(path)

        # start the ioloop so that we can respond to ZMQ stuff
        self.log.info('IOLoop starting')
        ioloop.IOLoop.instance().start()

    def initialize_sampler(self):
        """Initialize the adaptive sampling machinery.

        This entails
          - instantiating the classes
          - looking on the filesystem for the most recent MSM, and give that
            to the sampler if one is found.

        """
        self.sampler = CountsSampler(config=self.config)
        self.sampler.log = self.log
        self.sampler.statebuilder = OpenMMStateBuilder(self.system_xml)
        self.log.info('Sampler loaded')

        last_model = session.query(Model).order_by(Model.time.desc()).get(1)
        if last_model is not None:
            self.sampler.model_fn = last_model.path
            self.log.info(('Loading most recent model on disk, "%s". According '
                'to the database'), last_model)
            self.log.info('Ignoring seed structures, since we found a model.')

        else:
            self.log.info('Using seed structures. No existing model found on disk.')



    ########################################################################
    # BEGIN HANDLERS FOR INCOMMING MESSAGES
    ########################################################################

    def register_Simulator(self, header, content):
        """Called at the when a Simulator device boots up. We give it
        starting conditions
        """

        starting_state_fn = os.path.join(self.starting_states_outdir,
                                         '%s.xml' % header.sender_id)
        with open(starting_state_fn, 'w') as f:
            state = self.sampler.sample_xml_state()
            f.write(state)

        self.send_message(header.sender_id, 'simulate', content={
            'starting_state': {
                'protocol': 'localfs',
                'path': os.path.abspath(starting_state_fn)
            },
            'topology_pdb': {
                'protocol': 'localfs',
                'path': self.topology_pdb,
            },
            'output': {
                'protocol': 'localfs',
                'path': os.path.join(os.path.abspath(self.traj_outdir), header.sender_id + '.h5'),
            },
        })

    def register_Modeler(self, header, content):
        """Called when a Modeler device boots up, asking for a path to data.
        """

        # get the filename of all of the trajectories from the database
        traj_fns = [str(e[0]) for e in session.query(Trajectory.path).all()]
        assert isinstance(traj_fns, list)
        assert len(traj_fns) == 0 or isinstance(traj_fns[0], str)

        self.send_message(header.sender_id, 'construct_model', content={
            'traj_fns': traj_fns,
            'output': {
                'protocol': 'localfs',
                'path': os.path.join(os.path.abspath(self.models_outdir), header.sender_id + '.h5'),
            }
        })

    def modeler_done(self, header, content):
        """Called when a Modeler finishes, returning the path to the model
        build.
        """
        assert content.output.protocol == 'localfs'
        # register the newest model with the sampler!
        self.sampler.model_fn = content.output.path
        self.send_message(header.sender_id, 'acknowledge_receipt')

        # save every model in the database
        session.add(Model(
            time = datetime.fromtimestamp(header.time),
            protocol = content['output']['protocol'],
            path = content['output']['path']
        ))
        session.commit()

    def simulation_status(self, header, content):
        """Called when the simulation reports its status.
        """
        self.send_message(header.sender_id, 'acknowledge_receipt')

    def simulation_done(self, header, content):
        """Called when a simulation finishes"""
        self.send_message(header.sender_id, 'acknowledge_receipt')

        session.add(Trajectory(
            time = datetime.fromtimestamp(header.time),
            protocol = content['output']['protocol'],
            path = content['output']['path']
        ))
        session.commit()


    # permit external interaction with the sampler, to change its
    # beta
    def register_Interactor(self, header, content):
        self.send_message(header.sender_id, 'acknowledge_receipt')

    def set_beta(self, header, content):
        """The interactor can tell us to change our sampler's beta
        parameteter"""

        try:
            new_beta = content.value
            self.sampler.beta = new_beta
            self.send_message(header.sender_id, 'set_beta', content={
                'status': 'success'
            })
        except Exception as e:
            self.send_message(header.sender_id, 'set_beta', content={
                'status': 'failure',
                'msg': str(e)
            })

    def get_beta(self, header, content):
        """Query the beta parameter in the sampler
        """

        try:
            self.send_message(header.sender_id, 'response', content={
                'beta': self.sampler.beta,
                'status': 'sucess'
            })
        except AttributeError as e:
            self.send_message(header.sender_id, 'response', content={
                'status': 'failure',
                'msg': str(e)
            })



    ########################################################################
    # END HANDLERS FOR INCOMMING MESSAGES
    ########################################################################

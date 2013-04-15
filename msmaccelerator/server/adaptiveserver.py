"""Adaptive sampling server process for msmaccelerator
"""
##############################################################################
# Imports
##############################################################################

import os
import glob
from zmq.eventloop import ioloop
ioloop.install()  # this needs to come at the beginning

# local
from .openmm import OpenMMStateBuilder
from .baseserver import BaseServer

from simtk.openmm.app import PDBFile

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

    system_xml = Unicode('system.xml', config=True, help='''
        Path to the XML file containing the OpenMM system to propagate''')
    system = Instance('simtk.openmm.openmm.System')

    traj_outdir = Unicode('trajs/', help='Path where output trajectories will be stored')
    models_outdir = Unicode('models/', help='Path where MSMs will be saved')
    starting_states_outdir = Unicode('starting_states', help='Path where starting structures will be stored')

    statebuilder = Instance('msmaccelerator.server.openmm.OpenMMStateBuilder')
    initial_pdb = Unicode('ala5.pdb', help='Initial structure. we need to generalize this...')

    aliases = dict(use_db='AdaptiveServer.use_db',
                   zmq_port='BaseServer.zmq_port',
                   collection_suffix='BaseServer.collection_suffix',
                   mongo_url='BaseServer.mongo_url')

    def start(self):
        super(AdaptiveServer, self).start()

        # instantiate the machinery for building serialized openmm states
        self.statebuilder = OpenMMStateBuilder(self.system_xml)
        self.initial_structure = PDBFile(self.initial_pdb)

        # create paths if need be
        for path in [self.traj_outdir, self.models_outdir, self.starting_states_outdir]:
            if not os.path.exists(path):
                os.makedirs(path)

        ioloop.IOLoop.instance().start()

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
            state = self.statebuilder.build(self.initial_structure.getPositions(asNumpy=True))
            f.write(state)

        self.send_message(header.sender_id, 'simulate', content={
            'starting_state': {
                'protocol': 'localfs',
                'path': os.path.abspath(starting_state_fn)
            },
            'topology_pdb': {
                'protocol': 'localfs',
                'path': self.initial_pdb,
            },
            'outdir': os.path.abspath(self.traj_outdir),
        })

    def register_Modeler(self, header, content):
        """Called when a Modeler device boots up, asking for a path to data.
        """
        self.send_message(header.sender_id, 'cluster', content={
            'traj_fns': glob.glob(os.path.join(self.traj_outdir, '*.npy')),
            'outdir': os.path.abspath(self.models_outdir),
        })

    def simulation_status(self, header, content):
        """Called when the simulation reports its status.
        """
        pass

    def simulation_done(self, header, content):
        """Called when a simulation finishes"""
        pass

    def cluster_done(self, header, content):
        """Called when a clustering job finishes, """
        # TODO: add data to adaptive sampling data structure
        pass

    ########################################################################
    # END HANDLERS FOR INCOMMING MESSAGES
    ########################################################################

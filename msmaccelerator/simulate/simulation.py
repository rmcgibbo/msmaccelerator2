"""OpenMM simulation device. We connect to server, request a starting
structure, and then propagate.
"""
#############################################################################
# Imports
##############################################################################

import numpy as np
from IPython.utils.traitlets import Unicode, CInt, Instance, Bool, Enum
from mdtraj.reporters import HDF5Reporter
from simtk.openmm import XmlSerializer, Platform
from simtk.openmm.app import (Simulation, PDBFile)

# local
from .reporters import CallbackReporter
from ..core.device import Device

#############################################################################
# Handlers
##############################################################################


class Simulator(Device):
    name = 'simulate'
    path = 'msmaccelerator.simulate.simulation.Simulator'
    short_description = 'Run a single round of dynamics'
    long_description = '''This device will connect to the msmaccelerator server,
        request the initial conditions with which to start a simulation, and
        propagate dynamics'''

    # configurables.
    system_xml = Unicode('system.xml', config=True, help='''
        Path to the XML file containing the OpenMM system to propagate''')
    system = Instance('simtk.openmm.openmm.System')

    integrator_xml = Unicode('integrator.xml', config=True, help='''
        Path to the XML file containing the OpenMM Integrator to use''')
    integrator = Instance('simtk.openmm.openmm.Integrator')

    number_of_steps = CInt(10000, config=True, help='''
        Number of steps of dynamics to do''')

    report_interval = CInt(1000, config=True, help='''
        Interval at which to save positions to a disk, in units of steps''')

    minimize = Bool(True, config=True, help='''Do local energy minimization on
        the configuration that's passed to me, before running dynamics''')

    random_initial_velocities = Bool(True, config=True, help='''Choose
        random initial velocities from the Maxwell-Boltzmann distribution''')

    platform = Enum(['Reference', 'CUDA', 'OpenCL'], default_value='CUDA',
        config=True, help='''The OpenMM platform on which to run the simulation''')
    device_index = CInt(0, config=True, help='''OpenMM device index for CUDA or
        OpenCL platforms. This is used to select which GPU will be used on a
        multi-gpu system. This option is ignored on reference platform''')


    # expose these as command line flags on --help
    # other settings can still be specified on the command line, its just
    # less convenient
    aliases = dict(system_xml='Simulator.system_xml',
                  integrator_xml='Simulator.integrator_xml',
                  number_of_steps='Simulator.number_of_steps',
                  report_interval='Simulator.report_interval',
                  zmq_port='Device.zmq_port',
                  zmq_url='Device.zmq_url',
                  platform='Simulator.platform',
                  device_index='Simulator.device_index')


    def start(self):
        # load up the system and integrator files
        with open(self.system_xml) as f:
            self.system = XmlSerializer.deserialize(f.read())
        with open(self.integrator_xml) as f:
            self.integrator = XmlSerializer.deserialize(f.read())

        super(Simulator, self).start()

    def on_startup_message(self, msg):
        """This method is called when the device receives its startup message
        from the server.
        """

        assert msg.header.msg_type in ['simulate']  # only allowed RPC
        return getattr(self, msg.header.msg_type)(msg.header, msg.content)

    def simulate(self, header, content):
        """Main method that is "executed" by the receipt of the
        msg_type == 'simulate' message from the server.

        We run some OpenMM dynamics, and then send back the results.
        """
        self.log.info('Setting up simulation...')
        state, topology = self.deserialize_input(content)

        # set the GPU platform
        platform = Platform.getPlatformByName(str(self.platform))
        if self.platform == 'CUDA':
            properties = {'CudaPrecision': 'mixed',
                          'CudaDeviceIndex': str(self.device_index)
                         }
        elif self.platform == 'OpenCL':
            properties = {'OpenCLPrecision': 'mixed',
                          'OpenCLDeviceIndex': str(self.device_index)
                         }
        else:
            properties = None


        simulation = Simulation(topology, self.system, self.integrator,
                                platform, properties)
        # do the setup
        self.set_state(state, simulation)
        self.sanity_check(simulation)
        if self.minimize:
            self.log.info('minimizing...')
            simulation.minimizeEnergy()

        if self.random_initial_velocities:
            try:
                temp = simulation.integrator.getTemperature()
                simulation.context.setVelocitiesToTemperature(temp)
            except AttributeError:
                print "I don't know what temperature to use!!"
                # TODO: look through the system's forces to find an andersen
                # thermostate?
                raise
            pass

        assert content.output.protocol == 'localfs', "I'm currently only equiped for localfs output"
        self.log.info('adding reporters...')
        self.add_reporters(simulation, content.output.path)

        # run dynamics!
        self.log.info('Starting dynamics')
        simulation.step(self.number_of_steps)

        for reporter in simulation.reporters:
            # explicitly delete the reporters so that any open file handles
            # are closed.
            del reporter

        # tell the master that I'm done
        self.send_recv(msg_type='simulation_done', content={
            'status': 'success',
            'output': {
                'protocol': 'localfs',
                'path': content.output.path
            }
        })

    ##########################################################################
    # Begin helpers for setting up the simulation
    ##########################################################################

    def sanity_check(self, simulation):
        positions = simulation.context.getState(getPositions=True).getPositions(asNumpy=True)
        for atom1, atom2 in simulation.topology.bonds():
            d = np.linalg.norm(positions[atom1.index, :] - positions[atom2.index, :])
            if not d < 0.3:
                self.log.error(positions[atom1.index, :])
                self.log.error(positions[atom2.index, :])
                raise ValueError('atoms are bonded according to topology but not close by '
                                 'in space: %s. %s' % (d, positions))


    def deserialize_input(self, content):
        """Retreive the state and topology from the message content

        The message protocol tries not to pass 'data' around within the
        messages, but instead pass paths to data. So far we're only sending
        paths on the local filesystem, but we might could generalize this to
        HTTP or S3 or something later.

        The assumption that data can be passed around on the local filesystem
        shouldn't be built deep into the code at all
        """
        # todo: better name for this function?

        if content.starting_state.protocol == 'localfs':
            with open(content.starting_state.path) as f:
                self.log.info('Opening state file: %s', content.starting_state.path)
                state = XmlSerializer.deserialize(f.read())
        else:
            raise ValueError('Unknown protocol')

        if content.topology_pdb.protocol == 'localfs':
            topology = PDBFile(content.topology_pdb.path).topology
        else:
            raise ValueError('Unknown protocol')

        return state, topology

    def set_state(self, state, simulation):
        "Set the state of a simulation to whatever is in the state object"
        # why do I have to do this so... manually?
        # this is why:

        # simulation.context.setState(state)
        # TypeError: in method 'Context_setState', argument 2 of type 'State const &'

        simulation.context.setPositions(state.getPositions())
        simulation.context.setVelocities(state.getVelocities())
        simulation.context.setPeriodicBoxVectors(*state.getPeriodicBoxVectors())
        for key, value in state.getParameters():
            simulation.context.setParameter(key, value)

    def add_reporters(self, simulation, outfn):
        "Add reporters to a simulation"
        def reporter_callback(report):
            """Callback for processing reporter output"""
            self.log.info(report)

        callback_reporter = CallbackReporter(reporter_callback,
            self.report_interval, step=True, potentialEnergy=True,
            temperature=True, time=True, total_steps=self.number_of_steps)
        h5_reporter = HDF5Reporter(outfn, self.report_interval)

        simulation.reporters.append(callback_reporter)
        simulation.reporters.append(h5_reporter)

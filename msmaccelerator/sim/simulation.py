"""
Simple simulation process. Two dimensional dynamics on a lattice.

"""
#############################################################################
# Imports
##############################################################################

import os
from IPython.utils.traitlets import Unicode, Int, Instance, Bool

from simtk.openmm import XmlSerializer
from simtk.openmm.app import (Simulation, DCDReporter, PDBFile)

# local
from .reporters import CallbackReporter
from ..core.device import Device

#############################################################################
# Handlers
##############################################################################


class Simulator(Device):
    name = 'simulate'
    path = 'msmaccelerator.sim.simulation.Simulator'
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

    number_of_steps = Int(10000, config=True, help='''
        Number of steps of dynamics to do''')

    report_internval = Int(1000, config=True, help='''
        Interval at which to report positions to a file, in units of steps''')

    minimize = Bool(True, config=True, help='''Do local energy minimization on
        the configuration that's passed to me, before running dynamics''')

    random_initial_velocities = Bool(True, config=True, help='''Choose
        random initial velocities from the Maxwell-Boltzmann distribution''')

    # expose these as command line flags on --help
    # other settings can still be specified on the command line, its just
    # less convenient
    aliases = dict(system_xml='Simulator.system_xml',
                  integrator_xml='Simulator.integrator_xml',
                  number_of_steps='Simulator.number_of_steps',
                  report_internval='Simulator.report_internval',
                  zmq_port='Device.zmq_port',
                  zml_url='Device.zmq_url')


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
        state, topology = self.deserialize_input(content)

        # path to store the dcd file that we create
        outfn = os.path.join(content.outdir, '%s.dcd' % self.uuid)

        simulation = Simulation(topology, self.system, self.integrator)
        # do the setup
        self.set_state(state, simulation)
        if self.minimize:
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

        self.add_reporters(simulation, outfn)

        # run dynamics!
        simulation.step(self.number_of_steps)

        # tell the master that I'm done
        self.send_message(msg_type='simulation_done', content={
            'traj_fn': {
                'protocol': 'localfn',
                'path': outfn
            }
        })

    ##########################################################################
    # Begin helpers for setting up the simulation
    ##########################################################################

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
        def zmq_reporter_callback(report):
            """Callback for CallbackReporter to publish the report back
            to the server"""
            self.send_message(msg_type='simulation_status', content={
                'status': 'inprogress',
                'report': report
            })
            print report

        simulation.reporters.append(CallbackReporter(zmq_reporter_callback,
            self.report_internval, step=True, potentialEnergy=True, temperature=True))
        simulation.reporters.append(DCDReporter(outfn, self.report_internval))

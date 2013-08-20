"""AMBER simulation device. We connect to server, request a starting
structure, and then propagate.
"""
#############################################################################
# Imports
##############################################################################

import os
import shutil
import subprocess
from os.path import join, basename, relpath, splitext, isfile, abspath, exists

from ..core.traitlets import FilePath
from IPython.utils.traitlets import Unicode, Enum, CBytes


# local
from ..core.utils import cd_context
from ..core.device import Device

#############################################################################
# Classes
##############################################################################

class AmberSimulator(Device):
    name = 'AMBER'
    path = 'msmaccelerator.simulate.amber_simulation.AmberSimulator'
    short_description = 'Run a single round of dynamics with AMBER'
    long_description = '''This device will connect to the msmaccelerator server,
        request the initial conditions with which to start a simulation, and
        propagate dynamics'''
    
    mdin = FilePath(config=True, exists=True, isfile=True,
        help="""AMBER .in file controlling the production run. If no production is
        desired, do not set this parameter.""")
    workdir = CBytes(config=True, help="""Directory to work in. If not set,
        we'll requirest a temporary directory from the OS and clean it up
        when we're finished. This option is useful for debugging.""")
    executable = Enum(['pmemd', 'pmemd.cuda', 'pmemd.cuda.MPI'], config=True,
        default_value='pmemd', help="Which AMBER executable to use?")
    precommand = Unicode(u'', config=True, help="Something to run before the command, like mpirun")
    prmtop = FilePath(config=True, exists=True, isfile=True,
                      help="""Parameter/topology file for the system""")

    amber_home = FilePath(exists=True, isdir=True, help='Home directory for AMBER installation')
    def _amber_home_default(self):
        if 'AMBERHOME' not in os.environ:
            raise KeyError("You need to set the AMBERHOME environment variable")
        return os.environ['AMBERHOME']

    aliases = dict(mdin='AmberSimulator.mdin',
                   precommand='AmberSimulator.precommand',
                   prmtop='AmberSimulator.prmtop',
                   zmq_port='Device.zmq_port',
                   zmq_url='Device.zmq_url')

    def start(self):
        super(AmberSimulator, self).start()


    def error(self, msg):
        self.log.error(msg)
        self.exit(1)
        
    def on_startup_message(self, msg):
        """This method is called when the device receives its startup message
        from the server.
        """

        assert msg.header.msg_type in ['simulate']  # only allowed RPC
        return getattr(self, msg.header.msg_type)(msg.header, msg.content)

    def simulate(self, header, content):
        """Run the simulation in subprocesses to invoke the AMBER binaries"""

        if content.starting_state.protocol == 'localfs':
            if not content.starting_state.path.endswith('.inpcrd'):
                raise ValueError('starting state must have inpcrd extension. '
                                 'did you start server in amber mode? '
                                 'starting_state.path=%s' % content.starting_state.path)
        else:
            raise NotImplementedError('Only localfs transport is currently '
                                      'supported.')

        template = '{precommand} {binary} -O -i {mdin} -o {mdout} -p {prmtop} -c {inpcrd} -r {restart} -x {traj}'

        # RUNNING PRODUCTION
        with cd_context('amber_workdir', logger=self.log):
            base = splitext(basename(self.mdin))[0]
            binary = join(self.amber_home, 'bin', self.executable)
            mdout = base + '.out'
            restart = base + '.restart'
            traj = base + '.nc'
            cmd = template.format(binary=binary, mdin=relpath(self.mdin),
                                  mdout=mdout, prmtop=relpath(self.prmtop),
                                  inpcrd=relpath(content.starting_state.path),
                                  restart=restart, precommand=self.precommand,
                                  traj=relpath(content.output.path)).split()
            self.log.info('Executing Command: %s' % cmd)
            subprocess.check_output(cmd)
        

        self.send_recv(msg_type='simulation_done', content={
            'status': 'success',
            'output': {
                'protocol': 'localfs',
                'path': content.output.path
            }
        })


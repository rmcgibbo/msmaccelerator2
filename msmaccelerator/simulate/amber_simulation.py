"""AMBER simulation device. We connect to server, request a starting
structure, and then propagate.
"""
#############################################################################
# Imports
##############################################################################

import os
import subprocess
from IPython.utils.traitlets import Unicode, List

# local
from ..core.device import Device

#############################################################################
# Classes
##############################################################################

class AmberSimulator(Device):
    name = 'amber_simulate'
    path = 'msmaccelerator.simulate.amber_simulation.AmberSimulator'
    short_description = 'Run a single round of dynamics with AMBER'
    long_description = '''This device will connect to the msmaccelerator server,
        request the initial conditions with which to start a simulation, and
        propagate dynamics'''
    
    mdin_minimization = Unicode('', config=True,
        help="""AMBER .in file giving the input parameters for a minimization run.
        If no minimization is desired, do not set this parameter.""")
    mdin_production = Unicode('', config=True,
        help="""AMBER .in file controlling the production run. If no production is
        desired, do not set this parameter.""")

    aliases = dict(mdin_minimization='AmberSimulator.mdin_minimization',
                   mdin_production='AmberSimulator.mdin_production',
                   zmq_port='Device.zmq_port',
                   zmq_url='Device.zmq_url')

    def start(self):
        if self.mdin_minimization is not u'':
            if not os.path.isfile(self.mdin_minimization):
                raise ValueError('%s does not exist' % self.mdin_minimization)
        if self.mdin_production is not u'':
            if not os.path.isfile(self.mdin_production):
                raise ValueError('%s does not exist' % self.mdin_production)
        if self.mdin_production is u'' and self.mdin_minimization is u'':
            raise ValueError("One of mdin_minimization and mdin_production "
                             "must be specified.")

        super(AmberSimulator, self).start()
        
    def on_startup_message(self, msg):
        """This method is called when the device receives its startup message
        from the server.
        """

        assert msg.header.msg_type in ['simulate']  # only allowed RPC
        return getattr(self, msg.header.msg_type)(msg.header, msg.content)

    def simulate(self, header, content):
        

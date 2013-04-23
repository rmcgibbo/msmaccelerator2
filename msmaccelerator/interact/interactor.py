##############################################################################
# Imports
##############################################################################

import IPython
import numpy as np
from pymongo import Connection
from IPython.utils.traitlets import Unicode, Instance, Bool

# local
from ..core.device import Device

##############################################################################
# Classes
##############################################################################

class Interactor(Device):
    name = 'interact'
    path = 'msmaccelerator.interact.interactor.Interactor'
    short_description = 'Modify the parameters inside of a live server'
    long_description = ''
    db = Instance('pymongo.database.Database')
    
    set_beta = Instance(int, config=True, help='''Set the server's beta
        parameter''')
    shell = Bool(False, config=True, help='''Go into interactive shell mode''')

    aliases = dict(set_beta = 'Interactor.set_beta',
                   shell = 'Interactor.shell',
                   zmq_port = 'Device.zmq_port',
                   zmq_url = 'Device.zmq_url')
    
    def on_startup_message(self, msg):
        mongo_url = msg.content.mongo_url
        db_name = msg.content.db_name
        
        c = Connection(mongo_url)
        self.db = getattr(c, db_name)

        if self.shell:
            IPython.embed()
            return
        elif np.isscalar(self.set_beta):
            self.send_recv('set_beta', {'value': self.set_beta})
        else:
            raise ValueError('Either you should go into shell mode or set a new '
                             'beta')
        
        
        

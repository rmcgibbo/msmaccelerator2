##############################################################################
# Imports
##############################################################################

import IPython
import numpy as np
from IPython.utils.traitlets import Unicode, Instance, Bool

# local
from ..core.database import session, connect_to_sqlite_db, Trajectory, Model
from ..core.device import Device

##############################################################################
# Classes
##############################################################################

class Interactor(Device):
    name = 'interact'
    path = 'msmaccelerator.interact.interactor.Interactor'
    short_description = 'Modify the parameters inside of a live server'
    long_description = ''
    
    set_beta = Instance(float, config=True, help='''Set the server's beta
        parameter''')
    shell = Bool(False, config=True, help='''Go into interactive shell mode''')
    db_path = Unicode('db.sqlite', config=True, help='''
        Path to the database (sqlite3 file)''')

    aliases = dict(set_beta = 'Interactor.set_beta',
                   shell = 'Interactor.shell',
                   zmq_port = 'Device.zmq_port',
                   zmq_url = 'Device.zmq_url')
    
    def on_startup_message(self, msg):
        connect_to_sqlite_db(self.db_path)

        if self.shell:
            IPython.embed()
            return
        elif np.isscalar(self.set_beta):
            self.send_recv('set_beta', {'value': self.set_beta})
        else:
            raise ValueError('Either you should go into shell mode or set a new '
                             'beta')
        
        
        

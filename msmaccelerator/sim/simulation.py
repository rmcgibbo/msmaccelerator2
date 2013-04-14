"""
Simple simulation process. Two dimensional dynamics on a lattice.


"""
#############################################################################
# Imports
##############################################################################

import os
import zmq
import uuid
import time
import numpy as np

from IPython.utils.traitlets import Unicode, Int

# local
from ..core.app import App
from ..core.message import message

#############################################################################
# Handlers
##############################################################################

class Simulator(App):
    name = 'simulate'
    path = 'msmaccelerator.sim.simulation.Simulator'
    short_description = 'Run a single round of dynamics'
    long_description = '''This device will connect to the msmaccelerator server,
        request the initial conditions with which to start a simulation, and
        propagate dynamics'''
    
    zmq_port = Int(12345, config=True, help='ZeroMQ port to connect to the server on')
    zmq_url = Unicode('127.0.0.1', config=True, help='URL to connect to server with')

    aliases = dict(zmq_port='Simulator.zmq_port',
                   zmq_url='Simulator.zmq_url')

    def start(self):
        ctx = zmq.Context()
        self.sock = ctx.socket(zmq.REQ)
        self.uuid = uuid.uuid4()
        self.sock.connect('tcp://%s:%s' % (self.zmq_url, self.zmq_port))
        
        # send the "here i am message"
        self.sock.send_json(message(msg_type='register_simulator',
                              sender_id=self.uuid,
                              content={}))

        msg = self.sock.recv_json()
        getattr(self, msg['header']['msg_type'])(**msg)    
    
    def simulate(self, header, parent_header, content):
        starting_structure = content['starting_structure']
        steps = content['steps']
        box_size = content['box_size']
        outdir = content['outdir']

        print 'Simulation: Let\'s do this!'

        trajectory = np.zeros((steps+1, 2))
        trajectory[0] = starting_structure

        # simulate the trajectory
        for i in range(steps):
            # 2 random numbers that are both uniform from {-1, 0, 1}
            r = np.random.randint(3, size=2) - 1
            # increment the trajectory, with periodic boundary conditions
            trajectory[i+1] = np.mod(trajectory[i] + r, box_size)

        # make this take a little bit of time, so that it's more fun
        time.sleep(2)

        # save the trajectory to disk
        outfn = os.path.join(outdir, '%s.npy' % self.uuid)
        np.save(outfn, trajectory)

        # tell the master that I'm done
        self.sock.send_json(message(msg_type='similation_status', content={
            'status': 'done',
            'traj_fn': outfn,
        }, parent_header=header, sender_id=self.uuid))

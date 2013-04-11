"""
Simple simulation process. Two dimensional dynamics on a lattice.


"""
#############################################################################
# Imports
##############################################################################

import os
import zmq
import numpy as np
import time

# local
from ..core.message import message

#############################################################################
# Handlers
##############################################################################


def simulate(req, header, parent_header, content):
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
    outfn = os.path.join(outdir, header['msg_id'] + '.npy')
    np.save(outfn, trajectory)

    # tell the master that I'm done
    req.send_json(message(msg_type='similation_status', content={
        'status': 'done',
        'traj_fn': outfn,
    }, parent_header=header))


def main(url, port):
    ctx = zmq.Context()
    req = ctx.socket(zmq.REQ)
    req.connect('tcp://%s:%s' % (url, int(port)))

    req.send_json(message(msg_type='register_simulator', content={}))
    msg = req.recv_json()
    globals()[msg['header']['msg_type']](req, **msg)

if __name__ == '__main__':
    main()

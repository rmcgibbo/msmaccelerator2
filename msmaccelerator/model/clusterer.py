"""
Simple clustering process. Builds an MSM and saves it to disk.
"""
#############################################################################
# Imports
##############################################################################

import os
import zmq
import uuid
import numpy as np

from scipy.cluster.hierarchy import fclusterdata
from msmbuilder.MSMLib import get_count_matrix_from_assignments, build_msm

# local
from ..core.app import App
from ..core.message import message

from IPython.utils.traitlets import Unicode, Int

#############################################################################
# Handlers
##############################################################################


class Modeler(App):
    name = 'model'
    path = 'msmaccelerator.model.clusterer.Modeler'
    short_description = 'Run the modeler, building an MSM on the available data'
    long_description = '''This device will connect to the msmaccelerator server,
        request the currently available data and build an MSM. That MSM will be
        used by the server to drive future rounds of adaptive sampling'''
    
    zmq_port = Int(12345, config=True, help='ZeroMQ port to connect to the server on')
    zmq_url = Unicode('127.0.0.1', config=True, help='URL to connect to server with')

    aliases = dict(zmq_port='Modeler.zmq_port',
                   zmq_url='Modeler.zmq_url')

    def start(self):
        ctx = zmq.Context()
        self.sock = ctx.socket(zmq.REQ)
        self.uuid = uuid.uuid4()
        self.sock.connect('tcp://%s:%s' % (self.zmq_url, self.zmq_port))
        
        # send the "here i am message"
        self.sock.send_json(message(msg_type='register_clusterer',
                                    sender_id=self.uuid, content={}))

        msg = self.sock.recv_json()
        getattr(self, msg['header']['msg_type'])(**msg)
        
    def cluster(self, header, parent_header, content):
        outdir = content['outdir']
        # load all of the trajectories
        trajs = [np.load(fn) for fn in content['traj_fns']]

        # concatenate them together
        data = np.asarray(np.concatenate(trajs), dtype=int)
        # form a unique number for each row, using a big prime (the eigth Mersenne)
        col = data[:, 0]*2147483647 + data[:, 1]
        # this is the number of unique data points in trajs
        unique = np.unique(col)
        n_unique = len(unique)

        # simple way to cluster them together
        allassignments = np.digitize(col, bins=unique)
        #allassignments = fclusterdata(data, t=n_unique, criterion='maxclust')
        # need to subtrack one because the digitizer starts the counting at 1, not 0
        allassignments -= 1
        # get the first data point assigned to each cluster
        centers = np.array([data[allassignments == i][0] for i in range(n_unique)])

        # reshape the allassignments array into a 2d array
        assignments = -1*np.ones((len(trajs), max(len(t) for t in trajs)),
                                 dtype=int)
        p = 0
        for i in range(len(trajs)):
            p_new = p + len(trajs[i])
            row = allassignments[p:p_new]
            assignments[i, :len(row)] = row
            p = p_new

        # build a msm
        counts = get_count_matrix_from_assignments(assignments, n_states=n_unique)
        msm = build_msm(counts, symmetrize='transpose', ergodic_trimming=False)
        rev_counts, t_matrix, populations, mapping = msm

        # save the data
        outfn = os.path.join(outdir, '%s.npz' % self.uuid)
        np.savez(outfn,
                 raw_counts=counts,
                 rev_counts=rev_counts,
                 t_matrix=t_matrix,
                 populations=populations,
                 mapping=mapping,
                 trajs=content['traj_fns'],
                 centers=centers)

        self.sock.send_json(message(msg_type='cluster_status', content={
            'status': 'done',
            'model_fn': outfn,
        }, parent_header=header, sender_id=self.uuid))

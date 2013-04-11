"""
Simple clustering process. Builds an MSM and saves it to disk.
"""
#############################################################################
# Imports
##############################################################################

import os
import zmq
import numpy as np

from scipy.cluster.hierarchy import fclusterdata
from msmbuilder.MSMLib import get_count_matrix_from_assignments, build_msm

# local
from ..core.message import message

#############################################################################
# Handlers
##############################################################################


def cluster(req, header, parent_header, content):
    outdir = content['outdir']
    # load all of the trajectories
    trajs = [np.load(fn) for fn in content['traj_fns']]

    # concatenate them together
    data = np.asarray(np.concatenate(trajs), dtype=int)
    # form a unique number for each row, using a big prime (the eigth Mersenne)
    col = data[:, 0]*2147483647 + data[:, 1]
    # this is the number of unique data points in trajs
    n_unique = len(np.unique(col))

    # simple way to cluster them together, using scipy
    allassignments = fclusterdata(data, t=n_unique, criterion='maxclust')
    # need to subtrack one because fclusterdata starts the counting at 1, not 0
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
    outfn = os.path.join(outdir, header['msg_id'] + '.npz')
    np.savez(outfn,
             raw_counts=counts,
             rev_counts=rev_counts,
             t_matrix=t_matrix,
             populations=populations,
             mapping=mapping,
             trajs=content['traj_fns'],
             centers=centers)

    req.send_json(message(msg_type='cluster_status', content={
        'status': 'done',
        'model_fn': outfn,
    }, parent_header=header))


def main(url, port):
    ctx = zmq.Context()
    req = ctx.socket(zmq.REQ)
    req.connect('tcp://%s:%s' % url, int(port))
    # send the "here i am" message
    req.send_json(message(msg_type='register_clusterer', content={}))

    # receive a single message and respond to it
    msg = req.recv_json()
    globals()[msg['header']['msg_type']](req, **msg)

if __name__ == '__main__':
    main()

"""
Simple clustering process. Builds an MSM and saves it to disk.
"""
#############################################################################
# Imports
##############################################################################

import os
import numpy as np

# mdtraj
import mdtraj.trajectory
# msmbuilder
import msmbuilder.io
import msmbuilder.metrics
import msmbuilder.Trajectory
import msmbuilder.MSMLib
import msmbuilder.clustering

# local
from ..core.device import Device

from IPython.utils.traitlets import Unicode, Int, Float, Enum, Bool

#############################################################################
# Handlers
#############################################################################


class Modeler(Device):
    name = 'model'
    path = 'msmaccelerator.model.clusterer.Modeler'
    short_description = 'Run the modeler, building an MSM on the available data'
    long_description = '''This device will connect to the msmaccelerator server,
        request the currently available data and build an MSM. That MSM will be
        used by the server to drive future rounds of adaptive sampling'''

    stride = Int(2, config=True, help='''Subsample data by taking only
        every stride-th point''')
    lag_time = Int(1, config=True, help='''Lag time for building the
        model, in units of the stride. This way, we don't do an assignment step''')

    rmsd_atom_indices = Unicode('AtomIndices.dat', config=True, help='''File
        containing the indices of atoms to use in the RMSD computation''')
    rmsd_distance_cutoff = Float(0.2, config=True, help='''Distance cutoff fo
        clustering''')
    symmetrize = Enum(['MLE', 'Transpose', None], default='MLE', config=True,
        help='''Symmetrization method for constructing the reversibile counts
        matrix''')
    ergodic_trimming = Bool(False, config=True, help='''Do ergodic trimming when
        constructing the Markov state model''')

    aliases = dict(stride='Modeler.stride',
                   lag_time='Modeler.lag_time',
                   rmsd_atom_indices='Modeler.rmsd_atom_indices',
                   rmsd_distance_cutoff='Modeler.rmsd_distance_cutoff',
                   conf_pdb='Modeler.conf_pdb',
                   symmetrize='Modeler.symmetrize',
                   trim='Modeler.ergodic_trimming',
                   zmq_url='Device.zmq_url',
                   zmq_port='Device.zmq_port')

    def on_startup_message(self, msg):
        """This method is called when the device receives its startup message
        from the server
        """
        assert msg.header.msg_type in ['construct_model'], 'only allowed methods'
        return getattr(self, msg.header.msg_type)(msg.header, msg.content)

    def construct_model(self, header, content):
        # the message needs to not contain unicode

        trajs = self.load_trajectories(content.traj_fns)
        assignments, generator_indices = self.cluster(trajs)
        counts, rev_counts, t_matrix, populations, mapping =  self.build_msm(assignments)

        outfn = os.path.join(content.outdir, self.uuid + '.h5')
        # TODO: add transparent saving/loading of CSR matricies to msmbuilder.io
        msmbuilder.io.saveh(outfn,
                            # counts matrix (CSR)
                            counts_data=counts.data,
                            counts_indices=counts.indices,
                            counts_intptr=counts.indptr,
                            # rev counts matrix (CSR)
                            rev_counts_data=rev_counts.data,
                            rev_counts_indices=rev_counts.indices,
                            rev_counts_indptr=rev_counts.indptr,
                            # transition matrix (CSR)
                            t_matrix_data=t_matrix.data,
                            t_matrix_indices=t_matrix.indices,
                            t_matrix_indptr=t_matrix.indptr,
                            populations=populations,
                            mapping=mapping,
                            assignments=assignments,
                            assignments_stride=np.array([self.stride]),
                            lag_time=np.array([self.lag_time]),
                            traj_fns=np.array(content.traj_fns))

        self.send_message(msg_type='Modeler_finished', content={
            'outfn': outfn
        })


    def load_trajectories(self, traj_fns):
        """Load up the trajectories, taking into account both the stride and
        the atom indices"""

        trajs = []
        atom_indices = np.loadtxt(self.rmsd_atom_indices, dtype=int)

        for traj_fn in traj_fns:
            # use the mdtraj dcd reader, but then monkey-patch
            # the coordinate array into shim for the msmbuilder clustering
            # code that wants the trajectory to act like a dict with the XYZList
            # key.
            t =  mdtraj.trajectory.load(traj_fn)
            t2 = ShimTrajectory(t.xyz[::self.stride, atom_indices, :])

            trajs.append(t2)

        if len(trajs) == 0:
            raise ValueError('No trajectories found!')

        return trajs


    def cluster(self, trajectories):
        metric = msmbuilder.metrics.RMSD()
        clusterer = msmbuilder.clustering.KCenters(metric, trajectories,
                                        distance_cutoff=self.rmsd_distance_cutoff)
        assignments = clusterer.get_assignments()

        # if we get the generators as a trajectory, it will only
        # have the reduced set of atoms.

        # the clusterer contains indices with respect to the concatenated trajectory
        # inside the clusterer object. we need to reindex to get the
        # traj/frame index of each generator
        # print 'generator longindices', clusterer._generator_indices
        # print 'traj lengths         ', clusterer._traj_lengths
        generator_indices = reindex_list(clusterer._generator_indices,
                                         clusterer._traj_lengths)
        # print 'generator indices', generator_indices

        # but these indices are still with respect to the traj/frame
        # after striding, so we need to unstride them
        generator_indices[:,1] *= self.stride

        # print generator_indices

        return assignments, generator_indices

    def build_msm(self, assignments):
        counts = msmbuilder.MSMLib.get_count_matrix_from_assignments(assignments,
            lag_time=self.lag_time)

        result = msmbuilder.MSMLib.build_msm(counts, symmetrize=self.symmetrize,
                                             ergodic_trimming=self.ergodic_trimming)
        # unpack
        rev_counts, t_matrix, populations, mapping = result
        return counts, rev_counts, t_matrix, populations, mapping


############################################################################
# Utilities
############################################################################

def reindex_list(indices, sublist_lengths):
    """Given a list of indices giving the position of items in a long list,
    which actually composed of a number of short lists concatenated together,
    determine which short list, and what index within that short list, each
    entry corresponds to

    Example
    -------
    >>> indices = [1, 31, 41]
    >>> sublist_lengths = [20, 20, 20]
    reindex_list(indices, sublist_lengths)
    array([[ 0,  1],
           [ 1, 11],
           [ 1, 1]])
    """
    cumulative = np.concatenate([[0], np.cumsum(sublist_lengths)])
    if np.any(indices >= cumulative[-1]):
        raise ValueError('Index off the end')

    output = np.zeros((len(indices), 2), dtype=int)
    for ii, longindex in enumerate(indices):
        k = np.argmax(cumulative[cumulative <= longindex])
        residual = longindex - cumulative[k]

        output[ii] = k, residual
    return output

class ShimTrajectory(dict):
    """This is a dict that can be used to interface some xyz coordinates
    with MSMBuilder's clustering algorithms.

    I'm really sorry that this is necessary. It's horridly ugly, but it comes
    from the fact that I want to use the mdtraj trajectory object (its better),
    but the OpenMM code hasn't been rewritted to use the mdtraj trajectory
    yet. Soon, we will move mdtraj into msmbuilder, and this won't be necessary.
    """
    def __init__(self, xyz):
        self['XYZList'] = xyz

    def __len__(self):
        return len(self['XYZList'])

"""
ZMQ device that builds an MSM and saves it to disk.
"""
#############################################################################
# Imports
##############################################################################

import os
import numpy as np
import pickle

# mdtraj
import mdtraj.trajectory
import msmbuilder.io
import msmbuilder.metrics
import msmbuilder.Trajectory
import msmbuilder.MSMLib
import msmbuilder.clustering

# local
from ..core.markovstatemodel import MarkovStateModel
from ..core.device import Device

from ..core.traitlets import FilePath
from IPython.utils.traitlets import Unicode, Int, Float, Enum, Bool

#############################################################################
# Handlers
#############################################################################


class Modeler(Device):
    name = 'model'
    path = 'msmaccelerator.model.modeler.Modeler'
    short_description = 'Run the modeler, building an MSM on the available data'
    long_description = '''This device will connect to the msmaccelerator server,
        request the currently available data and build an MSM. That MSM will be
        used by the server to drive future rounds of adaptive sampling.
        Currently, we're using RMSD clustering with the K-centers distance
        metric. We can make this more configurable in the future.'''

    stride = Int(1, config=True, help='''Subsample data by taking only
        every stride-th point''')
    topology_pdb = FilePath(config=True, extension='.pdb', help='''PDB file
        giving the topology of the system''')
    lag_time = Int(1, config=True, help='''Lag time for building the
        model, in units of the stride. Currently, we are not doing the step
        in MSMBuilder that is refered to as "assignment", where you assign
        the remaining data that was not used during clustering to the cluster
        centers that were identified.''')
    rmsd_atom_indices = FilePath('AtomIndices.dat', extension='.dat', config=True,
        help='''File containing the indices of atoms to use in the RMSD computation. Using
        a PDB as input, this file can be created with the MSMBuilder script
        CreateAtomIndices.py''')
    rmsd_distance_cutoff = Float(0.2, config=True, help='''Distance cutoff for
        clustering, in nanometers. We will continue to create new clusters
        until each data point is within this cutoff from its cluster center.''')
    symmetrize = Enum(['MLE', 'Transpose', None], default='MLE', config=True,
        help='''Symmetrization method for constructing the reversibile counts
        matrix.''')
    ergodic_trimming = Bool(False, config=True, help='''Do ergodic trimming when
        constructing the Markov state model. This is generally a good idea for
        building MSMs in the high-data regime where you wish to prevent transitions
        that appear nonergodic because they've been undersampled from influencing
        your model, but is inappropriate in the sparse-data regime when you're
        using min-counts sampling, because these are precisiely the states that
        you're most interested in.''')
    use_custom_metric = Bool(False, config=True, help='''Should we use
         a custom distance metric for clusering instead of RMSD?''')
    custom_metric_path = Unicode('metric.pickl', config=True, help='''File
         containing a pickled metric for use in clustering.''')

    aliases = dict(stride='Modeler.stride',
                   lag_time='Modeler.lag_time',
                   rmsd_atom_indices='Modeler.rmsd_atom_indices',
                   rmsd_distance_cutoff='Modeler.rmsd_distance_cutoff',
                   topology_pdb='Modeler.topology_pdb',
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
        """All the model building code. This code is what's called by the
        server after registration."""
        # the message needs to not contain unicode
        assert content.output.protocol == 'localfs', "I'm currently only equipped for localfs output"

        # load up all of the trajectories
        trajs = self.load_trajectories(content.traj_fns)

        # run clustering
        if use_custom_metric:
            metric = custom_metric_path
        else:
            metric = None
        assignments, generator_indices = self.cluster(trajs, metric)

        # build the MSM
        counts, rev_counts, t_matrix, populations, mapping = self.build_msm(assignments)

        # save the results to disk
        msm = MarkovStateModel(counts=counts, reversible_counts=rev_counts,
            transition_matrix=t_matrix, populations=populations, mapping=mapping,
            generator_indices=generator_indices, traj_filenames=content.traj_fns,
            assignments_stride=self.stride, lag_time=self.lag_time)
        msm.save(content.output.path)

        # tell the server that we're done
        self.send_recv(msg_type='modeler_done', content={
            'status': 'success',
            'output': {
                'protocol': 'localfs',
                'path': content.output.path
            },
        })

    def load_trajectories(self, traj_fns):
        """Load up the trajectories, taking into account both the stride and
        the atom indices"""

        trajs = []
        if os.path.exists(self.rmsd_atom_indices):
            self.log.info('Loading atom indices from %s', self.rmsd_atom_indices)
            atom_indices = np.loadtxt(self.rmsd_atom_indices, dtype=np.int)
        else:
            self.log.info('Skipping loading atom_indices. Using all.')
            atom_indices = None

        for traj_fn in traj_fns:
            # use the mdtraj dcd reader, but then monkey-patch
            # the coordinate array into shim for the msmbuilder clustering
            # code that wants the trajectory to act like a dict with the XYZList
            # key.
            self.log.info('Loading traj %s', traj_fn)
            if not os.path.exists(traj_fn):
                self.log.error('Traj file reported by server does not exist: %s' % traj_fn)
                continue

            t = mdtraj.trajectory.load(traj_fn, atom_indices=atom_indices,
                                       top=self.topology_pdb)
            t2 = ShimTrajectory(t.xyz[::self.stride, :])

            trajs.append(t2)

        if len(trajs) == 0:
            raise ValueError('No trajectories found!')

        self.log.info('loaded %s trajectories', len(trajs))
        self.log.info('loaded %s total frames...', sum(len(t) for t in trajs))
        self.log.info('loaded %s atoms', t2['XYZList'].shape[1])

        return trajs

    def cluster(self, trajectories, metric):
        """Cluster the trajectories into microstates.

        Returns
        -------
        assignments : np.ndarray, dtype=int, shape=[n_trajs, max_n_frames]
            assignments is a 2d arry giving the microstate that each frame
            from the simulation is assigned to. The indexing semantics are
            a little bit nontrivial because of the striding and the lag time.
            They are that assignments[i,j]=k means that in the `ith` trajectory,
            the `j*self.stride`th frame is assiged to microstate `k`.
        generator_indices : np.ndarray, dtype=int, shape=[n_clusters, 2]
            This array gives the indices of the clusters centers, with respect
            to their position in the trajectories on disk. the semantics are
            that generator_indices[i, :]=[k,l] means that the `ith` cluster's center
            is in trajectory `k`, in its `l`th frame. Because of the striding,
            `l` will always be a multiple of `self.stride`.
        """
        if metric is None:
            metric = msmbuilder.metrics.RMSD()
        else:
            print("Loading custom metric: %s" % custom_metric_path)
            pickle_file = open(custom_metric_path)
            metric = pickle.load(pickle_file)

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
        generator_indices[:, 1] *= self.stride

        # print generator_indices

        return assignments, generator_indices

    def build_msm(self, assignments):
        """Build the MSM from the microstate assigned trajectories"""
        counts = msmbuilder.MSMLib.get_count_matrix_from_assignments(assignments,
            lag_time=self.lag_time)

        result = msmbuilder.MSMLib.build_msm(counts, symmetrize=self.symmetrize,
                                             ergodic_trimming=self.ergodic_trimming)
        # unpack the results
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
    but the msmbuilder code hasn't been rewritted to use the mdtraj trajectory
    yet. Soon, we will move mdtraj into msmbuilder, and this won't be necessary.
    """
    def __init__(self, xyz):
        self['XYZList'] = xyz

    def __len__(self):
        return len(self['XYZList'])

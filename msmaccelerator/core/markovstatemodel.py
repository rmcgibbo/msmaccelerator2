"""Container class to hold a MSM, backed by an HDF5 file on disk.
"""
##############################################################################
# Imports
##############################################################################
# stdlib
import numbers

#3rd party
import tables
import msmbuilder.io
import scipy.sparse
import numpy as np
from IPython.utils.traitlets import HasTraits, Instance

#local
from ..core.traitlets import CNumpyArray

##############################################################################
# Classes
##############################################################################


class MarkovStateModel(HasTraits):
    """Class to hold all of the attributes of a Markov state model,
    (optionally) backed by a HDF5 file.
    """
    handle = Instance('tables.file.File')

    counts = Instance('scipy.sparse.csr.csr_matrix')
    reversible_counts = Instance('scipy.sparse.csr.csr_matrix')
    transition_matrix = Instance('scipy.sparse.csr.csr_matrix')
    populations = CNumpyArray()
    mapping = CNumpyArray()
    assignments = CNumpyArray()
    generator_indices = CNumpyArray()
    assignments_stride = Instance(int)
    lag_time = Instance(int)
    traj_filenames = CNumpyArray()

    @classmethod
    def load(cls, filename):
        return cls(handle=tables.open_file(filename, 'r'))

    def save(self, filename):
        kwargs = {}
        for name in self.class_trait_names():
            attr = getattr(self, name)
            if isinstance(attr, scipy.sparse.csr_matrix):
                kwargs[name + '_data'] = attr.data
                kwargs[name + '_indices'] = attr.indices
                kwargs[name + '_indptr'] = attr.indptr
                kwargs[name + '_shape'] = np.array(attr.shape)
            elif isinstance(attr, np.ndarray):
                kwargs[name] = attr
            elif isinstance(attr, numbers.Number):
                kwargs[name] = np.array([attr])
            elif isinstance(attr, list):
                kwargs[name] = np.array(attr)


        msmbuilder.io.saveh(filename, **kwargs)

    def close(self):
        if self.handle is not None:
            self.handle.close()

    ##########################################################################
    # Default methods: These work with HasTraits to allow the the matricies
    # to be loaded lazily from disk if they're in the hdf5 file with `handle`
    ##########################################################################
    # This code is a little repetitive -- SORRY. It would be possible to
    # factor it out into a metaclass. That might make it shorter, but
    # it would be less comprehisible.
    ##########################################################################

    def _counts_default(self):
        if self.handle is not None:
            return scipy.sparse.csr_matrix((self.handle.root.counts_data,
                self.handle.root.counts_indices, self.handle.root.counts_indptr),
                shape=self.handle.root.counts_shape)
        return None

    def _reversible_counts_default(self):
        if self.handle is not None:
            return scipy.sparse.csr_matrix((self.handle.root.reversible_counts_data,
                self.handle.root.reversible_counts_indices, self.handle.root.reversible_counts_indptr),
                shape=self.handle.root.reversible_counts_shape)
        return None

    def _transition_matrix_default(self):
        if self.handle is not None:
            return scipy.sparse.csr_matrix((self.handle.root.transition_matrix_data,
                self.handle.root.transition_matrix_indices, self.handle.root.transition_matrix_indptr),
                shape=self.handle.root.transition_matrix_shape)
        return None

    def _populations_default(self):
        if self.handle is not None:
            return self.handle.root.populations[:]
        return None

    def _mapping_default(self):
        if self.handle is not None:
            return self.handle.root.mapping[:]
        return None

    def _assignments_default(self):
        if self.handle is not None:
            return self.handle.root.assignments[:]
        return None

    def _generator_indices_default(self):
        if self.handle is not None:
            return self.handle.root.generator_indices[:]
        return None

    def _traj_filenames_default(self):
        if self.handle is not None:
            return self.handle.root.traj_filenames[:]
        return None

    def _assignments_stride_default(self):
        if self.handle is not None:
            return int(self.handle.root.assignments_stride[0])

    def _lag_time_default(self):
        if self.handle is not None:
            return int(self.handle.root.lag_time[0])

    ##########################################################################
    # END Default methods
    ##########################################################################


    def _generator_indices_changed(self, old, new):
        assert new.ndim == 2, 'generator indices must be 2d'
        assert new.shape[1] == 2, 'generator indices must have 2 columns'

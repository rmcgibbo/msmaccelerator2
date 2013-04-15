"""
Container class to hold a MSM, backed by an HDF5 file on disk.
"""

import tables

class MarkovStateModel(object):
    def __init__(self):
        self._generators = None
        self._populations = None
        self._raw_counts = None
        self._reversible_counts = None
        self._transition_matrix = None
        self._trajectories = None
        self._tables_fh = None
        
    @classmethod
    def load(self, filename):
        self._fh = tables.File(filename, 'r')
        
    def save(self, filename):
        # io.saveh(filename, generators=self._generators,
        #                    populations=self._populations,
        #                    raw_counts=self._raw_counts,
        #                    reversible_counts=self._reversibile_counts,
        #                    transition_matrix=self._transition_matrix,
        #                    trajectories=self._trajectories)
    
    @property
    def generators(self):
        if self._generators is not None:
            return self._generators
        if self._fh is not None:
            self._generators = self._fh.root.generators[:]
            return self._generators
            
        raise ValueError('Sorry')
        
    @generators.setter
    def generators(self, value):
        self._generators = value
    
    
    @property
    def populations(self):
        return self._populations
    @populations.setter
    def populations(self, value):
        self._populations = value
    
    @property
    def raw_counts(self):
        return self._raw_counts
    @raw_counts.setter
    def raw_counts(self, value):
        self._raw_counts = value
        
    @property
    def reversible_counts(self):
        return self._reversible_counts
    @reversible_counts.setter
    def reversible_counts(self, value):
        self._reversible_counts = value
        
    @property
    def transition_matrix(self):
        return self._transition_matrix
    @transition_matrix.setter
    def transition_matrix(self, value):
        self._transition_matrix = value
            
    @property
    def trajectories(self):
        return self._trajectories
    @trajectories.setter
    def trajectories(self, value):
        self._trajectories = value

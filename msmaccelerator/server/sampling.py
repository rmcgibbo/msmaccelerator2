"""Adaptive sampling code. This module contains classes that are capable
of sampling from some kind of distribution and returning a starting structure
to the server that can be sent to a waiting client to propagate.

Note: this class uses a lot of traits programming. It can look a little
odd, since there are some automatically triggered callbacks, but it makes the
code pretty easy to use. If you don't understand what's going on, you should
try reading about enthought traits / ipython traitlets, or ask me (@rmcgibbo),
and I will try to improve the docstrings.
"""
##############################################################################
# Imports
##############################################################################
# stdlib
import os

# 3rd party
import numpy as np
import mdtraj as md
from IPython.config import Configurable
from IPython.utils.traitlets import Instance, Float, Unicode

# ours
from ..core.traitlets import CNumpyArray
from ..core.markovstatemodel import MarkovStateModel

##############################################################################
# Abstract Classes
##############################################################################


class BaseSampler(Configurable):
    """Adaptive sampler that simply returns a given initial structure.

    This can be used for the very first round when you have no data, and
    also as a base class for the other samplers
    """
    log = Instance('logging.Logger')
    statebuilder = Instance('msmaccelerator.server.statebuilder.StateBuilder')
    seed_structures = Unicode('ala5.pdb', config=True, help='''Trajectory file giving the
        initial structures that you want to sample from. This should be a
        single PDB or other type of loadable trajectory file. These structures
        will only be used in the beginning, before we have an actual MSM
        to use.''')

    def get_state(self):
        self.log.error(self.seed_structures)
        """Get a serialized state to send to the client to propage

        This is the main external interface by which the server interacts
        with the adaptive sampler.

        Returns
        -------
        serialized_state : string
            A string containing a serialized reprenation of the state
            to send to a client to simulate.
        """
        return self.statebuilder.build(self.select())

    def select(self):
        """Use adaptive sample algorithm to select a simulation frame

        This is the main method that should be overriden by Samplers if they
        want to implement a new adaptive sampling strategy Our implementation
        in the this base class just selects from the uniform distribution over
        the seed structures.

        Returns
        -------
        frame : md.Trajectory
            This method should return a Trajectory object, whose first
            frame contains the positions (and box vectors) that you want
            to send to the client to simulate.
        """
        if not os.path.exists(self.seed_structures):
            raise ValueError("I couldn't find the seed_structures file "
                "on the local filesystem. I need this configurable "
                "to know what starting conditions to send to the sampler, "
                "since no MSMs have been build")

        # if the seed structures trajectory is big and supports random
        # access, this might not be the most efficient, since we're loading
        # the whole trajectory just to get a single frame.
        traj = md.load(self.seed_structures)
        frame = np.random.randint(len(traj))

        self.log.info('Sampling from the seed structures, frame %d' % frame)
        return traj[frame]


class CentroidSampler(BaseSampler):
    """Adaptive sampler that uses the centroids/"generators"" of the states
    to choose amongst, with a multinomial distibition.

    This class DOES NOT actually contain a method to *set* the weights. That
    is done by subclasses. See, for example, CountsSampler, that sets the
    weights using the counts.

    """
    model = Instance('msmaccelerator.core.markovstatemodel.MarkovStateModel')
    model_fn = Unicode(help='''Filename of the markov model. This is a
        convenience handle. Once it's set, we'll load up the model internally.
        Note that this is not a configurable option, because by default it's
        setup within the AdaptiveServer to look for the most recent model.''')
    weights = CNumpyArray(help='''These are the weights of a multinomial distribution
        over the microstates that we select from when asked to select a new
        configuration to sample from. Different subclasses of this class
        can use different schemes to set the weights when a new model is
        registered by overriding the instance method _model_changed()''')

    def _model_fn_changed(self, old, new):
        """When the self.model_fn trait is changed, this method gets called
        automatically. We use this hook to load up the model from the supplied
        filename. This is a convenient way of keeping things in sync."""
        if self.model is not None:
            # lets try to explicitly close its handle
            self.model.close()

        self.model = MarkovStateModel.load(new)
        self.log.info('[CentroidSampler] New model, "%s", loaded', new)

    def _weights_changed(self, old, new):
        """When self.weights traits gets changed, this method gets called
        automatically. We use this hook to set the attribute
        self.cumulative_weights, which is needed by select but shouldn't
        be recomputed."""
        # keep the cumulative_weights updated to the current value
        # of the weights
        self.cumulative_weights = np.cumsum(new)
        np.testing.assert_almost_equal(self.cumulative_weights[-1], 1,
                                      err_msg='The weights don\'t sum to 1')
        self.log.info('[CentroidSampler] New sampling weights set!')


    def select(self):
        """Select a simulation frame from amongst the state centroids, choosing
        randomly from a multinomial distribution.

        Note that we're choosing based on `self.weights`, which should be set
        by a subclass!

        Returns
        -------
        frame : md.Trajectory
            This method retursn a Trajectory object, whose first frame
            contains the positions (and box vectors) that you want to send to
            the client to simulate.
        """

        if self.model is None or self.weights is None or len(self.weights) == 0:
            # fall back to the base sampler if we haven't seen a MSM yet
            self.log.error('CentroidSampler is falling back to BaseSampler '
                           'to get a structure, because no model or weights '
                           'are registered.')
            return super(CentroidSampler, self).select()

        # Find the index of the first weight over a random value.
        index = np.sum(self.cumulative_weights < np.random.rand())
        traj, frame = self.model.generator_indices[index]
        filename = self.model.traj_filenames[traj]

        # load up the generator from disk
        traj = md.trajectory.load(filename)[frame]
        self.log.info('Sampling from a multinimial. I choose '
                      'traj="%s", frame=%s', filename, frame)
        return traj


##############################################################################
# Concrete Classes
##############################################################################


class CountsSampler(CentroidSampler):
    beta = Float(1, config=True, help="""Temperature factor that controls the
        level of exploration vs. refinement. When beta = 0 (high temp), we do
        full exploration, putting simulations where few counts have been seen.
        When beta = 1 (room temp), we do uniform sampling from the microstate,
        with no preference based on their counts. When beta > 1 (low  temp),
        we do refinement, such that we focus on microstates with a high number
        of counts. At beta = 2, we choose microstates proportional to our
        estimate of their current equilibrium propbability. The explicit
        formula used is:
        Prob( choose state i ) ~ \sum_j C_{ij} ^{ beta - 1 }""")

    # TODO: Should we be using the reversible counts or the unsymmetrized counts?

    def _model_changed(self, old, new):
        """When the MarkovStateModel that this class is pointing to, self.model,
        is changed, this callback will be triggered. We use this hook to set
        the weights, which will be used by the superclass to randomly sample
        the generators with."""
        self.reset_weights()

    def _beta_changed(self, old, new):
        print 'beta changed'
        self.reset_weights()

    def reset_weights(self):
        if self.model is None:
            print 'no model yet'
            return

        counts_per_state = np.array(self.model.counts.sum(axis=1)).flatten() + 10.**-8
        w = np.power(counts_per_state, self.beta - 1.0)

        self.weights = w / np.sum(w)
        self.cumulative_weights = np.cumsum(self.weights)
        self.log.info('[CountsSampler] Beta=%s. Setting multinomial weights, %s',
                      self.beta, self.weights)

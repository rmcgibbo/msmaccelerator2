"""
Code for the server's interaction with OpenMM
"""
##############################################################################
# Imports
##############################################################################

import numpy as np
from simtk.unit import femtoseconds, nanometers
from simtk.openmm import Context, Platform, XmlSerializer, VerletIntegrator

##############################################################################
# Classes
##############################################################################


class OpenMMStateBuilder(object):
    """Build an OpenMM "state" that can be sent to a device to simulate.
    """
    def __init__(self, system, integrator=None):

        # if strings are passed in, assume that they are paths to
        # xml files on disk
        if isinstance(system, basestring):
            with open(system) as f:
                system = XmlSerializer.deserialize(f.read())
        if isinstance(integrator, basestring):
            with open(integrator) as f:
                integrator = XmlSerializer.deserialize(f.read())

        if integrator is None:
            # this integrator isn't really necessary, but it has to be something
            # for the openmm API to let us serialize the state
            integrator = VerletIntegrator(2*femtoseconds)
        self.context = Context(system, integrator, Platform.getPlatformByName('Reference'))

    def build(self, trajectory):
        """Create a serialized state from the first frame in a trajectory

        Parameteters
        ------------
        trajectory : mdtraj.trajectory.Trajectory
            The trajectory to take the frame from. We'll use both the the
            positions and the box vectors (if you're using periodic boundary
            conditions)
        """
        periodic = False
        if trajectory.unitcell_vectors is not None:
            a, b, c = trajectory.unitcell_lengths[0]
            np.testing.assert_array_almost_equal(trajectory.unitcell_angles[0], np.ones(3)*90)
            self.context.setPeriodicBoxVectors([a, 0, 0] * nanometers, [0, b, 0] * nanometers, [0, 0, c] * nanometers)
            periodic = True

        self.context.setPositions(trajectory.openmm_positions(0))
        state = self.context.getState(getPositions=True, getVelocities=True,
                                      getForces=True, getEnergy=True,
                                      getParameters=True, enforcePeriodicBox=periodic)
        return XmlSerializer.serialize(state)

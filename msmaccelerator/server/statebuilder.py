"""
Code for the server to build serialized states to send to the client
"""
##############################################################################
# Imports
##############################################################################

import os
import abc
import datetime
from cStringIO import StringIO

import numpy as np
from simtk.unit import femtoseconds, nanometers
from simtk.openmm import Context, Platform, XmlSerializer, VerletIntegrator

##############################################################################
# Classes
##############################################################################

class StateBuilder(object):
    __metaclass__ = abc.ABCMeta

    @abc.abstractmethod
    def build(self, trajectory):
        """Create a serialized state from the first frame in a trajectory

        Parameters
        ----------
        trajectory : mdtraj.trajectory.Trajectory
            The trajectory to take the frame from.
        """
        pass


class OpenMMStateBuilder(StateBuilder):
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
        """Create a serialized XML state from the first frame in a trajectory

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


class AmberStateBuilder(StateBuilder):
    def build(self, trajectory):
        """Create a serialized inpcrd from the first frame in a trajectory

        Parameteters
        ------------
        trajectory : mdtraj.trajectory.Trajectory
            The trajectory to take the frame from. We'll use both the the
            positions and the box vectors (if you're using periodic boundary
            conditions)
        """
        buf = StringIO()

        print >>buf, str(datetime.datetime.now())
        print >>buf, '%5d' % trajectory.n_atoms

        linecount = 0
        for atom in range(trajectory.n_atoms):
            for dim in range(3):
                # need to convert from nm to angstroms by multiplying by ten
                fmt = '%12.7f' % (10 * trajectory.xyz[0, atom, dim])
                assert len(fmt) == 12, 'fmt overflowed writing inpcrd. blowup?'
                buf.write(fmt)
                linecount += 1
                if linecount >= 6:
                    buf.write(os.linesep)
                    linecount = 0

        if trajectory.unitcell_lengths != None:
            if linecount != 0:
                buf.write(os.linesep)
            box = (trajectory.unitcell_lengths[0]*10).tolist()
            box.extend(trajectory.unitcell_angles[0].tolist())
            buf.write(('%12.7f' * 6) % tuple(box))
    
        return buf.getvalue()

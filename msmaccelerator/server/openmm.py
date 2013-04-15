"""
Code for the server's interaction with OpenMM


"""
##############################################################################
# Imports
##############################################################################

from simtk.unit import femtoseconds
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

    def build(self, positions):
        """Create a serialized state from a set of positions

        Parameteters
        ------------
        positions : np.ndarray or list of vec3
            The positions to set into the state
        """
        self.context.setPositions(positions)
        state = self.context.getState(getPositions=True, getVelocities=True,
                                      getForces=True, getEnergy=True,
                                      getParameters=True, enforcePeriodicBox=True)
        return XmlSerializer.serialize(state)

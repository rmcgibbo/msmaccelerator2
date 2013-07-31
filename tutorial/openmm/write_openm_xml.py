"""
This is just some example code showing how to write the system and integrator
XML files
"""
from simtk.openmm.app import *
from simtk.openmm import *
from simtk.unit import *

pdb = PDBFile('ala5.pdb')
forcefield = ForceField('amber99sbildn.xml', 'amber99_obc.xml')
#modeller = Modeller(pdb.topology, pdb.positions)
#modeller.addSolvent(forcefield, padding=1.0*nanometers)

# create a system
system = forcefield.createSystem(pdb.topology, nonbondedMethod=CutoffNonPeriodic,
                                 nonbondedCutoff=0.8*nanometer, constraints=HBonds,
                                 ewaldErrorTolerance=0.0005)
# and serialize it
print 'writing system.xml file'
with open('system.xml','w') as f:
    f.write(XmlSerializer.serialize(system))


# do the same for an integrator
integrator = LangevinIntegrator(300*kelvin, 1.0/picoseconds, 2.0*femtoseconds)
integrator.setConstraintTolerance(0.00001)
print 'writing integrator.xml file'
with open('integrator.xml', 'w') as f:
    f.write(XmlSerializer.serialize(integrator))

print system

#print 'Context...'
#context = Context(system, integrator, Platform.getPlatformByName("Reference"))
#context.setPositions(pdb.positions)

#box = [Vec3(1,0,0), Vec3(0,2,0), Vec3(0,0,3)] * angstroms
#context.setPeriodicBoxVectors(*box)
#state = context.getState(getPositions=True, getVelocities=True,
#                         getForces=True, getEnergy=True,
#                         getParameters=True, enforcePeriodicBox=True)

#with open('native2.xml', 'w') as f:
#    f.write(XmlSerializer.serialize(state))

#import IPython as ip
#ip.embed()

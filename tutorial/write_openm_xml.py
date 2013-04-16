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

#import IPython as ip
#ip.embed()

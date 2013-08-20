#!/bin/bash
#PBS -N testAmberAccelerator
#PBS -j oe
#PBS -l walltime=0:20:00,nodes=1:ppn=1:xk
#PBS -M gkiss@stanford.edu
#PBS -V

date
export AMBERHOME='/u/sciteam/gkiss/amber12'


cd /u/sciteam/gkiss/scratch/Pande/Robert/AmberOpenMM/
cp -r /u/sciteam/gkiss/robert/msmaccelerator2/tutorial/amber/input input

mkdir -p WorkDir
cd WorkDir

/u/sciteam/gkiss/opt/python-2.7.5/bin/accelerator serve --md_engine=AMBER --seed_structures ../input/ala5_TIP3P_equil.pdb &

/u/sciteam/gkiss/opt/python-2.7.5/bin/accelerator AMBER --precommand="aprun -n 1 -N 1" --mdin ../input/ala5_TIP3P.prod.in --prmtop ../input/ala5_TIP3P.prmtop --AmberSimulator.executable="pmemd.cuda"


wait

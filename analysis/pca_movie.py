"""Create a movie showing the evolution of the PCA density over adaptive sampling rounds
"""

import os
import glob
import sys
import subprocess
import itertools
import logging

import numpy as np
from sklearn.decomposition import PCA
import matplotlib.cm
import matplotlib.pyplot as pp

import mdtraj.trajectory
from msmbuilder.geometry import contact
from msmaccelerator.core.markovstatemodel import MarkovStateModel
logging.basicConfig(level=logging.DEBUG)


###############################################################################
# Globals
###############################################################################

PROJECT_DIR = '../tutorial'
MODELS_GLOB = '../tutorial/models/*.h5'
TRAJS_GLOB = '../tutorial/trajs/*.lh5'
ATOM_INDICES = '../tutorial/AtomIndices.dat'
# limits for the axes on the plot
# these will need to be set manually for your data
XLIM = (-3, 1.5)
YLIM = (-1.6, 1.7)
# value for the top of the colorbar
# this will need to be set manually for your data
VMAX = 2.11


###############################################################################
# Globals
###############################################################################



# the models, sorted by time
model_fns = sorted(glob.glob(MODELS_GLOB), key=lambda fn: os.stat(fn).st_ctime)

def load_trajs():
    """Load traejctories from disk

    """
    print 'loading trajs...'
    # load up ALL of the trajectories
    trajs = {}
    atom_indices = np.loadtxt(ATOM_INDICES, int)
    atom_pairs = np.array(list(itertools.combinations(atom_indices, 2)))

    traj_filenames = glob.glob(TRAJS_GLOB)
    # logging.debug('traj filenames %s', traj_filenames)

    for tfn in traj_filenames:
        t = mdtraj.trajectory.load(tfn)

        key = os.path.relpath(tfn, PROJECT_DIR)
        trajs[key] = contact.atom_distances(t.xyz, atom_pairs)


    print 'done'
    return trajs


def fit_pca(trajs):
    print 'fitting PCA...'
    pca = PCA(2, copy=True, whiten=False)
    X = np.vstack(trajs.values())
    pca.fit(X)
    print 'done'
    return pca


def main():
    trajs = load_trajs()
    pca = fit_pca(trajs)


    cmap2 = matplotlib.cm.hot_r
    #cmap1 = brewer2mpl.get_map('OrRd', 'Sequential', 9).mpl_colormap

    for i, mfn in enumerate(model_fns):
        msm = MarkovStateModel.load(mfn)
        try:
            X = np.vstack([trajs[str(t)] for t in msm.traj_filenames])
        except KeyError as e:
            logging.exception('Not found? round %d', i)
            continue

        X_reduced = pca.transform(X)
        pp.hexbin(X_reduced[:,0], X_reduced[:,1], cmap=cmap2, bins='log',
                  vmin=0, vmax=VMAX)

        pp.xlabel('PC 1')
        pp.ylabel('PC 2')
        pp.title('Round %d PCA: %d frames' % (i, X_reduced.shape[0]))
        pp.xlim(*XLIM)
        pp.ylim(*YLIM)
        cb = pp.colorbar()
        cb.set_label('log10(N)')
        
        fn = 'plot_%04d.png' % i
        print fn
        pp.savefig(fn)
        pp.clf()

    subprocess.check_output('echo y | avconv -i plot_%04d.png -c:v libx264 -preset slow -crf 1 output.avi', shell=True)

if __name__ == '__main__':
    main()

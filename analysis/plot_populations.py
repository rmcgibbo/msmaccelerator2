"""
Make a simple plot of the equilibrum populations (on the grid) vs round.

Saves it to a png file, populations.png
"""
import glob
import numpy as np
import itertools
import matplotlib.pyplot as pp
try:
    import brewer2mpl
except ImportError:
    print 'You need to install brewer2mpl to get sweet color maps'
    print 'It can be downloaded from here'
    print '    https://pypi.python.org/pypi/brewer2mpl/1.3.1'
    print 'or installed directly with pip or easy_install.'
    raise
    
models = []
for fn in glob.glob('models/*.npz'):
    models.append(np.load(fn))
# sort by the number of trajectories included in the model
models = sorted(models, key=lambda m: len(m['trajs']))

pp.figure(figsize=(9, 9))

colors = itertools.cycle(brewer2mpl.get_map('Paired', 'Qualitative', 9).mpl_colors)

for i, m in enumerate(models):
    centers = m['centers']
    pops = m['populations']

    subplot = pp.subplot(3, 3, i+1)
    pp.scatter(centers[:,0], centers[:,1], color=colors.next(),
        alpha=1, edgecolor='none', s=10000*pops, label=str(i))


    pp.xlim(-1, 10)
    pp.ylim(-1, 10)
    pp.legend()

pp.suptitle('Equilibrium populations by round', fontsize=16)
pp.savefig('populations.png')

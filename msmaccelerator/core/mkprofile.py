"""Command line script (subcommand of the main script) that creates
an empty configuration file for you
"""

import os
import sys

from IPython.utils.traitlets import Unicode

from .app import App


class MKProfile(App):
    name = 'mkprofile'
    path = 'msmaccelerator.core.mkprofile.MKProfile'
    short_description = 'Create a sample configuration file'
    long_description = '''This script will create a sample configuration fie
for msmbuilder. The file starts with all of its options commented out, but it
gives you a full list of all of the configurable options available.

The config will be saved to disk. Whenever an msmbuilder app is run, we try to
load up a config file. The search path is given by the function
msmb.config.app.config_file_paths(), which current looks in the current
directory and in $HOME/.msmbuilder.'''

    output_dir = Unicode('.', config=True, help='''Output directory in which
        to save the file msmbuilder_config.py''')
    aliases = dict(output_dir='MKProfile.output_dir')

    def start(self):
        import inspect
        from IPython.config.configurable import Configurable

        # all lines of the new config file
        lines = ['# Configuration file for msmaccelerator.']
        lines.append('')
        lines.append('c = get_config()')
        lines.append('')

        for cls in itersubclasses(Configurable):
            # get every subclass of Configurable that is part of
            # the msmb package (other subclasses are in IPython)
            pkg = inspect.getmodule(cls).__package__
            if pkg is not None and pkg.startswith('msmaccelerator'):
                lines.append(cls.class_config_section())

        if (self.output_dir != '') and (not os.path.exists(self.output_dir)):
            self.log.warning('Creating directory: %s', self.output_dir)
            os.makedirs(self.output_dir)

        # note that this needs to be consistent with the filename used for
        # loading the config file, in core.app
        path = os.path.join(self.output_dir, self.config_file_name)
        if os.path.exists(path):
            self.log.error("%s already exists. I don't want to overwrite it, "
                           "so I'm backing off...", path)
            sys.exit(1)

        print 'Saving config file to %s' % path

        with open(path, 'w') as f:
            print >> f, os.linesep.join(lines)


def itersubclasses(cls, _seen=None):
    """Generator over all subclasses of a given class, in depth first order.

    http://code.activestate.com/recipes/576949/

    Examples
    --------
    >>> list(itersubclasses(int)) == [bool]
    True
    >>> class A(object): pass
    >>> class B(A): pass
    >>> class C(A): pass
    >>> class D(B,C): pass
    >>> class E(D): pass
    >>>
    >>> for cls in itersubclasses(A):
    ...     print(cls.__name__)
    B
    D
    E
    C
    >>> # get ALL (new-style) classes currently defined
    >>> [cls.__name__ for cls in itersubclasses(object)] #doctest: +ELLIPSIS
    ['type', ...'tuple', ...]
    """

    if not isinstance(cls, type):
        raise TypeError('itersubclasses must be called with '
                        'new-style classes, not %.100r' % cls)
    if _seen is None:
        _seen = set()
    try:
        subs = cls.__subclasses__()
    except TypeError:  # fails only when cls is type
        subs = cls.__subclasses__(cls)
    for sub in subs:
        if sub not in _seen:
            _seen.add(sub)
            yield sub
            for sub in itersubclasses(sub, _seen):
                yield sub

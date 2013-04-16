"""MSMAccelerator app configuration system
"""
#-----------------------------------------------------------------------------
# Imports
#-----------------------------------------------------------------------------
# stdlib imports
from __future__ import print_function
import os

# ipython imports
from IPython.config.application import Application
from IPython.utils.text import indent, dedent, wrap_paragraphs
from IPython.config.loader import ConfigFileNotFound

#-----------------------------------------------------------------------------
# Globals
#-----------------------------------------------------------------------------

# there's probably a better way to do this, but I was having a little problem
# where the message "no config file found" was being printed twice, both
# by the RootApplication and by the subcommand, so I just put in a check to
# this global, so that it's only printed once
_printed_config_file_warning = False

#-----------------------------------------------------------------------------
# Classes
#-----------------------------------------------------------------------------


class ConfigurationError(Exception):
    pass


class App(Application):
    #######################################################################
    # BEGIN options that need to be overridden in every subclass (subapp)
    #######################################################################
    name = None
    path = None
    short_description = 'short description'
    long_description = 'long description'
    subcommands = None
    #######################################################################
    # END options that need to be overridden in every subclass (subapp)
    #######################################################################

    config_file_name = 'msmaccelerator_config.py'
    option_description = u''

    def print_description(self):
        "Print the application description"
        lines = []
        lines.append(self.short_description)
        lines.append('='*len(self.short_description))
        lines.append('')
        for l in wrap_paragraphs(self.long_description):
            lines.append(l)
            lines.append('')
        print(os.linesep.join(lines))

    def initialize(self, argv=None):
        """Do the first steps to configure the application, including
        finding and loading the configuration file"""
        # load the config file before parsing argv so that
        # the command line options override the config file options
        self.load_config_file()
        super(App, self).initialize(argv)

    def load_config_file(self):
        try:
            super(App, self).load_config_file(self.config_file_name,
                                                        config_file_paths())
            self.log.info('Config file loaded.')

        except ConfigFileNotFound:
            global _printed_config_file_warning
            if _printed_config_file_warning is False:
                _printed_config_file_warning = True
                self.log.warning('No config file was found. I searched in %s' %
                    ', '.join(config_file_paths()))

    def print_subcommands(self):
        """Print the list of subcommands under this application"""

        if not self.subcommands:
            return

        lines = ["Subcommands"]
        lines.append('-'*len(lines[0]))
        for subc, (cls, help) in self.subcommands.iteritems():
            lines.append(subc)
            if help:
                lines.append(indent(dedent(help.strip())))
        lines.append('')

        print(os.linesep.join(lines))

    def print_options(self):
        if not self.flags and not self.aliases:
            return
        lines = ['Options']
        lines.append('-'*len(lines[0]))
        print(os.linesep.join(lines))
        self.print_flag_help()
        self.print_alias_help()
        print()


class RootApplication(App):
    name = 'accelerator'
    path = 'msmaccelerator.core.app.RootApplication'
    short_description = ('MSMAccelerator: Adaptive Sampling Molecular Dynamics '
                         'with Markov State Models')
    long_description = """MSMAccelerator is an distributed adaptive sampling
        engine. Please use the appropriate subcommand to get started."""
    citation_string = 'If you use this sofware in a publication, please cite our papers :)'

    def __init__(self, *args, **kwargs):
        self.subcommands = {}
        super(RootApplication, self).__init__(*args, **kwargs)

    def start(self):
        """Start the application's main loop.

        This will be overridden in subclasses"""
        if self.subapp is not None:
            return self.subapp.start()
        else:
            # if they don't choose a subcommand, display the help message
            self.parse_command_line('-help')

    def initialize(self, argv=None):
        super(RootApplication, self).initialize(argv)
        print(self.citation_string)

    def register_subcommand(self, *apps):
        for app in apps:
            if app.name in self.subcommands:
                msg = ('subcommand %s is not unique. you need to override'
                       ' it in your new subclass' % app.name)
                raise ConfigurationError(msg)
            self.subcommands[app.name] = (app.path, app.short_description)


#-----------------------------------------------------------------------------
# Utility functions
#-----------------------------------------------------------------------------


def config_file_paths():
    """Get a list of paths where the msmbuilder_config.py file might be found
    """

    return ['.', os.path.expanduser('~/.msmaccelerator')]

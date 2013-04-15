"""
An OpenMM reporter that passes off the current report, as a dict, to a
callback. We can use this to publish the report over a socket instead of
printing it to stdout.
"""
#############################################################################
# Imports
##############################################################################

import os
# note this code requires openmm 5.1, in which StateDataReporter was
# refactored for easier subclassing
from simtk.openmm.app import StateDataReporter

#############################################################################
# Classes
##############################################################################


class CallbackReporter(StateDataReporter):
    def __init__(self, reportCallback, reportInterval, **kwargs):
        super(CallbackReporter, self).__init__(os.devnull, reportInterval, **kwargs)

        self.reportCallback = reportCallback
        self.headers = None

    def report(self, simulation, state):
        if not self._hasInitialized:
            self._initializeConstants(simulation)
            self.headers = self._constructHeaders()
            self._hasInitialized = True

        # Check for errors.
        self._checkForErrors(simulation, state)

        # Query for the values
        values = self._constructReportValues(simulation, state)

        content = dict(zip(self.headers, values))
        self.reportCallback(content)

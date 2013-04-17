"""Extra traitlets.

I'm not sure why these isn't a NumpyArray trait in IPython, but there should
be.
"""
##############################################################################
# Imports
##############################################################################

import numpy as np
from IPython.utils.traitlets import TraitType

##############################################################################
# Classes
##############################################################################


class CNumpyArray(TraitType):
    default_value = np.array([])
    info_text = 'a numpy array'

    def validate(self, obj, value):
        if value is None:
            return value
        try:
            return np.array(value)
        except:
            self.error(obj, value)

    def __set__(self, obj, value):
        new_value = self._validate(obj, value)
        old_value = self.__get__(obj)
        obj._trait_values[self.name] = new_value
        if np.any(old_value != new_value):
            obj._notify_trait(self.name, old_value, new_value)

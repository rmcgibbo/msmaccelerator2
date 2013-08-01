"""Extra traitlets, including one for a filesystem path, and one for
a numpy array

"""
##############################################################################
# Imports
##############################################################################

import os
import numpy as np
from IPython.utils.traitlets import TraitType, TraitError, class_of

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


class Undefined(object):
    def __str__(self):
        return self.__repr__()
        
    def __repr__(self):
        return '<Undefined>'
Undefined = Undefined()


class FilePath(TraitType):
    info_text = 'a file path'

    def __init__(self, default_value=Undefined, exist=False, isfile=False,
                 isdir=False, extension=None, **metadata):
        self._exist = exist
        self._isfile = isfile
        self._isdir = isdir
        self._extension = extension
        if self._extension is not None and not self._extension.startswith('.'):
            raise ValueError('extension must start with ".". you supplied %s' % self._extension)
        super(FilePath, self).__init__(default_value, **metadata)

    def validate(self, obj, value):
        if value == Undefined:
            # if they haven't actually specified anything yet, this is presumably cominf
            # from the static initialization, before the config options are parsed
            return value

        if self._exist and not os.path.exists(value):
            self.error(obj, value, 'exist')
        if self._isfile and not os.path.isfile(value):
            self.error(obj, value, 'file')
        if self._isdir and not os.path.isdir(value):
            self.error(obj, value, 'dir')
        if self._extension is not None and os.path.splitext(value)[1] != self._extension:
            self.error(obj, value, 'extension')

        return os.path.abspath(value)

    def error(self, obj, value, reason=None):
        if reason is None:
            return super(FilePath, self).error(obj, value)

        if reason == 'exist':
            e = "The '%s' trait of %s instance must exist, but '%s' does not exist on disk."
        elif reason == 'file':
            e = "The '%s' trait of %s instance must be a file, '%s' is not."
        elif reason == 'dir':
            e = "The '%s' trait of %s instance must be a dir, but '%s' is not."
        elif reason == 'extension':
            e = "The '%s' trait of %s instance must end with {0}, but '%s' does not.".format(self._extension)

        raise TraitError(e % (self.name, class_of(obj), value))
            
            

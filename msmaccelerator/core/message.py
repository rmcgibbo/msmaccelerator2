"""Messaging for MSMAccelerator2

The MSMAccelerator messaging format is *heavily* inspired by the IPython
messaging format, which is documented here:
http://ipython.org/ipython-doc/dev/development/messaging.html

The general format is

{
  'header' : {
                'msg_id' : uuid,
                'sender_id' : uuid,
                # All recognized message type strings are listed below.
                'msg_type' : str,
     },

  # The actual content of the message must be a dict, whose structure
  # depends on the message type.
  'content' : dict,
}

The allowable 'msg_type's have not been fully decided yet. Sorry.

TODO: Figure out schema for all of the message types. What content do they
supply?
"""

#############################################################################
# Imports
##############################################################################

import time
import uuid
import pprint

#############################################################################
# Functions
##############################################################################


def pack_message(msg_type, sender_id, content):
    """Construct a message dict

    Parameters
    ----------
    msg_type : str
        The type of the message
    sender_id : uuid
        A unique identifier that identifies the sender process.
    content : dict
        Any content of the message. The semantics of the content dict
        are specific to different message types
    """
    # do some typechecking on the keys
    if not isinstance(msg_type, str):
        raise ValueError('msg_type must be string')
    if not isinstance(content, dict):
        raise ValueError('content must be dict')

    return squash_unicode({
        'header': {
            'sender_id': str(sender_id),
            'msg_id': str(uuid.uuid4()),
            'msg_type': msg_type,
            'time': time.time()
        },
        'content': content
    })


##############################################################################
# The following code is copied from IPython
# https://github.com/ipython/ipython/blob/master/IPython/kernel/zmq/session.py
##############################################################################


class Message(object):
    """A simple message object that maps dict keys to attributes.

    A Message can be created from a dict and a dict from a Message instance
    simply by calling dict(msg_obj)."""

    def __init__(self, msg_dict):
        dct = self.__dict__
        for k, v in dict(msg_dict).iteritems():
            if isinstance(v, dict):
                v = Message(v)
            dct[k] = v

    # Having this iterator lets dict(msg_obj) work out of the box.
    def __iter__(self):
        return iter(self.__dict__.iteritems())

    def __repr__(self):
        return repr(self.__dict__)

    def __str__(self):
        return pprint.pformat(self.__dict__)

    def __contains__(self, k):
        return k in self.__dict__

    def __getitem__(self, k):
        return self.__dict__[k]


def squash_unicode(obj):
    """coerce unicode back to bytestrings."""
    if isinstance(obj, dict):
        for key in obj.keys():
            obj[key] = squash_unicode(obj[key])
            if isinstance(key, unicode):
                obj[squash_unicode(key)] = obj.pop(key)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            obj[i] = squash_unicode(v)
    elif isinstance(obj, unicode):
        obj = obj.encode('utf8')
    return obj

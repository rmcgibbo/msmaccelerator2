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

  # In a chain of messages, the header from the parent is copied so that
  # clients can track where messages come from.
  'parent_header' : dict,

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

import uuid
import time

#############################################################################
# Functions
##############################################################################


def message(msg_type, sender_id, content, parent_header=None):
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
    parent_header : dict
        The header from a previous message, so that we can chain them



    """
    # do some typechecking on the keys
    if not isinstance(msg_type, basestring):
        raise ValueError('msg_type must be string')
    if not isinstance(content, dict):
        raise ValueError('content must be dict')

    if parent_header is None:
        parent_header = {}

    return {
        'header': {
            'sender_id': str(sender_id),
            'msg_id': str(uuid.uuid4()),
            'msg_type': msg_type,
            'time': time.time()
        },
        'parent_header': parent_header,
        'content': content
    }

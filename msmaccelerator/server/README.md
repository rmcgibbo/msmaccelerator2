## MSMAccelerator server

The server manages a ZMQ socket, on which it replies to messages.
The messages are basically either a simulator saying "give me some initial conditions"
or "i'm all done", or a modeler saying "let me build an MSM" or "i'm all done".

The server does not instantiate these processes, it just gives them work when they
contact it, and manages their results when they finish.

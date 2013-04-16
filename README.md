MSMAccelerator2
===============
*Next-generation* MSMAccelerator app.
[View a simple run and analysis here](http://nbviewer.ipython.org/urls/raw.github.com/rmcgibbo/msmaccelerator2/2623d76bbbee28d682c72aaa05575ed60b33c865/simple%2520analysis.ipynb)

Overview
--------
*MSMAccelerator* implements a protocol for simulating and modeling biomolecular
conformation dynamics known as Markov state model-driven adaptive sampling in a
*modern, extensible, distributed python environment*. MSMAccelerator combines
two existing technologies: OpenMM for GPU-accelerated molecular simulations
and MSMBuilder for building Markov state models (MSM) -- stochastic network
models of the system's dynamics.

Although some questions remain, the theory governing adaptive sampling has
been worked out for some time. See for example, Bowman, G. R.; Ensign, D. L;
Pande, V. S. "Enhanced Modeling via Network Theory: Adaptive Sampling of
Markov State Models" J. Chem. Theory Comput., 2010, 6 (3), pp 787–794 
doi: 10.1021/ct900620b. What has been lacking, up to now, is a practical
implementation of the algorithms.

Getting Started
---------------

## Installation

For the impatient MSMAccelerator can be run directly from the source directory
with the `accelerator` script, without installation. If you'd like to install
everything like a proper python package, you can do that by running
`python setup.py install`.

## Dependencies

The two major pieces of scientific software that MSMAccelerator depends on are
[OpenMM](https://simtk.org/home/openmm) to run the simulations and 
[MSMBuilder](https://github.com/SimTk/msmbuilder) to build models. To install
these packages, visit their respective websites for instructions.

MSMAccelerator has a distributed message-passing architecture, based on the
fast and lightweight messaging protocol [ZeroMQ](http://www.zeromq.org/). It
also uses the configuration framework from [IPython](http://ipython.org/). There
are a few other miscellaneous dependencies.  The easiest way to install these
libraries is with [pip](https://pypi.python.org/pypi/pip), the python package manager.

```
$ pip install pyzmq     # messaging framework
$ pip install ipython   # configration framework
$ pip install pyyaml    # message serialization
$ pip install pymongo   # database interaction
# Code for loading and saving trajectories lives in a different
# package called MDTraj. You can install that with the following
$ pip install git+git://github.com/rmcgibbo/mdtraj.git
```

TODO: Eliminate the pyyaml dependency by fixing the unicode issues with
the stdlib's json code.

Running some code
-----------------

Move into the `tutorial` directory, and start the MSMAccelerator server in
the background with `accelerator serve &`. This process will run in the
background and orchestrate state across the application. Now you can
start a single simulation with `accelerator simulate`, or build an MSM based on
your existing data with `accelerator model`.

Messaging protocol
------------------
The communication structure is modeled off the FAH workserver, instead
of workqueue. The accelerator server responds to requests. *It doesn't
initiate them*. The two types of requests it (basically) responds to are
a simulator coming online and saying "let me run a simulation", and a
"modeler" coming online and saying "let me build an MSM". The interleaving
of these two processes -- how many of each to run, how many cycles, etc, is
NOT controlled by the server. That is the domain of the queueing system or
whatever.

- The server process (`accelerator serve`) runs with a ZMQ router socket. It
  is capable of communicating with both simulators and modelers. When
  a simulator comes online, it pings the server who replies with an
  initial structure. When the simulator is done, it tells the server and then
  exits.
- Note that the simulator does not actually send back any data, it just sends
  back the location where the data is saved. Currently, we're sending paths
  in a JSON struct under the "protocol" "localfs", indicating that the files
  are transfered via a shared local file system. In the future, we can expand
  the protocol support to include something else, like an S3 bucket or HTTP.
- When a modeler comes online, it pings the server who replies with a list
  of all of the trajectories currently on disk. It builds an MSM and tells the
  server when it's done. When the server hears that the MSM is built, it loads
  some info from the MSM. This is where we plug in new adaptive sampling
  algorithms.
- It's really important that the server have a LIGHT memory and compute
  footprint, because its probably going to run on a cluster's head node under
  most circumstances.
- All messages between theserver and devices are JSON-encoded, following a
  format set out in `messaging.py`. This format is inspired by the
  [IPython messaging specification](http://ipython.org/ipython-doc/dev/development/messaging.html).
  One design goal of the messaging spec. is that the messages are suitable to
  be logged directly to a database backend for monitoring.

Communicating initial structures & setting simulation params.
-------------------------------------------------------------
We're bootstrapping off the excellent work that's been done in OpenMM5.1 and for
FAH Core17 with XML serialization. The `accelerator simulate` engine takes
as input the a sytem and integrator XML file that together specify the run
parameters. It's up to you to prepare those XML files.

Note: Currently, because of some questionable design decisions, the server
also needs access to the system xml file, which it uses to prepare the serialized
state that's communicated to simulator devices.

Design Goals
------------
- The app should be able to work on clusters with PBS systems. That means
  being able to work within the constraints of a queueing system, and taking
  advantage of the shared filesystem.
- Clustering and MSM-building cannot be required to happen on the head node,
  because many HPC clusters do not allow this. There needs to be separate
  processes submitted for the MSM building.
- WorkQueue was holding MSMAccelerator1 back. Installation was a pain, and
  debugging was hard. I felt like we were battling *against* the framework,
  which is not good. ZeroMQ is the answer.
- Trying to be agnostic w.r.t. MD engine is really hard, because you don't have a lot
  of robust interchange formats to work with. In MSMAccelerator1, we were
  trying to use PDBs to communicate initial state to the simulation engines,
  but PDB is such a loosey-goosey format, that this caused a lot of headaches.
  This code, at least for the first iteration, is tied to OpenMM.


Execution Workflow
------------------
Both the simulator and the clusterer exit when they're done with a single
round. **This is important** because it means that we can run the entire
workflow as a set of dependent PBS jobs, alternating between simulation and
clustering "jobs". But to control them and manage the state between rounds,
we need to have the server process running in the background. The only thing
that should need to be coordinated between the processes when you're writing
the PBS scripts that call is the url and port for the ZMQ connection.

But the server itself is AGNOSTIC to the ordering or interleaving of the
simulators and modelers.

Testing the code 
----------------
Everything is runnable from a single executable, `accelerator`, whose subcommands
are `serve`, `model` and `simulate`

Going forward, the structure for a set of PBS jobs that orchestrate the whole
workflow would be something like:

```
$ accelerator serve &  # runs in background

repeat N times:
  - run M times
      $ accelerator simulate
    wait for them to exit
  - run one
      $ accelerator model
    wait for it to finish
```

Take a look at the file `submit`, which is a little python script that does
exactly this.

Note that this doesn't really tie us to PBS at all, but it does *let* us use pbs if
we want to, because the N x M structure of the jobs is laid out at the beginning.
But we don't have to worry about handling state between the different simulate and
model rounds by writing out to the filesystem or saving ENV variables, because we
have this little lightweight ZMQ server who can tell each process what to do, when
it comes online.

Database
--------
To track the messages, we're using `MongoDB`. To make it easy, there are some cloud mongodb
services, including [MongoHQ](https://www.mongohq.com/home). You can go there and sign up
for a free account. Then, find the URI used to connect to your database. It should look
like `mongodb://<user>:<password>@dharma.mongohq.com:10077/msmaccelerator`. Substitute in
your real username and password, and then export it as the environment variable `MONGO_URL`,
like

`$ export MONGO_URL='mongodb://<user>:<password>@dharma.mongohq.com:10077/msmaccelerator'`

Currently, all the messages will be saved, when they hit the server, both on the sending and
recieving end. On the MongoHQ website, you can track the status of the messages. In the future,
we'll have a webapp that can do this monitoring.

For example, if you input `find({"header.msg_type": "register_simulator"}).limit(10)` into their
search box, you'll see all the events that correspond to a new simulation starting up.

License
-------
GPLv3s

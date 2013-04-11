MSMAccelerator2
===============
*sketch* for a next-generation MSMAccelerator app.

Design
------
- The app should be designed to work on relatively homogeneous clusters with a
  PBS system. This means that we can expect a bunch of jobs to be started at
  the same time, and finish at about the same time.
- Clustering and MSM-building cannot be required to happen on the head node,
  because many HPC clusters do not allow this. There needs to be separate
  "jobs" submitted for the MSM building.
- WorkQueue was holding MSMAccelerator1 back. Installation was a pain, and
  debugging was hard. I felt like we were battling *against* the framework,
  which is not good. We need to switch to a different framework for
  interprocess communication.
- Trying to be agnostic w.r.t. MD engine is really hard, because you don't have a lot
  of robust interchange formats to work with. In MSMAccelerator1, we were
  trying to use PDBs to communicate initial state to the simulation engines,
  but PDB is such a loosey-goosey format, that this caused a lot of headaches.
  This code, at least for the first iteration, should be tied more closely
  to a single MD engine.


Initial code
------------
- For the initial code, the "simulation" is dynamics on a 2d lattice with
  simple PBCs. This means that the starting structures that need to be
  communicated to the simulation engines are just a 2-tuple of coordinates
- We're going to do communication with [ZeroMQ](http://www.zeromq.org/),
  and specifically the python [pyzmq](http://zeromq.github.io/pyzmq/) bindings.
  This stuff is a little bit lower level than workqueue, but it's
  **battle tested** and used in real production systems. Also, our
  communication architecture is pretty simple.


Communication structure
-----------------------
- A "server" process (see `server.py`) runs with a ZMQ REP (reply) socket. It
  is capable of communicting with both "simulators" and "clusterers". When
  a "simulator" comes online, it pings the server who replies with an
  initial structure. When the simulator is done, it tells the server and then
  exits.
- Note that the simulator does not actually send back any data, it just sends
  back the location where the data is saved. Currently, this is just an
  absolute path on the local system, but in the future it could be a S3 bucket
  or something. But we really *should* take advantage of shared filesystems
  on clusters.
- When a "clusterer" comes online, it bigs the server who replies with a list
  of all of the trajectories currently on disk. It builds an msm and pings the
  server when it's done. When the server hears that the MSM is built, it loads
  some info from the MSM (currently the cluster centers and eq. populations)
  which it uses to generate future starting structures (currently by sampling
  from the multinomial)
- It's really important that the server process have a LIGHT memory and
  compute footprint. If need-be, the actual selection of the starting
  structure (e.g. from the multinomial or whatever adaptive sampling strategy
  is being used) could be done within the "simulator" process if the selection
  is getting too expensive within the server.
- All of the messages sent over the sockets will be JSON-encoded, following
  (basically), the structure set out by the IPython project for communication
  between the kernel and the frontends. Eventually, I want to log all of these
  messages to a database like mongodb that plays nice with JSON. The exact
  format of the messages is described in `msmaccelerator/message.py`. For some
  background, you can also ready the [IPython messaging specification](http://ipython.org/ipython-doc/dev/development/messaging.html).


Execution structure
-------------------
Both the simulator and the clusterer exit when they're done with a single
round. **This is important** because it means that we can run the entire
workflow as a set of dependent PBS jobs, alternating between simulation and
clustering "jobs". But to control them and manage the state between rounds,
we need to have the server process running in the background. The only thing
that should need to be coordinated between the processes when you're writing
the PBS scripts that call is the url and port for the ZMQ connection.

Testing the code 
----------------
Everything is runnable from a single executable, `accelerator`, whose subcommands
are `serve`, `model` and `simulate`

Going forward, the structure for a set of PBS jobs that orchestrate the whole
workflow would be something like:

```
$ accelerator serve &  # runs in background

repeat N times:
  - run M
      $ accelerator simulate
    wait for them to exit
  - run one
      $ accelerator model
    wait for it to finish
```

License
-------
GPLv3s

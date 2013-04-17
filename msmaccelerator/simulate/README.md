## Code for running the simulation

This code is run by `$ accelerator simulate`

### Flow
- simulator boots up
- connect to server
- recieve intial conditions
- propagate dynamics
- notify server when done

### Questions
- How to handle the simulator being killed mid-run?
- Heartbeat messages notifying the server about its status?

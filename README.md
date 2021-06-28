# pytla

*pytla* the Python (Integrable) Tunable Laser Assembly library!

This is meant to be an open source and relatively user friendly way to interact
with Integrable Tubable Laser Assembly lasers. 
The pytla package provides a base class `ITLA` that can be extended for specific 
manufacturer requirements with another yaml register file to specify the new registers.


## Current Specs Followed

* [OIF-ITLA-MSA-01.3](https://www.oiforum.com/wp-content/uploads/2019/01/OIF-ITLA-MSA-01.3.pdf). 
  * This communication scheme supports microITLA 1.1 devices as well.

## Status

This is very much a work in progress. Use at your own risk.

Hidden functions for each register (names the same as each register but in lowercase) 
are available. There are still a bunch of registers that have not been implemented. 
Namely the Module Status commands (0x20 - 0x2F) and dither control.

## Example Usage

```python
# import, initialize, and connect to laser
import pytla
laser = pytla.ITLA('/dev/ttyUSB0', 9600)
laser.connect()

# Set the frequency to 193.560 THz
laser.set_frequency(193.560)

# Set the power to 10 dBm
laser.set_power(10)
```

More info about features available currently can be found in [pytla docs](https://alexrkaufman.github.io/pytla).

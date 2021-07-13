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

This is very much a work in progress. Use at your own risk. I would call this
pre-alpha but most functionality exists and we use it at SpectrumLab.

Hidden functions for each register (names the same as each register but in lowercase)
are available. Some registers still don't have user friendly functions defined
for them.

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

## Paradigm

The basic paradigm we have used for implementing this library is one in which
functions are created for all registers based on a yaml file specifying and
describing each register. These are all implemented as hidden functions with a
single underscore.

For simplicity all ITLA register functions are named as follows: assuming
we have some register named `REGISTER` in the ITLA documentation the
corresponding function would be `_register()`.

## For Manufacturers

This library was designed to be simple to extend for implementing manufacturer
specific registers and functions. The first step is to create a yaml file
containing all of the additional registers your laser will utilize. Each entry
should have the following format.

```yaml
RegisterName:
  register: 0x00
  fnname: registername
  description: >
    Here we provide a description of this particular register for documentation
    purposes. It is best to format this the same way you would a docstring as it
    will be read as a docstring.
  readonly: [true/false]
  AEA: [true/false]
  signed: [true/false]
```

You can name your register whatever you'd like and name the function for
accessing it to whatever you'd like as long as it is acceptable for python.
Generally a best practice is to make the register function name all lowercase
and change dashes to underscores. The register value must be numeric. It can be
base 10 but best practice is hex values.

Assuming you have installed the pytla package and your yaml register
file is in the same folder as the file with the `MyLaser` class you can create a
class with hidden functions for your registers implemented in addition to
the basic ITLA1.3 registers and wrapper functions.

```python
from itla import ITLA

class MyLaser(ITLA):

    def __init__(self, port, baudrate=9600):
        register_files = ['myregisters.yaml']
        super().__init__(port, baudrate=baudrate, register_files=register_files)
```
## Acknowlegements

This work was done as a part of projects for

* Montana State University
* Spectrum Lab

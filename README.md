# pytla

*pytla* the Python (Integrable) Tunable Laser Assembly library!

This is meant to be an open source and relatively user friendly way to interact
with Integrable Tubable Laser Assembly lasers.
The pytla package provides a base class `ITLA` that can be extended for specific
manufacturer requirements with another yaml register file to specify the new registers.


## Current Specs Followed

* [OIF-ITLA-MSA-01.3](https://www.oiforum.com/wp-content/uploads/2019/01/OIF-ITLA-MSA-01.3.pdf).
  * This communication scheme supports microITLA 1.1 devices as well.
* [OIF-ITLA-MSA-01.2](https://www.oiforum.com/wp-content/uploads/2019/01/OIF-ITLA-MSA-01.2.pdf).
  * Some older devices still adhere to the 1.2 standard. These can be accessed
    by setting `version='1.2` parameter on ITLA object initialization. Example below.
  * If you are receiving unexpected execution errors on register functions like
    `_fcf3` it is likely you need to use `version='1.2'`.

## Status

This is very much a work in progress. Use at your own risk. I would call this
pre-alpha but most functionality exists and we use it at SpectrumLab.

Hidden functions for each register (names the same as each register but in lowercase)
are available. Some registers still don't have user friendly functions defined
for them.

It would be nice if we could include documentation for the
hidden register functions for each class in the pytla docs.

## Examples

### default use (with MSA-01.3 lasers)

```python3
# import, initialize, and connect to laser
import itla
import time
from itla.itla_errors import CPExcpetion

laser = itla.ITLA('/dev/ttyUSB0', 9600)
laser.connect()

# Set the frequency to 193.560 THz
laser.set_frequency(193.560)

# Set the power to 10 dBm
laser.set_power(10)

# enable the laser
# enabling takes some time so a CPExcpetion will be thrown
# It is necessary to catch this explicitly so the user
# doesnt continue on without explicitly handling this time delay
# (at least until we implement checking the pending bit in nop)
try:
    laser.enable()
except CPException:
    time.sleep(30)
```

More info about features available currently can be found in [pytla docs](https://alexrkaufman.github.io/pytla).

### version selection

You can also select the 1.2 spec if your laser does not yet support 1.3.
This is as simple as setting `version` in initialization of your `ITLA` object.

```python3
# import, initialize, and connect to laser
import itla
import time
from itla.itla_errors import CPExcpetion

laser = itla.ITLA('/dev/ttyUSB0', 9600, version='1.2')
laser.connect()

# Set the frequency to 193.560 THz
laser.set_frequency(193.560)

# Set the power to 10 dBm
laser.set_power(10)

# enable the laser
# enable the laser
# enabling takes some time so a CPExcpetion will be thrown
# It is necessary to catch this explicitly so the user
# doesnt continue on without explicitly handling this time delay
# (at least until we implement checking the pending bit in nop)
try:
    laser.enable()
except CPException:
    time.sleep(30)
```

#### Currently supported options under version

- [x] `version='1.3'` (OIF-ITLA-MSA-01.3)
- [x] `version='1.2'` (OIF-ITLA-MSA-01.2)

### Pure Photonics

We have also implemented a class for PurePhotonics lasers as an example of how
easy it can be for manufacturers to extend this library to control their own
ITLA based lasers.

```python3
# import, initialize, and connect to laser
import itla
import time
from itla.itla_errors import CPExcpetion

pplaser = itla.PPLaser('/dev/ttyUSB0')
pplaser.connect()

# Set the frequency to 193.560 THz
laser.set_frequency(193.560)

# Set the power to 10 dBm
laser.set_power(10)

# enable the laser
# enable the laser
# enabling takes some time so a CPExcpetion will be thrown
# It is necessary to catch this explicitly so the user
# doesnt continue on without explicitly handling this time delay
# (at least until we implement checking the pending bit in nop)
try:
    laser.enable()
except CPException:
    time.sleep(30)

laser.whispermode()
```


## Paradigm

The basic paradigm we have used for implementing this library is one in which
functions are created for all registers based on a yaml file specifying and
describing each register. These are all implemented as hidden functions with a
single underscore.

For simplicity all ITLA register functions are named as follows: assuming
we have some register named `REGISTER` in the ITLA documentation the
corresponding function would be `_register()`.

## For Manufacturers

If you would like to have a specific class available for your particular type of
laser please create a yaml file as specified below and submit it for inclusion.
Please also provide any details for the order of operations required to enable
or activate your features.

This library was designed to be simple to extend for implementing manufacturer
specific registers and functions. The first step is to create a yaml file
containing all of the additional registers your laser will utilize. Each entry
should have the following format.

```yaml
REGISTERNAME:
  register: 0xFF
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

Realistically, unless you are OIF and you are defining a 1.4 or 2.0 spec,
you should not need to write a class that depends directly on `ITLABase`.
Instead, you are likely adding functionality to the 1.3 (or older) standard.


```python3
from itla.itla13 import ITLA13

class MyLaser(ITLA13):

    def __init__(self, port, baudrate=9600):
        register_files = ['myregisters.yaml']
        super().__init__(port, baudrate=baudrate, register_files=register_files)

    def myfunction(self, data=None):
    ''' this function reads from REGISTERNAME and returns whatever bytes it
    sends back. this is the simplest version of reading a register you could do.
    it is usually better to do something with the response to convert
    the byte to an easier type to work with.'''

    response = self._registername()
    return response
```

## Acknowlegements

This work was done as a part of projects for

* Montana State University
* Spectrum Lab

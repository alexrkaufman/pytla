# pytla

*pytla* the Python (Integrable) Tunable Laser Assembly library!

This is meant to be an open source and relatively user friendly way to interact
with Integrable Tubable Laser Assembly lasers. 
The pytla package provides a base class `ITLA` that can be extended for specific 
manufacturer requirements with another yaml register file to specify the new registers.


## Current Specs Followed

* [OIF-ITLA-MSA-01.3](https://www.oiforum.com/wp-content/uploads/2019/01/OIF-ITLA-MSA-01.3.pdf). 
  * This communication scheme supports microITLA 1.1 devices as well.


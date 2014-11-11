# gauntlet #

Gauntlet is a tool for building and composing images in parts. A gauntlet build
process specifies a start image, some files to add, and a process to run. The
files that are changed or added after the process runs are added to a "shard"
object, with the original image listed as a dependency, so the final state of
the image can be reconstructed. The start image is also specified as a list of
one or more shards.

Gauntlet provides a gauntlet server, which is a content addressable object
store for storing completed shards, and large files such as source tarballs.
The remaining added build files, usually including the object to be executed,
are stored in git repositories, which the gauntlet server can index.

## Installation ##

Gauntlet uses setuptools for its configuration. With setuptools installed you
may simply run

~~~
$ python setup.py install
~~~

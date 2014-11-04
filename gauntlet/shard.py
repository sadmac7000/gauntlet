# -*- coding: utf-8 -*-
# Copyright © 2014 Casey Dahlin
#
# This file is part of Gauntlet.
#
# Gauntlet is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# Gauntlet is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE.  See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# Gauntlet.  If not, see <http://www.gnu.org/licenses/>.

import hashlib
import struct
import sys
import tarfile
import os
import shutil

class InvalidShardError(Exception):
    """
    Error thrown if we try to load a shard that is invalid.
    """
    pass

class Shard(object):
    """
    A Gauntlet Shard is a piece of an image file. It contains dependencies on
    other shards, and when combined with its dependencies it forms a complete
    disk image.

    Fundimentally a gauntlet file is a tar.gz with a header bolted on.
    """

    HEADER_MAGIC_STR = "gauntsh"
    HEADER_MAGIC_VER = 1

    def __init__(self, gz_stream, name, compose=[], compose_buildonly=[],
            drop_list=[], chmod_list={}):
        """
        Create a new shard. We provide the tar.gz content as a whole object.
        The `name`, `compose` and `compose_buildonly` arguments contain the
        config values for the name, compose, and compose-buildonly fields of
        the config used to build our contents. `drop_list` is a list of files
        in our dependencies that should be removed from the result.
        `chmod_list` is a hash from paths to integers specifying octal chmods
        of files provided by our dependencies.
        """

        self.gz_stream = gz_stream
        self.name = name
        self.compose = compose
        self.compose_buildonly = compose_buildonly
        self.drop_list = drop_list
        self.chmod_list = chmod_list

    def write_out(self, path):
        """
        Write out our shard to `path` and return the SHA-1 of the result.
        """

        sha = hashlib.sha1()

        with open(path, "w") as f:
            buf = struct.pack(">7sBB{}sHHHH".format(len(self.name)),
                    self.HEADER_MAGIC_STR, self.HEADER_MAGIC_VER,
                    len(self.name), self.name, len(self.compose),
                    len(self.compose_buildonly), len(self.drop_list),
                    len(self.chmod_list))
            sha.update(buf)
            f.write(buf)

            for item in self.compose + self.compose_buildonly:
                buf = struct.pack(">" + ("Q" * 5),
                        [ int(item[x:x + 8],16) for x in range(0, 40, 8)])
                sha.update(buf)
                f.write(buf)

            for item in self.drop_list:
                buf = struct.pack(">H{}s".format(len(item)), len(item), item)
                sha.update(buf)
                f.write(buf)

            for item, mod in self.chmod_list.iteritems():
                buf = struct.pack(">HH{}s".format(len(item)), len(item), mod,
                        item)
                sha.update(buf)
                f.write(buf)

            buf = 'a'
            while len(buf) > 0:
                buf = self.gz_stream.read(4096)
                sha.update(buf)
                f.write(buf)

        return sha.hexdigest()

    @classmethod
    def load(cls, path):
        """
        Load a shard from a file.
        """

        f = open(path, 'r')

        (magic, version, namelen) = struct.unpack(">7sBB", f.read(9))
        (name, compose_count, compose_buildonly_count, drop_count,
                chmod_count) = struct.unpack(">{}sHHHH".format(namelen),
                        f.read(namelen+8))

        if magic != cls.HEADER_MAGIC_STR:
            raise InvalidShardError("Bad shard magic")
        if version != cls.HEADER_MAGIC_VER:
            raise InvalidShardError("Bad shard version")

        compose = []

        compose_total = compose_count + compose_buildonly_count;

        while compose_total:
            sha_words = struct.unpack(">" + ("Q" * 5), f.read(20))
            sha = "".join([ hex(x)[2:] for x in sha_words ])
            compose += [sha]
            compose_total -= 1

        compose_buildonly = compose[compose_count:]
        compose = compose[:compose_count]

        drop_list = []

        while drop_count:
            (slen,) = struct.unpack(">H", f.read(2))
            string = struct.unpack(">" + str(slen) + 's', f.read(slen))
            drop_list += [string]
            drop_count -= 1

        chmod_list = {}

        while chmod_count:
            slen, mod = struct.unpack(">HH", f.read(4))
            string = struct.unpack(">" + str(slen) + 's', f.read(slen))
            chmod_list[string] = mod
            chmod_count -= 1

        return cls(f, name, compose, compose_buildonly, drop_list, chmod_list)

    def explode(self, path):
        """
        Extract the unique contents of this shard to the given location
        """
        tarfile.open(fileobj=self.gz_stream, mode='r|*').extractall(path)

if __name__ == "__main__":
    stream = open(sys.argv[2], 'r')
    shard = Shard(stream, sys.argv[1])
    print shard.write_out(sys.argv[3])
    shard2 = Shard.load(sys.argv[3])
    shutil.rmtree("/tmp/shardextract")
    os.makedirs("/tmp/shardextract")
    shard2.explode("/tmp/shardextract")

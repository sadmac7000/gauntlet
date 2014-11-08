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

import os
import shutil
import uuid

class Chroot(object):
    """
    A Gauntlet chroot. We will copy our build folder to this chroot, then run
    tasks within it.
    """

    def __init__(self, server, path = None):
        """
        In order to create a chroot, we need a server to resolve magic gauntlet
        files from.
        """
        self.server = server

        if path == None:
            path = os.path.join("/tmp", str(uuid.uuid4()))

        self.path = path

    def execute(self, config):
        """
        Run the build task for the given config in the chroot.
        """
        build_path = os.path.join(self.path, self.config['build-path'])

        try:
            shutil.rmtree(self.path)
        except OSError:
            pass

        shutil.copytree(".", build_path)

        for (path, sha) in config['file']:
            if os.path.isabs(path):
                path = os.path.join(self.path, path[1:])
            else:
                path = os.path.join(build_path, path)

            with open(path, 'w') as location:
                with self.server.get(sha) as data:
                    chunk = 'a'
                    while len(chunk) > 0:
                        chunk = data.read(4096)
                        location.write(chunk)

        pid = os.fork()

        if pid == 0:
            os.chroot(self.path)
            os.chdir('/')
            os.execl(config['task'], config['task'])
        else:
            os.waitpid(pid, 0)

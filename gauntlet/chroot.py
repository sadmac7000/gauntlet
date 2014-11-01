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

    def __init__(self, config, path = None):
        self.config = config

        if path == None:
            path = os.path.join("/tmp", str(uuid.uuid4()))

        self.path = path
        self.did_setup = False

    def setup(self):
        if self.did_setup:
            return

        self.did_setup = True

        if self.config.has_key('buildinit-rename'):
            build_path = os.path.join(self.path, self.config['buildinit-rename'])
        else:
            build_path = os.path.join(self.path, self.config['buildinit'])

        try:
            shutil.rmtree(self.path)
        except OSError:
            pass

        shutil.copytree(self.config['buildinit'], build_path)

    def execute(self):
        self.setup()
        pid = os.fork()

        if pid == 0:
            os.chroot(self.path)
            os.chdir('/')
            os.execl(self.config['task'], self.config['task'])
        else:
            os.waitpid(pid, 0)

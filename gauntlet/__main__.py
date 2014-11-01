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

import re
import os
from config import GauntletFile
from chroot import Chroot
from server import Server

if __name__ == "__main__":
    gfile = None
    server = Server("http://127.0.0.1:5000")

    hsh = server.post("hello")
    print hsh

    print server.get(hsh).read()

    with open(".gauntlet") as mine:
        gfile = GauntletFile(mine)

    chroot = Chroot(gfile, server)
    chroot.execute()

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

from flask import Flask, abort, request, send_file
import re
import os
import uuid
import hashlib
import shutil

__all__ = ["app"]

sha_re = re.compile(r'[a-zA-Z0-9]{40}')

app = Flask(__name__)

@app.route("/<sha>")
def retrieve(sha):
    """
    Return an object from our database given its SHA-1 handle
    """
    if not sha_re.match(sha):
        abort(404)

    obj_folder = app.config["GAUNTLET_OBJECTS_DIR"]
    folder = sha[0:2]
    obj = sha[2:]

    path = os.path.join(obj_folder, folder, obj)
    try:
        response = app.make_response(send_file(path))
        response.headers['X-Gauntlet-Type'] = "raw"
        return response
    except IOError:
        abort(404)

@app.route("/", methods=["POST"])
def send():
    """
    Place a new object into our database
    """
    tmp_loc = os.path.join(app.config["GAUNTLET_OBJECTS_DIR"],
            str(uuid.uuid4()))
    output = open(tmp_loc, "w")
    sha = hashlib.sha1()

    buf = "a"

    while len(buf) > 0:
        buf = request.stream.read(4096)
        sha.update(buf)
        output.write(buf)

    sha = sha.hexdigest()
    output.close()

    folder = os.path.join(app.config["GAUNTLET_OBJECTS_DIR"], sha[0:2])
    path = os.path.join(folder, sha[2:])

    try:
        os.mkdir(folder)
    except OSError:
        pass

    shutil.move(tmp_loc, path)

    return sha

if __name__ == "__main__":
    app.config["GAUNTLET_OBJECTS_DIR"] = "/tmp/test"
    try:
        shutil.rmtree(app.config["GAUNTLET_OBJECTS_DIR"])
    except OSError:
        pass
    os.mkdir(app.config["GAUNTLET_OBJECTS_DIR"])
    app.debug = True
    app.run()

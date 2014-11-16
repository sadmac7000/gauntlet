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

from flask import Flask, abort, request, send_file, redirect
import re
import os
import uuid
import hashlib
import shutil
import requests
import git as Git

__all__ = ["app", "Server"]

sha_re = re.compile(r'[a-zA-Z0-9]{40}')

app = Flask(__name__)

git_redirs = {}

@app.route("/<sha>")
def retrieve(sha):
    """
    Return an object from our database given its SHA-1 handle
    """
    if sha in git_redirs.keys():
        response = app.make_response(redirect(git_redirs[sha], 301))
        response.headers['X-Gauntlet-Type'] = "git"
        return response

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

@app.route("/git", methods = ['POST'])
def git():
    """
    Add a new git repository to our list.
    """
    objdir = app.config["GAUNTLET_OBJECTS_DIR"]
    gitroot = os.path.join(objdir, "git")

    if not os.path.exists(gitroot):
        os.makedirs(gitroot)

    numbers = [ int(x) for x in os.listdir(gitroot) if
            os.path.isdir(os.path.join(gitroot,x)) ]
    numbers.sort()

    idx = 0

    while idx < len(numbers) and idx == numbers[idx]:
        idx += 1

    gitdir = os.path.join(gitroot, str(idx))

    repo = Git.Repo.clone_from(request.data, gitdir, bare=True)

    for sha in repo.git.log('--pretty=%H').split():
        git_redirs[sha] = request.data

    return str(idx)

class ServerError(Exception):
    """
    An exception indicating some sort of error communicating with a server.
    """
    pass

class GitResult(object):
    def __init__(self, url, sha):
        self.sha = sha
        self.url = url

class Server(object):
    """
    A proxy object for a Gauntlet server
    """
    def __init__(self, uri):
        """
        Create a new proxy object for the gauntlet server at the given uri.
        """
        if uri[-1] != '/':
            uri += '/'

        self.uri = uri

    def get_size(self, sha):
        """
        Get the size of an object
        """
        req = requests.head(self.uri + str(sha))
        return int(req.headers['content-length'])

    def get(self, sha):
        """
        Fetch a hash from the gauntlet server
        """
        req = requests.get(self.uri + str(sha), stream=True,
                allow_redirects=False)

        if req.status_code == requests.codes.moved and req.headers['X-Gauntlet-Type'] == 'git':
            return GitResult(req.headers['Location'], sha)

        if req.status_code != requests.codes.ok:
            raise ServerError("Could not fetch " + sha + " from " + self.uri)

        return req.raw

    def post(self, data_or_fd):
        """
        Put a new object on the gauntlet server
        """
        req = requests.post(self.uri, data=data_or_fd)

        if req.status_code != requests.codes.ok:
            raise ServerError("Could not post item")

        return req.text

    def git_post(self, giturl):
        """
        Register a new git repository with the gauntlet server. The server will
        redirect to the git repository when we query for the hashes of commits
        therein.
        """
        req = requests.post(self.uri + 'git', data=giturl)

        if req.status_code != requests.codes.ok:
            raise ServerError("Could not post git URL")

        return int(req.text)

if __name__ == "__main__":
    app.config["GAUNTLET_OBJECTS_DIR"] = "/tmp/test"
    try:
        shutil.rmtree(app.config["GAUNTLET_OBJECTS_DIR"])
    except OSError:
        pass
    os.mkdir(app.config["GAUNTLET_OBJECTS_DIR"])
    app.debug = True
    app.run()

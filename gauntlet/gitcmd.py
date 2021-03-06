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

from __future__ import print_function

import os
import sys
import git
import errno
import re
import ConfigParser
import progressbar
from server import Server
from config import GauntletFile, ComposeCollideError
from ansi.color import fg as ansi_fg

from argparse import ArgumentParser

def real_repo(repo):
    if repo.bare:
        print("Command not valid for bare repo", file=sys.stderr)
        sys.exit(1)

class ArgFormatException(Exception):
    """
    Exception for a badly formed argument.
    """

class GitGauntletCmd(object):
    """
    The 'git gauntlet ...' command, which is used to manipulate gauntlet
    specific aspects of a gauntlet repo.
    """

    def __init__(self, git_dir = None, work_tree = None):
        self.repo = git.Repo()

        if git_dir:
            self.repo.git_dir = git_dir

        if work_tree:
            self.repo.working_tree_dir = work_tree

        base_args = ArgumentParser()
        sc = base_args.add_subparsers(title='actions')

        init_parse = sc.add_parser('init')
        init_parse.set_defaults(func=self.init)
        init_parse.add_argument('name')

        setter_cmds = {
                'server': self.server,
                'build-path': self.build_path,
                'name': self.name,
                'task': self.task,
        }

        for cmd in setter_cmds:
            parse = sc.add_parser(cmd)
            parse.set_defaults(func=setter_cmds[cmd])
            parse.add_argument('--set', nargs='?', default=None)

        compose_parse = sc.add_parser('compose')
        compose_parse.set_defaults(func=self.compose)
        compose_parse.add_argument('--add', nargs='+', default=None)
        compose_parse.add_argument('--drop', nargs='+', default=None)
        compose_parse.add_argument('--build-only', action='store_true')

        upload_parse = sc.add_parser('upload')
        upload_parse.set_defaults(func=self.upload)
        upload_parse.add_argument('--list', action='store_true')
        upload_parse.add_argument('--fetch', action='store_true')
        upload_parse.add_argument('--drop', action='store_true')
        upload_parse.add_argument('path', nargs='*')

        self.args = base_args.parse_args()
        self.func = self.args.func
        self.gfile_path = os.path.join(self.repo.working_tree_dir, ".gauntlet")

    def __call__(self):
        return self.func()

    def upload(self):
        """
        Main method for the 'upload' command. Puts a file on the gauntlet
        server and sets the 'file' directive.
        """

        found = False

        for i in [self.args.list, self.args.fetch, self.args.drop]:
            if not i:
                continue
            if not found:
                found = True
                continue
            print("You can only specify one of --list, --fetch, and --drop",
                    file=sys.stderr)
            return 1

        if self.args.drop and len(self.args.path) == 0:
            print ("You must specify filenames with --drop", file=sys.stderr)
            return 1

        if self.args.list and len(self.args.path) > 0:
                print("--list doesn't make sense with filenames",
                        file=sys.stderr)
                return 1

        reader = self.repo.config_reader()
        try:
            server = reader.get_value('gauntlet', 'server')
        except (ConfigParser.NoOptionError, ConfigParser.NoSectionError):
            print("You must set a gauntlet server\n"
                    "Use 'git gauntlet server --set <url>'", file=sys.stderr)
            return 1

        try:
            coloring = reader.get_value('color', 'ui')
        except ConfigParser.NoOptionError:
            coloring = 'auto'

        try:
            coloring_local = reader.get_value('color', 'gauntlet')
        except ConfigParser.NoOptionError:
            coloring_local = None

        if coloring_local == 'false':
            coloring = False
        elif coloring == 'false':
            coloring = False
        elif coloring == 'always':
            coloring = True
        else:
            coloring = os.isatty(1)

        gfile = self.get_gfile()

        if self.args.fetch:
            return self.upload_fetch(gfile, server)
        if self.args.drop:
            return self.upload_drop(gfile)
        if len(self.args.path) == 0:
            for path, sha in gfile['files'].iteritems():
                if coloring:
                    print('{} {}'.format(ansi_fg.green(sha), path))
                else:
                    print('{} {}'.format(sha, path))

            return 0

        ret = 0

        for path in self.args.path:
            ret += self.do_upload(path, gfile, server)

        self.put_gfile(gfile)
        return ret

    def upload_drop(self, gfile):
        """
        Process an upload --drop command
        """

        ret = 0
        for path in self.args.path:
            path = os.path.abspath(path)
            path = os.path.relpath(path, self.repo.working_tree_dir)

            if not path in gfile['files'].keys():
                print("No such upload '{}'".format(path), file=sys.stderr)
                ret += 1
            else:
                del gfile['files'][path]

        self.put_gfile(gfile)
        return ret

    def upload_fetch(self, gfile, server):
        """
        Process an upload --fetch command
        """

        server = Server(server)

        paths = gfile['files'].keys()

        if len(paths) == 0:
            print("No uploaded files to fetch", file=sys.stderr)
            return 1

        ret = 0

        if len(self.args.path) > 0:
            paths_good = []

            for path in self.args.path:
                path = os.path.abspath(path)
                path = os.path.relpath(path, self.repo.working_tree_dir)

                if not path in paths:
                    printf("No uploaded file at '{}'".format(path),
                            file=sys.stderr)
                    ret += 1
                else:
                    paths_good += [path]

            if not len(paths_good):
                return ret

            paths = paths_good

        for path in paths:
            sha = gfile['files'][path]
            abpath = os.path.join(self.repo.working_tree_dir, path)
            ret += self.upload_do_fetch(abpath, path, sha, server)

        return ret

    def upload_do_fetch(self, path, repopath, sha, server):
        """
        Get an upload from the server and put it at the given path
        """

        target = open(abpath, 'w')

        if os.isatty(2):
            size = server.get_size(sha)
            progress = self.progress("Downloading", repopath, size)
            progress.start()
        else:
            progress = None

        src = server.get(sha)

        buf = 'a'
        while len(buf) > 0:
            buf = src.read(4096)
            progress.update(len(buf))
            target.write(buf)

        if progress:
            progress.finish()

        target.close()
        return 0


    def do_upload(self, path, gfile, server):
        """
        Upload a single file to the gauntlet cache
        """
        repopath = os.path.abspath(path)

        if not repopath.startswith(self.repo.working_tree_dir):
            print("{}: File must be inside the "
                    "working tree folder".format(path), file=sys.stderr)
            return 1

        repopath = os.path.relpath(repopath, self.repo.working_tree_dir)

        # FIXME: Make sure repopath is in self.repo.untracked_files
        # once GitPython is updated and that property starts working again.

        if not os.path.exists(path):
            print("'{}' does not exist".format(repopath), file=sys.stderr)
            return 1

        server = Server(server)

        # The server is in flask, and apparently WSGI can't handle chunked
        # requests. There's code to implement a progress bar below, but it's
        # disabled since we have to chunk the request to do it.
        #
        # See https://github.com/mitsuhiko/flask/issues/367
        #
        #if os.isatty(2): #stderr
        #    progress = self.progress("Uploading", repopath,
        #            os.path.getsize(self.args.path))
        #else:
        #    progress = None

        with open(path, 'r') as f:
            #def f_iter():
            #    data = 'a'
            #    count = 0
            #    while len(data):
            #        data = f.read(4096)
            #        yield data
            #        count += len(data)
            #        progress.update(count)

            #if progress:
            #    progress.start()
            #    sha = server.post(f_iter())
            #    progress.finish()
            #else:
            #    sha = server.post(f)
            sha = server.post(f)

        gfile['files'][repopath] = str(sha)

        with open(os.path.join(self.repo.working_tree_dir, '.gitignore'),
            'a') as ignore:
            print(repopath, file=ignore)

        return 0

    def get_gfile(self):
        try:
            gfile_fd = os.open(self.gfile_path, os.O_RDONLY)
        except OSError, e:
            if e.errno != errno.ENOENT:
                raise

            print("Not a gauntlet repository", file=sys.stderr)
            sys.exit(1)

        return GauntletFile(os.fdopen(gfile_fd, 'r'))

    def put_gfile(self, gfile, create=False):
        flags = os.O_WRONLY
        if create:
            flags |= os.O_CREAT | os.O_EXCL
        else:
            flags |= os.O_TRUNC

        try:
            gfile_fd = os.open(self.gfile_path, flags, 0644)
            os.write(gfile_fd, str(gfile))
            os.close(gfile_fd)
        except OSError, e:
            if e.errno != errno.ENOENT:
                raise

            print("Not a gauntlet repository", file=sys.stderr)
            sys.exit(1)

    @staticmethod
    def process_compose(arg):
        fields = re.match('^(\w+):([a-zA-Z0-9]{40})$', arg)

        if fields == None:
            raise ArgFormatException("Compose packages are in "
                "<name>:<hash> form")

        return {'package': fields.group(1), 'hash': fields.group(2) }

    @staticmethod
    def progress(task, filename, size):
        """
        Get a progress bar
        """
        widgets = ['{} {} '.format(task, filename),
                progressbar.Bar(marker='=', left='[', right=']'), ' ',
                progressbar.Percentage(), ' ', progressbar.AdaptiveETA(), ' ',
                progressbar.AdaptiveTransferSpeed()]

        return progressbar.ProgressBar(widgets=widgets, maxval=size)

    def compose(self):
        """
        Main function for the 'git gauntlet compose' command. Adds a 'compose'
        or 'compose-buildonly' directive.
        """

        gfile = self.get_gfile()

        if self.args.build_only:
            directive = 'compose-buildonly'
        else:
            directive = 'compose'

        if self.args.drop:
                gfile[directive] = [x for x in gfile[directive] if x['package'] not in
                        self.args.drop]

        if self.args.add:
            try:
                gfile[directive] += [self.process_compose(x) for x in self.args.add]
            except ArgFormatException, e:
                print(e, file=sys.stderr)
                return 1
            except ComposeCollideError, e:
                print(e, file=sys.stderr)
                return 1

        if self.args.add or self.args.drop:
            self.put_gfile(gfile)
        else:
            strings = [x['package'] + ':' + x['hash'] for x in
                    gfile[directive]]
            print('\n'.join(strings))

        return 0

    def conf_setter(self, key):
        """
        Main function for any of our git commands which just gets or sets a
        singleton config parameter.
        """

        gfile = self.get_gfile()

        if self.args.set:
            gfile[key] = self.args.set
            self.put_gfile(gfile)
        else:
            print(gfile[key])

        return 0

    def build_path(self):
        """
        Main function for 'git gauntlet build-path'. Adds or reads a build-path
        directive in the .gauntlet file.
        """

        return self.conf_setter('build-path')

    def task(self):
        """
        Main function for 'git gauntlet task'. Adds or reads a task directive
        in the .gauntlet file.
        """

        return self.conf_setter('task')

    def name(self):
        """
        Main function for 'git gauntlet name'. Adds or reads a name directive
        in the .gauntlet file.
        """

        return self.conf_setter('name')

    def init(self):
        """
        Main function for 'git gauntlet init'. Creates the gauntlet file and
        initializes it with a name field.
        """
        try:
            gfile = GauntletFile()
            gfile['name'] = self.args.name
            self.put_gfile(gfile, create=True)
        except OSError, e:
            if e.errno != errno.EEXIST:
                raise

            print("Already initialized", file=sys.stderr)
            return 1

        return 0

    def server(self):
        """
        Main function for 'git gauntlet server'. Queries or sets the
        'gauntlet.server' config parameter for this repo.
        """

        writer = self.repo.config_writer()

        if self.args.set:
            writer.set_value('gauntlet', 'server', self.args.set)
        else:
            print(writer.get_value('gauntlet', 'server'))

        return 0

def main():
    """
    Main function for the git extension.
    """
    
    cmd = GitGauntletCmd(os.environ.get("GIT_DIR"),
            os.environ.get("GIT_WORK_TREE"))

    return cmd()


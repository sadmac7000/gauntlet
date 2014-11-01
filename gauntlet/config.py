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

class ConfigError(Exception):
    """
    An exception indicating some sort of error in a configuration. The error
    string should contain more details
    """
    pass

class ParseError(ConfigError):
    """
    An error message indicating problems parsing a configuration file.
    """
    pass

class Directive(object):
    """
    A configuration directive. This is a method-like object which is flagged as
    handling a given configuration directive.
    """
    def __init__(self, name, defaults, method):
        self.directive_name = name
        self.defaults = defaults
        self.method = method

    def __call__(self, *args, **kwargs):
        return self.method(*args, **kwargs)

class directive(object):
    """
    A decorator for wrapping methods into Directive objects.
    """
    def __init__(self, name, defaults = None):
        self.name = name
        self.defaults = defaults

    def __call__(self, method):
        return Directive(self.name, self.defaults, method)

class Config(dict):
    directive_splitter = re.compile(r'^([a-zA-Z0-9_]+)\s*:\s*(.+)$')

    def __init__(self, conf_file = None):
        """
        Initialize a Gauntlet configuration

        conf_file:
            A configuration file which will be parsed to generate the
            properties in this configuration.
        """

        dict.__init__(self)

        for item in self.__class__.__dict__.values():
            try:
                if item.defaults == None:
                    continue
            except AttributeError:
                continue

            self.__raw_setitem(item.directive_name, item.defaults)

        if conf_file == None:
            return

        line_prefix = ""

        for line in conf_file.readlines():
            comment = line.find("#")
            if comment >= 0:
                line = line[0:comment]

            line = (line_prefix + line).strip()
            line_prefix = ""

            if len(line) == 0:
                continue

            if line[-1] == '\\':
                line_prefix = line[:-1].strip() + " "
                continue

            self.parse_line(line)

    def defaults(self):
        return {}

    def parse_line(self, line):
        """
        Parse a single line of a gauntlet configuration. Lines are generally in
        the "directive: value" format, where 'value' could be anything
        depending on the directive.
        """

        if len(line) == 0:
            return

        match = self.directive_splitter.match(line)

        if match == None:
            raise ParseError("Malformed line: '" + line + "'")

        self[match.group(1)] = match.group(2)

    def __raw_setitem(self, key, item):
        """
        Shortcut to our parent class' setitem method.
        """
        dict.__setitem__(self, key, item)

    def __setitem__(self, key, value):
        """
        Set a config directive. The value is either an object of the
        appropriate type giving information about the directive value, or a
        string which can be parsed to make such an object.
        """
        for item in self.__class__.__dict__.values():
            try:
                if item.directive_name != key:
                    continue
            except AttributeError:
                continue

            self.__raw_setitem(key, item(self, value))
            return

        raise ConfigError("Unknown directive: '" + key + "'")

    def __str__(self):
        """
        Output a sumarized version of the config
        """

        ret = ""

        for k in self.keys():
            ret += k + ": " + str(self[k]) + "\n"

        return ret

class GauntletFile(Config):
    """
    A Gauntlet File configures a single Gauntlet image build. It tells us what
    images to compose and how to build the new content.
    """

    @directive("name")
    def name(self, string):
        return string

    @directive("buildinit-name", "build")
    def buildinit_rename(self, string):
        """
        This config parameter specifies what the buildinit folder should be
        named after it is copied into the chroot.
        """
        return string

    @directive("manifest")
    def manifest(self, string):
        """
        This config parameter specifies a manifest for the build results. All
        output files should be listed in the file specified here, which must be
        in the git repository with the Gauntletfile.
        """
        local = os.path.abspath('.')
        path = os.path.abspath(string)
        prefix = os.path.commonprefix([path, local])

        if not os.path.samefile(prefix, local):
            raise ConfigError("Manifest must be inside the repo")

        if not os.path.isfile(path):
            raise ConfigError("Manifest must be a file")

        with open(path) as manifest:
            return [x.strip() for x in manifest.readlines() if len(x.strip())]

    @directive("task", "/build/build.exec")
    def task(self, string):
        """
        This config parameter specifies a path relative to the chroot that
        should be executed after the chroot is constructed and switched to, in
        order to run the build.
        """
        return string

    @directive("compose", [])
    def compose(self, string):
        """
        This config parameter, which can be specified multiple times, specifies
        other gauntlet repositories whose build results should be placed into
        the chroot before we build. The syntax is a SHA-1 sum which the
        gauntlet server may resolve to either a git repository for another
        gauntlet image or a build result image.
        """
        return self['compose'] + [string]

    @directive("compose-buildonly", [])
    def compose_buildonly(self, string):
        """
        This config parameter is identical to compose, except the files placed
        in the chroot are only there for the build, and are not added to the
        result image or connected to it via a dependency.
        """
        return self['compose-buildonly'] + [string]

    @directive("download-prefix", "gauntlet..")
    def download_prefix(self, string):
        """
        Files in the buildinit folder that begin with the download prefix are
        assumed to be text files containing SHA-1 sums. These are resolved with
        the gauntlet server. If they are raw objects, those objects are copied
        into the buildinit folder before chroot begins, at the same path as the
        file that specified them, minus the download-prefix. If the hash is a
        git commit, the repo is checked out into a folder which bears the name
        of the file that specified the hash, minus the prefix.
        """
        if string == "off":
            return None
        return string

    @directive("file", [])
    def file(self, string):
        """
        A file to be placed into the build root, or a repo to check out. We
        specify a path within the build root and a sha-1.
        """
        path, sha = string.rsplit(None, 1)
        return self['file'] + [(path, sha)]

    @directive("git-hint", [])
    def git_hint(self, string):
        """
        This config parameter lists git repository URLs that we might touch.
        These are relayed to the gauntlet server so it may refresh its indexes.
        """
        return self['git-hint'] + [string]

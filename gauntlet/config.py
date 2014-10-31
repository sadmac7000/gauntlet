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

    @directive("buildinit", "build")
    def buildinit(self, string):
        local = os.path.abspath('.')
        path = os.path.abspath(string)
        prefix = os.path.commonprefix([path, local])

        if not os.path.samefile(prefix, local):
            raise ConfigError("Build init folder must be inside the repo")

        if not os.path.isdir(path):
            raise ConfigError("Build init folder does not exist")

        return path

    @directive("buildinit-rename")
    def buildinit_rename(self, string):
        return string

    @directive("manifest")
    def manifest(self, string):
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
    def landing(self, string):
        return string

    @directive("compose", [])
    def compose(self, string):
        return self['compose'] + [string]

    @directive("compose-buildonly", [])
    def compose_buildonly(self, string):
        return self['compose-buildonly'] + [string]

    @directive("download-prefix", "gauntlet..")
    def download_prefix(self, string):
        if string == "off":
            return None
        return string

    @directive("git-hint", [])
    def git_hint(self, string):
        return self['git-hint'] + [string]

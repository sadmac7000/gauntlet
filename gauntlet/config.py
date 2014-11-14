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
import re
import yaml
from copy import deepcopy

class ConfigError(Exception):
    """
    An exception indicating some sort of error in a configuration. The error
    string should contain more details
    """
    pass

class ComposeCollideError(ConfigError):
    """
    Exception indicating we specified something strange in our compose rules.
    """

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
    def __init__(self, conf = None):
        """
        Initialize a Gauntlet configuration

        conf:
            A configuration file or stream which will be parsed to generate the
            properties in this configuration.
        """

        try:
            conf = conf.read()
        except AttributeError:
            pass

        dict.__init__(self)

        for item in self.__class__.__dict__.values():
            try:
                if item.defaults == None:
                    continue
            except AttributeError:
                continue

            self.__raw_setitem(item.directive_name, deepcopy(item.defaults))

        if conf == None:
            return

        vals = yaml.load(conf)

        for i in vals:
            self[i] = vals[i]

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

        valdict = dict(self.iteritems())

        remove = []

        for key in valdict:
            for methname, meth in self.__class__.__dict__.iteritems():
                if not isinstance(meth, Directive):
                    continue
                if meth.directive_name != key:
                    continue
                if meth.defaults == valdict[key]:
                    remove += [key]
                    break

        for key in remove:
            del valdict[key]
        return yaml.dump(valdict, default_flow_style=False)

class GauntletFile(Config):
    """
    A Gauntlet File configures a single Gauntlet image build. It tells us what
    images to compose and how to build the new content.
    """

    @directive("name")
    def name(self, string):
        return string

    @directive("build-path", "build")
    def build_path(self, string):
        """
        This config parameter specifies where the repo info should be copied to
        inside the build root.
        """
        return string

    @directive("task", "/build.exec")
    def task(self, string):
        """
        This config parameter specifies a path relative to the chroot that
        should be executed after the chroot is constructed and switched to, in
        order to run the build.
        """
        return string

    def compose_handler(self, vals, dirname):
        """
        This is the validator for both the `compose` and `compose-buildonly`
        directives.
        """

        if not isinstance(vals, list):
            raise ConfigError("'{}' directive must be a list".format(dirname))

        for item in vals:
            try:
                if set(item.keys()) != set(['package', 'hash']):
                    raise ConfigError("'{}' directive items must "
                            "have 'package' and 'hash' keys".format(dirname))
            except AttributeError:
                raise ConfigError("'{}' directive must be "
                        "a list of dictionaries".format(dirname))

                if not re.match('^[a-zA-Z0-9]{40}$', item['hash']):
                    raise ConfigError("'{}' directive items must have valid"
                        "SHA-1 hashes".format(dirname))

                if not re.match('^\w+$', item['package']):
                    raise ConfigError("'{}' directive items must have valid"
                        "package names".format(dirname))

        vals = [tuple(x.items()) for x in vals]
        vals = [dict(x) for x in set(vals)]

        packages = [x['package'] for x in vals]
        seen = set()

        for package in packages:
            if package in seen:
                raise ComposeCollideError("Package '{}' listed twice at two "
                    "revisions".format(package))

            seen.add(package)

        hashes = [x['hash'] for x in vals]
        seen = set()

        for a_hash in hashes:
            if a_hash in seen:
                raise ComposeCollideError("Hash '{}' listed twice for two "
                    "packages".format(a_hash))

            seen.add(a_hash)

        return vals

    @directive("compose", [])
    def compose(self, vals):
        """
        This config parameter, which can be specified multiple times, specifies
        other gauntlet repositories whose build results should be placed into
        the chroot before we build. The syntax is a SHA-1 sum which the
        gauntlet server may resolve to either a git repository for another
        gauntlet image or a build result image.
        """

        return self.compose_handler(vals, 'compose')

    @directive("compose-buildonly", [])
    def compose_buildonly(self, vals):
        """
        This config parameter is identical to compose, except the files placed
        in the chroot are only there for the build, and are not added to the
        result image or connected to it via a dependency.
        """

        return self.compose_handler(vals, 'compose-buildonly')

    @directive("files", {})
    def file(self, vals):
        """
        A file to be placed into the build root, or a repo to check out. We
        specify a path within the build root and a SHA-1.
        """
        if not isinstance(vals, dict):
            raise ConfigError("'files' directive must be a dict")

        return vals

    @directive("git-hint", [])
    def git_hint(self, vals):
        """
        This config parameter lists git repository URLs that we might touch.
        These are relayed to the gauntlet server so it may refresh its indexes.
        """
        if not isinstance(vals, list):
            raise ConfigError("'git-hint' directive must be a list")

        return vals

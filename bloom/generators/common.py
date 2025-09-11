# Software License Agreement (BSD License)
#
# Copyright (c) 2013, Willow Garage, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
#  * Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
#  * Redistributions in binary form must reproduce the above
#    copyright notice, this list of conditions and the following
#    disclaimer in the documentation and/or other materials provided
#    with the distribution.
#  * Neither the name of Willow Garage, Inc. nor the names of its
#    contributors may be used to endorse or promote products derived
#    from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

# 强制 rosdep 优先使用 agirosdep 提供的 base.yaml 作为依赖解析来源
# 保留官方 rosdep rules 作为 fallback

from __future__ import print_function

import pkg_resources
import sys
import traceback

from bloom.logging import debug
from bloom.logging import error
from bloom.logging import info

from bloom.rosdistro_api import get_distribution_type
from bloom.rosdistro_api import get_index
from bloom.rosdistro_api import get_python_version
from bloom.rosdistro_api import get_sources_list_url

from bloom.util import code
from bloom.util import maybe_continue
from bloom.util import print_exc

try:
    from rosdep2 import create_default_installer_context
    from rosdep2.catkin_support import get_catkin_view
    from rosdep2.lookup import ResolutionError
    import rosdep2.catkin_support
except ImportError as err:
    debug(traceback.format_exc())
    error("rosdep was not detected, please install it.", exit=True)

BLOOM_GROUP = 'bloom.generators'
DEFAULT_ROS_DISTRO = 'indigo'


def list_generators():
    generators = []
    for entry_point in pkg_resources.iter_entry_points(group=BLOOM_GROUP):
        generators.append(entry_point.name)
    return generators


def load_generator(generator_name):
    for entry_point in pkg_resources.iter_entry_points(group=BLOOM_GROUP):
        if entry_point.name == generator_name:
            return entry_point.load()

view_cache = {}


def get_view(os_name, os_version, ros_distro):
    global view_cache
    key = os_name + os_version + ros_distro
    if key not in view_cache:
        value = get_catkin_view(ros_distro, os_name, os_version, False)
        view_cache[key] = value
    return view_cache[key]


def invalidate_view_cache():
    global view_cache
    view_cache = {}


def update_rosdep():
    info("Running 'rosdep update'...")
    try:
        rosdep2.catkin_support.update_rosdep()
    except:
        print_exc(traceback.format_exc())
        error("Failed to update rosdep, did you run 'rosdep init' first?",
              exit=True)


# === 新增：AGIROS rosdep installer context ===
def create_agiros_installer_context():
    """
    创建一个 rosdep installer context，
    在默认规则之前强制插入 agirosdep 的 base.yaml。
    """
    ctx = create_default_installer_context()

    agiros_source = {
        'type': 'yaml',
        'url': get_sources_list_url(),
        'tags': ['base'],
    }

    # 插入到最前，保证优先级
    ctx.rosdep_sources_list = {
        'agiros': agiros_source,
        **ctx.rosdep_sources_list
    }
    info("Using agirosdep as primary rosdep source: {0}".format(agiros_source['url']))
    return ctx


def resolve_more_for_os(rosdep_key, view, installer, os_name, os_version):
    d = view.lookup(rosdep_key)
    ctx = create_agiros_installer_context()
    os_installers = ctx.get_os_installer_keys(os_name)
    default_os_installer = ctx.get_default_os_installer_key(os_name)
    inst_key, rule = d.get_rule_for_platform(os_name, os_version,
                                             os_installers,
                                             default_os_installer)
    assert inst_key in os_installers
    return installer.resolve(rule), inst_key, default_os_installer


def package_conditional_context(ros_distro):
    if get_index().version < 4:
        error("Bloom requires a version 4 or greater rosdistro index to support package format 3.", exit=True)

    distribution_type = get_distribution_type(ros_distro)
    if distribution_type == 'ros1':
        ros_version = '1'
    elif distribution_type == 'ros2':
        ros_version = '2'
    else:
        error("Bloom cannot cope with distribution_type '{0}'".format(
            distribution_type), exit=True)
    python_version = get_python_version(ros_distro)
    if python_version is None:
        error(
            'No python_version found in the rosdistro index. '
            'The rosdistro index must include this key for bloom to work correctly.',
            exit=True)
    elif python_version == 2:
        ros_python_version = '2'
    elif python_version == 3:
        ros_python_version = '3'
    else:
        error("Bloom cannot cope with python_version '{0}'".format(
            python_version), exit=True)

    return {
            'ROS_VERSION': ros_version,
            'ROS_DISTRO': ros_distro,
            'ROS_PYTHON_VERSION': ros_python_version,
            }


def evaluate_package_conditions(package, ros_distro):
    if package.package_format >= 3:
        package.evaluate_conditions(package_conditional_context(ros_distro))


def resolve_rosdep_key(
    key,
    os_name,
    os_version,
    ros_distro=None,
    ignored=None,
    retry=True
):
    ignored = ignored or []
    ctx = create_agiros_installer_context()
    try:
        installer_key = ctx.get_default_os_installer_key(os_name)
    except KeyError:
        BloomGenerator.exit("Could not determine the installer for '{0}'"
                            .format(os_name))
    installer = ctx.get_installer(installer_key)
    ros_distro = ros_distro or DEFAULT_ROS_DISTRO
    view = get_view(os_name, os_version, ros_distro)
    try:
        return resolve_more_for_os(key, view, installer, os_name, os_version)
    except (KeyError, ResolutionError) as exc:
        debug(traceback.format_exc())
        if key in ignored:
            return None, None, None
        if isinstance(exc, KeyError):
            error("'{0}'".format(key))
            returncode = code.GENERATOR_NO_SUCH_ROSDEP_KEY
        else:
            error("Could not resolve rosdep key '{0}' for distro '{1}':"
                  .format(key, os_version))
            info(str(exc), use_prefix=False)
            returncode = code.GENERATOR_NO_ROSDEP_KEY_FOR_DISTRO
        if retry:
            error("Try to resolve the problem with rosdep and then continue.")
            if maybe_continue():
                update_rosdep()
                invalidate_view_cache()
                return resolve_rosdep_key(key, os_name, os_version, ros_distro,
                                          ignored, retry=True)
        BloomGenerator.exit("Failed to resolve rosdep key '{0}', aborting."
                            .format(key), returncode=returncode)


def default_fallback_resolver(key, peer_packages):
    BloomGenerator.exit("Failed to resolve rosdep key '{0}', aborting."
                        .format(key), returncode=code.GENERATOR_NO_SUCH_ROSDEP_KEY)


def resolve_dependencies(
    keys,
    os_name,
    os_version,
    ros_distro=None,
    peer_packages=None,
    fallback_resolver=None
):
    ros_distro = ros_distro or DEFAULT_ROS_DISTRO
    peer_packages = peer_packages or []
    fallback_resolver = fallback_resolver or default_fallback_resolver

    resolved_keys = {}
    keys = [k.name for k in keys]
    for key in keys:
        resolved_key, installer_key, default_installer_key = \
            resolve_rosdep_key(key, os_name, os_version, ros_distro,
                               peer_packages, retry=True)
        if resolved_key is None:
            resolved_key = fallback_resolver(key, peer_packages)
        resolved_keys[key] = resolved_key
    return resolved_keys


class GeneratorError(Exception):
    def __init__(self, msg, returncode=code.UNKNOWN):
        super(GeneratorError, self).__init__("Error running generator: " + msg)
        self.returncode = returncode

    @staticmethod
    def excepthook(etype, value, traceback):
        GeneratorError.sysexcepthook(etype, value, traceback)
        if isinstance(value, GeneratorError):
            sys.exit(value.returncode)

    sys.excepthook, sysexcepthook = excepthook.__func__, staticmethod(sys.excepthook)


class BloomGenerator(object):
    generator_type = None
    title = 'no title'
    description = None
    help = None

    @classmethod
    def exit(cls, msg, returncode=code.UNKNOWN):
        raise GeneratorError(msg, returncode)

    def prepare_arguments(self, parser):
        pass

    def handle_arguments(self, args):
        debug("BloomGenerator.handle_arguments: got args -> " + str(args))

    def summarize(self):
        info("Running " + self.title + " generator")

    def get_branching_arguments(self):
        return []

    def pre_modify(self):
        return 0

    def pre_branch(self, destination, source):
        return 0

    def post_branch(self, destination, source):
        return 0

    def pre_export_patches(self, branch_name):
        return 0

    def post_export_patches(self, branch_name):
        return 0

    def pre_rebase(self, branch_name):
        return 0

    def post_rebase(self, branch_name):
        return 0

    def pre_patch(self, branch_name):
        return 0

    def post_patch(self, branch_name):
        return 0

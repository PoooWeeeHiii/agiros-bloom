# Software License Agreement (BSD License)
#
# Copyright (c) 2025, AGIROS Maintainers
# All rights reserved.
#
# (License header adapted from OSRF's bloom)

from __future__ import print_function

from bloom.generators.common import default_fallback_resolver
from bloom.generators.debian import DebianGenerator
from bloom.generators.debian.generator import generate_substitutions_from_package
from bloom.generators.debian.generate_cmd import main as debian_main
from bloom.generators.debian.generate_cmd import prepare_arguments

from bloom.logging import info
from bloom.rosdistro_api import get_index, get_sources_list_url
import os


def agirosify_package_name(name, rosdistro):
    """
    Applies the AGIROS package naming convention.
    Rule: agiros-<distro>-<package_name>
    """
    # Sanitize the base name by removing potential old prefixes from other ecosystems
    name = name.replace('ros-' + rosdistro + '-', '')
    # Replace underscores with hyphens for Debian compatibility
    name = name.replace('_', '-')
    # Apply the AGIROS naming convention with the corrected prefix
    return 'agiros-{0}-{1}'.format(rosdistro, name)


class AgirosDebianGenerator(DebianGenerator):
    # Rule 6: Set the generator title
    title = 'agirosdebian'
    description = "Generates debians tailored for the AGIROS rosdistro"
    # Rule 2: Set the default installation prefix
    default_install_prefix = '/opt/agiros/'
    def __init__(self, *args, **kwargs):
        super(AgirosDebianGenerator, self).__init__(*args, **kwargs)
        self.template_dir = os.path.join(os.path.dirname(__file__), 'templates')

    def __init__(self, *args, **kwargs):
        super(AgirosDebianGenerator, self).__init__(*args, **kwargs)
        # 自动获取 AGIROS sources.list.d/base.yaml 的 URL
        self.agiros_sources_list_url = get_sources_list_url()

    def prepare_arguments(self, parser):
        # Add command line arguments for this generator
        add = parser.add_argument
        add('rosdistro', help="AGIROS distro to target (e.g., loong)")
        return DebianGenerator.prepare_arguments(self, parser)

    def handle_arguments(self, args):
        self.rosdistro = args.rosdistro
        # Append the distro name to the installation prefix
        self.default_install_prefix += self.rosdistro
        ret = DebianGenerator.handle_arguments(self, args)
        return ret

    def summarize(self):
        ret = DebianGenerator.summarize(self)
        info("Releasing for AGIROS distro: " + self.rosdistro)
        return ret

    def get_subs(self, package, debian_distro, releaser_history, deb_inc=0, native=False):
        def fallback_resolver(key, peer_packages, rosdistro=self.rosdistro):
            if key in peer_packages:
                return [agirosify_package_name(key, rosdistro)]
            return default_fallback_resolver(key, peer_packages)

        subs = generate_substitutions_from_package(
            package, self.os_name, debian_distro, self.rosdistro,
            self.install_prefix, self.debian_inc,
            [p.name for p in self.packages.values()],
            releaser_history=releaser_history,
            fallback_resolver=fallback_resolver,
            native=native
        )

        subs['Rosdistro'] = self.rosdistro
        # Rule 1: Apply AGIROS naming to the main package
        subs['Package'] = agirosify_package_name(package.name, self.rosdistro)

        # Rule 3: Add core AGIROS workspace dependency
        if package.name not in ['ament_cmake_core', 'ament_package', 'ros_workspace']:
            workspace_pkg_name = agirosify_package_name('ros-workspace', self.rosdistro)
            subs['BuildDepends'].append(workspace_pkg_name)
            subs['Depends'].append(workspace_pkg_name)

        # Rule 4: Add special dependencies for specific package groups
        ros2_distros = [
            name for name, values in get_index().distributions.items()
            if values.get('distribution_type') == 'ros2']
        if self.rosdistro in ros2_distros:
            if 'rosidl_interface_packages' in package.member_of_groups:
                INTERFACE_DEPENDENCIES = [
                    'rosidl-typesupport-fastrtps-c',
                    'rosidl-typesupport-fastrtps-cpp',
                ]
                agiros_deps = [
                    agirosify_package_name(name, self.rosdistro) for name in INTERFACE_DEPENDENCIES
                ]
                subs['BuildDepends'] += agiros_deps
        # === AGIROS Customizations End Here ===
        return subs

    def generate_branching_arguments(self, package, branch):
        # Rule 5 (Branches)
        deb_branch = 'debian/' + self.rosdistro + '/' + package.name
        args = [[deb_branch, branch, False]]
        n, r, b, ds = package.name, self.rosdistro, deb_branch, self.distros
        args.extend([['debian/' + r + '/' + d + '/' + n, b, False] for d in ds])
        return args

    def get_release_tag(self, data):
        # Rule 5 (Tags)
        return 'release/{0}/{1}/{2}-{3}'.format(
            self.rosdistro, data['Name'], data['Version'], self.debian_inc)


def get_subs(pkg, os_name, os_version, ros_distro, deb_inc, native):
    """Standalone get_subs function for the command-line entry point."""
    subs = generate_substitutions_from_package(
        pkg, os_name, os_version, ros_distro,
        AgirosDebianGenerator.default_install_prefix + ros_distro,
        deb_inc=deb_inc,
        native=native
    )
    # Apply AGIROS naming convention
    subs['Package'] = agirosify_package_name(subs['Package'], ros_distro)
    return subs


def main(args=None):
    """Main function for the 'rosdebian' command, adapted for AGIROS."""
    # Note: debian_main is imported from the original bloom generator
    debian_main(args, get_subs)


# This dictionary describes this command to the bloom loader
description = dict(
    title='agirosdebian',
    description="Generates AGIROS style debian packaging files",
    main=main,
    prepare_arguments=prepare_arguments
)


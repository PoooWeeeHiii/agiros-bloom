# bloom/generators/agirosrpm.py
from __future__ import print_function

from bloom.generators.common import default_fallback_resolver
from bloom.generators.rpm import RpmGenerator
from bloom.generators.rpm.generator import sanitize_package_name
from bloom.generators.rpm.generator import generate_substitutions_from_package
from bloom.generators.rpm.generate_cmd import main as rpm_main
from bloom.generators.rpm.generate_cmd import prepare_arguments

from bloom.logging import info
from bloom.rosdistro_api import get_index

def agirosify_package_name(name, rosdistro):
    """
    Applies the AGIROS package naming convention.
    Rule: agiros-<distro>-<package_name>
    """
    # Remove any existing ROS distro prefix to avoid duplication
    name = name.replace('ros-' + rosdistro + '-', '')
    # Replace underscores with hyphens for RPM naming
    name = name.replace('_', '-')
    # Prepend the AGIROS prefix
    return 'agiros-{0}-{1}'.format(rosdistro, name)

class AgirosRpmGenerator(RpmGenerator):
    title = 'agirosrpm'
    description = "Generates RPMs tailored for the AGIROS rosdistro"
    default_install_prefix = '/opt/agiros/'
    
    def prepare_arguments(self, parser):
        # Add command-line argument for AGIROS distro (e.g., 'loong')
        add = parser.add_argument
        add('rosdistro', help="AGIROS distro to target (e.g., loong)")
        return RpmGenerator.prepare_arguments(self, parser)
    
    def handle_arguments(self, args):
        self.rosdistro = args.rosdistro
        # Append distro name to installation prefix (e.g., /opt/agiros/loong)
        self.default_install_prefix += self.rosdistro
        return RpmGenerator.handle_arguments(self, args)
    
    def summarize(self):
        ret = RpmGenerator.summarize(self)
        info("Releasing for AGIROS distro: " + self.rosdistro)
        return ret

    def get_subs(self, package, rpm_distro, releaser_history):
        # Custom fallback: map peer package dependencies using AGIROS naming
        def fallback_resolver(key, peer_packages, rosdistro=self.rosdistro):
            if key in peer_packages:
                return [sanitize_package_name(agirosify_package_name(key, rosdistro))]
            return default_fallback_resolver(key, peer_packages)
        # Generate base substitutions using the parent logic
        subs = generate_substitutions_from_package(
            package,
            self.os_name,
            rpm_distro,
            self.rosdistro,
            self.install_prefix,
            self.rpm_inc,
            [p.name for p in self.packages.values()],
            releaser_history=releaser_history,
            fallback_resolver=fallback_resolver,
            skip_keys=self.skip_keys
        )
        # Record the ROS distro in substitutions
        subs['Rosdistro'] = self.rosdistro
        # Apply AGIROS naming to the main package name
        subs['Package'] = agirosify_package_name(package.name, self.rosdistro)
        # Ensure the main package provides common subpackages (devel, doc, runtime)
        subs['Provides'] += [
            '%%{name}-%s = %%{version}-%%{release}' % subpkg 
            for subpkg in ['devel', 'doc', 'runtime']
        ]
        # Represent group membership in RPM metadata (as in original rosrpm)
        subs['Provides'].extend(
            sanitize_package_name(agirosify_package_name(g.name, self.rosdistro)) + '(member)'
            for g in package.member_of_groups
        )
        subs['Supplements'].extend(
            sanitize_package_name(agirosify_package_name(g.name, self.rosdistro)) + '(all)'
            for g in package.member_of_groups
        )
        # Add AGIROS core workspace dependency to all non-core packages
        if package.name not in ['ament_cmake_core', 'ament_package', 'ros_workspace']:
            ws_pkg = agirosify_package_name('ros-workspace', self.rosdistro)
            subs['BuildDepends'].append(ws_pkg)
            subs['Depends'].append(ws_pkg)
        # For ROS 2 distributions, add FastRTPS dependencies for interface packages
        ros2_distros = [
            name for name, distro in get_index().distributions.items()
            if distro.get('distribution_type') == 'ros2'
        ]
        if self.rosdistro in ros2_distros:
            if 'rosidl_interface_packages' in package.member_of_groups:
                fast_rtps_pkgs = [
                    agirosify_package_name('rosidl-typesupport-fastrtps-c', self.rosdistro),
                    agirosify_package_name('rosidl-typesupport-fastrtps-cpp', self.rosdistro)
                ]
                subs['BuildDepends'] += fast_rtps_pkgs
        return subs

    def generate_branching_arguments(self, package, branch):
        # Use 'rpm/<rosdistro>/<pkg>' as base branch and then one per target RPM distro
        rpm_branch = 'rpm/' + self.rosdistro + '/' + package.name
        args = [[rpm_branch, branch, False]]
        n, r, b, ds = package.name, self.rosdistro, rpm_branch, self.distros
        args.extend([['rpm/' + r + '/' + d + '/' + n, b, False] for d in ds])
        return args

    def get_release_tag(self, data):
        # Include distro name and RPM increment in the release tag
        return 'release/{0}/{1}/{2}-{3}'.format(
            self.rosdistro, data['Name'], data['Version'], self.rpm_inc)

# Standalone get_subs for command-line entry point
def get_subs(pkg, os_name, os_version, ros_distro):
    subs = generate_substitutions_from_package(
        pkg,
        os_name,
        os_version,
        ros_distro,
        AgirosRpmGenerator.default_install_prefix + ros_distro
    )
    subs['Package'] = agirosify_package_name(subs['Package'], ros_distro)
    return subs

def main(args=None):
    rpm_main(args, get_subs)

# Describe this generator to Bloom's loader
description = dict(
    title='agirosrpm',
    description="Generates AGIROS style RPM packaging files",
    main=main,
    prepare_arguments=prepare_arguments
)

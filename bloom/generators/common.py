import pkg_resources
import sys
import traceback
import subprocess

from bloom.logging import debug, error, info
from bloom.rosdistro_api import (
    get_distribution_type,
    get_index,
    get_python_version,
    get_sources_list_url,
)
from bloom.util import code, maybe_continue, print_exc

try:
    from rosdep2.catkin_support import get_catkin_view
    from rosdep2.lookup import ResolutionError
    import rosdep2.catkin_support
except ImportError:
    debug(traceback.format_exc())
    error("rosdep was not detected, please install it.", exit=True)

BLOOM_GROUP = "bloom.generators"
DEFAULT_ROS_DISTRO = "loong"

# 缓存 agirosdep resolve 结果，加速重复调用
_resolve_cache = {}
view_cache = {}


def list_generators():
    generators = []
    for entry_point in pkg_resources.iter_entry_points(group=BLOOM_GROUP):
        generators.append(entry_point.name)
    return generators


def load_generator(generator_name):
    for entry_point in pkg_resources.iter_entry_points(group=BLOOM_GROUP):
        if entry_point.name == generator_name:
            return entry_point.load()


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
    info("Running 'agirosdep update'...")
    try:
        subprocess.check_call(["agirosdep", "update"])
    except subprocess.CalledProcessError:
        print_exc(traceback.format_exc())
        error("Failed to update agirosdep (check your sources.list.d), aborting.", exit=True)


def package_conditional_context(ros_distro):
    if get_index().version < 4:
        error(
            "Bloom requires a version 4 or greater rosdistro index to support package format 3.",
            exit=True,
        )

    distribution_type = get_distribution_type(ros_distro)
    if distribution_type == "ros1":
        ros_version = "1"
    elif distribution_type == "ros2":
        ros_version = "2"
    else:
        error(f"Bloom cannot cope with distribution_type '{distribution_type}'", exit=True)

    python_version = get_python_version(ros_distro)
    if python_version is None:
        error(
            "No python_version found in the rosdistro index. The rosdistro index must include this key.",
            exit=True,
        )
    elif python_version == 2:
        ros_python_version = "2"
    elif python_version == 3:
        ros_python_version = "3"
    else:
        error(f"Bloom cannot cope with python_version '{python_version}'", exit=True)

    return {
        "ROS_VERSION": ros_version,
        "ROS_DISTRO": ros_distro,
        "ROS_PYTHON_VERSION": ros_python_version,
    }


def evaluate_package_conditions(package, ros_distro):
    if package.package_format >= 3:
        package.evaluate_conditions(package_conditional_context(ros_distro))


def _guess_installer_for_os(os_name: str) -> str:
    os_name = (os_name or "").lower()
    if os_name in ("ubuntu", "debian"):
        return "apt"
    if os_name in ("fedora", "rhel", "centos", "openeuler", "rocky", "almalinux", "amazon"):
        return "dnf"  # 或者 "yum"，取决于 agirosdep 输出
    return "apt"


def resolve_rosdep_key(
    key,
    os_name,
    os_version,
    ros_distro=None,
    ignored=None,
    retry=True,
):
    ignored = ignored or []
    ros_distro = ros_distro or DEFAULT_ROS_DISTRO
    cache_key = (key, os_name, os_version, ros_distro)

    if cache_key in _resolve_cache:
        return _resolve_cache[cache_key]

    try:
        cmd = [
            "agirosdep",
            "resolve",
            key,
            "--rosdistro",
            ros_distro,
            "--os",
            f"{os_name}:{os_version}",
        ]
        debug("Running: " + " ".join(cmd))
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        lines = out.decode("utf-8", "ignore").splitlines()

        pkgs = []
        for line in lines:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if s.startswith("agiros-"):
                pkgs.append(s)

        if not pkgs:
            raise KeyError(
                f"No agirosdep rule for {key} on {os_name}:{os_version} (distro={ros_distro})"
            )

        installer_key = _guess_installer_for_os(os_name)
        result = (pkgs, installer_key, installer_key)
        _resolve_cache[cache_key] = result
        return result

    except subprocess.CalledProcessError as exc:
        debug(traceback.format_exc())
        if key in ignored:
            return None, None, None
        error(f"Could not resolve rosdep key '{key}' via agirosdep.")
        info(exc.output.decode("utf-8", "ignore"), use_prefix=False)

        if retry:
            error("Try to resolve the problem with agirosdep and then continue.")
            if maybe_continue():
                update_rosdep()
                invalidate_view_cache()
                return resolve_rosdep_key(
                    key, os_name, os_version, ros_distro, ignored, retry=True
                )

        BloomGenerator.exit(
            f"Failed to resolve rosdep key '{key}', aborting.",
            returncode=code.GENERATOR_NO_SUCH_ROSDEP_KEY,
        )


def default_fallback_resolver(key, peer_packages):
    BloomGenerator.exit(
        f"Failed to resolve rosdep key '{key}', aborting.",
        returncode=code.GENERATOR_NO_SUCH_ROSDEP_KEY,
    )


def resolve_dependencies(
    keys, os_name, os_version, ros_distro=None, peer_packages=None, fallback_resolver=None
):
    ros_distro = ros_distro or DEFAULT_ROS_DISTRO
    peer_packages = peer_packages or []
    fallback_resolver = fallback_resolver or default_fallback_resolver

    resolved_keys = {}
    keys = [k.name for k in keys]
    for key in keys:
        resolved_key, installer_key, default_installer_key = resolve_rosdep_key(
            key, os_name, os_version, ros_distro, peer_packages, retry=True
        )
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
    title = "no title"
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

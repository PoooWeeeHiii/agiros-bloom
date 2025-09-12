import pkg_resources
import sys
import traceback
import subprocess

from bloom.logging import debug, error, info
from bloom.rosdistro_api import get_distribution_type, get_index, get_python_version, get_sources_list_url
from bloom.util import code, maybe_continue, print_exc

try:
    from rosdep2 import create_default_installer_context
    from rosdep2.catkin_support import get_catkin_view
    from rosdep2.lookup import ResolutionError
    import rosdep2.catkin_support
except ImportError:
    debug(traceback.format_exc())
    error("rosdep was not detected, please install it.", exit=True)

BLOOM_GROUP = 'bloom.generators'
DEFAULT_ROS_DISTRO = 'loong'


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
    except Exception:
        print_exc(traceback.format_exc())
        error("Failed to update rosdep, did you run 'rosdep init' first?", exit=True)


# AGIROS 强制使用 agirosdep base.yaml
def create_agiros_installer_context():
    ctx = create_default_installer_context()
    agiros_url = get_sources_list_url()
    info(f"Using AGIROS base.yaml: {agiros_url}")
    ctx.rosdep_sources_list = {
        "agiros": {
            "type": "yaml",
            "url": agiros_url,
            "tags": ["base"],
        }
    }
    return ctx


def package_conditional_context(ros_distro):
    if get_index().version < 4:
        error("Bloom requires a version 4 or greater rosdistro index to support package format 3.", exit=True)

    distribution_type = get_distribution_type(ros_distro)
    if distribution_type == 'ros1':
        ros_version = '1'
    elif distribution_type == 'ros2':
        ros_version = '2'
    else:
        error(f"Bloom cannot cope with distribution_type '{distribution_type}'", exit=True)

    python_version = get_python_version(ros_distro)
    if python_version is None:
        error('No python_version found in the rosdistro index. The rosdistro index must include this key.', exit=True)
    elif python_version == 2:
        ros_python_version = '2'
    elif python_version == 3:
        ros_python_version = '3'
    else:
        error(f"Bloom cannot cope with python_version '{python_version}'", exit=True)

    return {
        'ROS_VERSION': ros_version,
        'ROS_DISTRO': ros_distro,
        'ROS_PYTHON_VERSION': ros_python_version,
    }


def evaluate_package_conditions(package, ros_distro):
    if package.package_format >= 3:
        package.evaluate_conditions(package_conditional_context(ros_distro))


# === 改造版：直接调用 agirosdep resolve ===
def resolve_rosdep_key(key, os_name, os_version, ros_distro=None, ignored=None, retry=True):
    ignored = ignored or []
    ros_distro = ros_distro or DEFAULT_ROS_DISTRO

    try:
        cmd = [
            "agirosdep", "resolve", key,
            "--rosdistro", ros_distro,
            "--os", f"{os_name}:{os_version}"
        ]
        debug("Running: " + " ".join(cmd))
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        lines = out.decode("utf-8").strip().splitlines()
        pkgs = []
        for line in lines:
            if line.startswith("agiros-"):
                pkgs.append(line.strip())
        if not pkgs:
            raise KeyError(f"No agirosdep rule for {key}")
        return pkgs, "apt", "apt"
    except subprocess.CalledProcessError as e:
        debug(traceback.format_exc())
        if key in ignored:
            return None, None, None
        error(f"Could not resolve rosdep key '{key}' via agirosdep")
        info(e.output.decode("utf-8"), use_prefix=False)
        if retry and maybe_continue():
            return resolve_rosdep_key(key, os_name, os_version, ros_distro, ignored, retry)
        BloomGenerator.exit(f"Failed to resolve rosdep key '{key}', aborting.", returncode=code.GENERATOR_NO_SUCH_ROSDEP_KEY)


def default_fallback_resolver(key, peer_packages):
    BloomGenerator.exit(f"Failed to resolve rosdep key '{key}', aborting.", returncode=code.GENERATOR_NO_SUCH_ROSDEP_KEY)


def resolve_dependencies(keys, os_name, os_version, ros_distro=None, peer_packages=None, fallback_resolver=None):
    ros_distro = ros_distro or DEFAULT_ROS_DISTRO
    peer_packages = peer_packages or []
    fallback_resolver = fallback_resolver or default_fallback_resolver

    resolved_keys = {}
    keys = [k.name for k in keys]
    for key in keys:
        resolved_key, installer_key, default_installer_key = resolve_rosdep_key(key, os_name, os_version, ros_distro, peer_packages, retry=True)
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

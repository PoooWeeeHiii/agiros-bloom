# Copyright 2025 AGIROS Maintainers
# Licensed under the BSD License
#
# 移除了 ROS 官方 rosdep 源的逻辑
# 强制只使用 agirosdep 的 base.yaml


import traceback

from bloom.logging import debug, error, info
from bloom.rosdistro_api import get_sources_list_url
from bloom.util import code, maybe_continue, print_exc

try:
    from rosdep2 import create_default_installer_context
    from rosdep2.catkin_support import get_catkin_view, update_rosdep
    from rosdep2.lookup import ResolutionError
except ImportError:
    error("rosdep was not detected, please install it.", exit=True)

DEFAULT_ROS_DISTRO = "loong"
view_cache = {}


def create_agiros_installer_context():
    """
    创建 agirosdep 的 installer context，只加载 agirosdep base.yaml。
    """
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


def get_view(os_name, os_version, ros_distro):
    key = os_name + os_version + ros_distro
    if key not in view_cache:
        value = get_catkin_view(ros_distro, os_name, os_version, False)
        view_cache[key] = value
    return view_cache[key]


def invalidate_view_cache():
    global view_cache
    view_cache = {}


def resolve_more_for_os(rosdep_key, view, installer, os_name, os_version):
    """
    从 agirosdep 的 rules 解析依赖 key。
    """
    d = view.lookup(rosdep_key)
    ctx = create_agiros_installer_context()
    os_installers = ctx.get_os_installer_keys(os_name)
    default_os_installer = ctx.get_default_os_installer_key(os_name)
    inst_key, rule = d.get_rule_for_platform(
        os_name, os_version, os_installers, default_os_installer
    )
    assert inst_key in os_installers
    return installer.resolve(rule), inst_key, default_os_installer


def resolve_rosdep_key(
    key, os_name, os_version, ros_distro=None, ignored=None, retry=True
):
    ignored = ignored or []
    ctx = create_agiros_installer_context()
    try:
        installer_key = ctx.get_default_os_installer_key(os_name)
    except KeyError:
        error(f"Could not determine the installer for '{os_name}'", exit=True)

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
            error(f"Could not resolve rosdep key '{key}'")
            returncode = code.GENERATOR_NO_SUCH_ROSDEP_KEY
        else:
            error(f"Could not resolve rosdep key '{key}' for distro '{os_version}':")
            info(str(exc), use_prefix=False)
            returncode = code.GENERATOR_NO_ROSDEP_KEY_FOR_DISTRO

        if retry:
            error("Try to resolve the problem with agirosdep and then continue.")
            if maybe_continue():
                update_rosdep()
                invalidate_view_cache()
                return resolve_rosdep_key(
                    key, os_name, os_version, ros_distro, ignored, retry=True
                )

        error(f"Failed to resolve rosdep key '{key}', aborting.", exit=True)

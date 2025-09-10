# -*- coding: utf-8 -*-

import unittest
from unittest.mock import MagicMock, patch

# 这是一个独立的单元测试脚本，用于验证您定制的 agirosdebian.py 的核心逻辑。
# 它通过模拟一个ROS软件包和bloom的运行环境，来检查每一条AGIROS规范是否被正确实现。

# 动态导入被测试的模块
try:
    from bloom.generators.agirosdebian import AgirosDebianGenerator, agirosify_package_name
except ImportError:
    print("错误: 无法导入 'bloom.generators.agirosdebian'。")
    print("请确保:")
    print("1. 正从项目的根目录运行此脚本。")
    print("2. 已经以 '可编辑模式' (pip install -e .) 安装了bloom项目。")
    print("3. 'agirosdebian.py' 文件位于 'bloom/generators/' 目录下。")
    import sys
    sys.exit(1)


# 创建一些虚拟对象来模拟真实的ROS包，避免需要读取真实文件。
class MockMaintainer:
    def __init__(self, name='Mock Maintainer', email='mock@agiros.org'):
        self.name = name
        self.email = email

    def __str__(self):
        return f"{self.name} <{self.email}>"


class MockPackage:
    def __init__(self, name, version='1.2.3', member_of_groups=None):
        self.name = name
        self.version = version
        self.member_of_groups = member_of_groups or []
        # 添加其他必要的属性以模拟真实的package对象
        self.description = "A mock package for testing."
        self.maintainers = [MockMaintainer()]
        self.licenses = ['Apache-2.0']
        self.urls = []
        self.run_depends = []
        self.buildtool_export_depends = []
        self.build_depends = []
        self.buildtool_depends = []
        self.test_depends = []
        self.replaces = []
        self.conflicts = []
        self.exports = []


class TestAgirosDebianGenerator(unittest.TestCase):
    """
    为 AgirosDebianGenerator 编写的单元测试。
    """

    def setUp(self):
        """在每个测试用例前，创建一个干净的生成器实例。"""
        self.generator = AgirosDebianGenerator()
        # 模拟 handle_arguments 方法被调用后的状态
        self.generator.rosdistro = 'loong'
        self.generator.os_name = 'ubuntu'
        self.generator.debian_inc = '0'
        self.generator.install_prefix = self.generator.default_install_prefix + self.generator.rosdistro
        self.generator.packages = {'my_awesome_pkg': MockPackage('my_awesome_pkg')}
        self.generator.distros = ['noble']

    def test_rule1_package_naming_convention(self):
        """测试规则1: 软件包命名规范 (agiros-<distro>-<pkg>)"""
        print("\n---> 1. 测试软件包命名...")
        original_name = 'my_robot_driver'
        rosdistro = 'loong'
        # 更新: 预期结果现在是 'agiros-' 前缀
        expected_name = 'agiros-loong-my-robot-driver'
        result_name = agirosify_package_name(original_name, rosdistro)
        self.assertEqual(result_name, expected_name)
        print(f"     成功: '{original_name}' -> '{result_name}'")

    def test_rule2_default_install_prefix(self):
        """测试规则2: 默认安装路径 (/opt/agiros/<distro>/)"""
        print("\n---> 2. 测试默认安装路径...")
        expected_prefix = '/opt/agiros/loong'
        self.assertEqual(self.generator.install_prefix, expected_prefix)
        print(f"     成功: 安装路径为 '{self.generator.install_prefix}'")

    @patch('bloom.generators.agirosdebian.generate_substitutions_from_package')
    def test_rule3_core_dependency_injection(self, mock_generate_subs):
        """测试规则3: 核心基础依赖注入 (agiros-loong-ros-workspace)"""
        print("\n---> 3. 测试核心依赖注入...")
        mock_generate_subs.return_value = {
            'Package': 'my_awesome_pkg', 'BuildDepends': [], 'Depends': []
        }
        
        pkg = MockPackage('my_awesome_pkg')
        subs = self.generator.get_subs(pkg, 'noble', {})
        # 更新: 预期结果现在是 'agiros-' 前缀
        workspace_dep = 'agiros-loong-ros-workspace'
        self.assertIn(workspace_dep, subs['BuildDepends'])
        self.assertIn(workspace_dep, subs['Depends'])
        print(f"     成功: 普通软件包自动添加了 '{workspace_dep}' 依赖")

    @patch('bloom.generators.agirosdebian.get_index')
    @patch('bloom.generators.agirosdebian.generate_substitutions_from_package')
    def test_rule4_special_group_dependencies(self, mock_generate_subs, mock_get_index):
        """测试规则4: 特殊包组依赖 (rosidl_interface_packages)"""
        print("\n---> 4. 测试特殊包组依赖注入...")
        mock_index_distributions = {'loong': {'distribution_type': 'ros2'}}
        mock_get_index.return_value.distributions = mock_index_distributions
        mock_generate_subs.return_value = {'Package': 'my_interface_pkg', 'BuildDepends': [], 'Depends': []}

        interface_pkg = MockPackage('my_interface_pkg', member_of_groups=['rosidl_interface_packages'])
        subs = self.generator.get_subs(interface_pkg, 'noble', {})
        # 更新: 预期结果现在是 'agiros-' 前缀
        expected_dep = 'agiros-loong-rosidl-typesupport-fastrtps-c'
        self.assertIn(expected_dep, subs['BuildDepends'])
        print(f"     成功: 接口包自动添加了 '{expected_dep}' 等依赖")

    def test_rule5_git_naming_scheme(self):
        """测试规则5: Git分支与标签命名规则"""
        print("\n---> 5. 测试Git命名规则...")
        pkg = MockPackage('my_awesome_pkg', version='1.2.3')
        
        branch_args = self.generator.generate_branching_arguments(pkg, 'upstream')
        expected_branch = 'debian/loong/my_awesome_pkg'
        self.assertEqual(branch_args[0][0], expected_branch)
        print(f"     成功: 生成的分支名为 '{expected_branch}'")
        
        mock_data = {'Name': pkg.name, 'Version': pkg.version}
        tag_name = self.generator.get_release_tag(mock_data)
        # 注意: 标签名本身不包含 'agiros-' 前缀，是根据原始包名生成的，所以这里不需要改动
        expected_tag = 'release/loong/my_awesome_pkg/1.2.3-0'
        self.assertEqual(tag_name, expected_tag)
        print(f"     成功: 生成的标签名为 '{expected_tag}'")
        
    def test_rule6_generator_title(self):
        """测试规则6: 生成器名称"""
        print("\n---> 6. 测试生成器名称...")
        expected_title = 'agirosdebian'
        self.assertEqual(self.generator.title, expected_title)
        print(f"     成功: 生成器名称为 '{self.generator.title}'")


if __name__ == '__main__':
    print("=" * 70)
    print("开始测试 'agirosdebian.py' (使用 agiros- 前缀规范)...")
    print("=" * 70)
    unittest.main(verbosity=0)
    print("\n" + "=" * 70)
    print("所有测试完成。")
    print("=" * 70)


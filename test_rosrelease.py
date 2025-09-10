# -*- coding: utf-8 -*-

import unittest
import argparse
import sys
from io import StringIO


try:
    # 导入我们想要测试的目标类
    from bloom.generators.rosrelease import RosReleaseGenerator
except ImportError:
    print("错误: 无法导入 'bloom.generators.rosrelease'。")
    print("请确保:")
    print("1. 正从项目的根目录运行此脚本。")
    print("2. 已经以 '可编辑模式' (pip install -e .) 安装了bloom项目。")
    sys.exit(1)


class TestRosReleaseGenerator(unittest.TestCase):
    """
    为优化后的 RosReleaseGenerator 编写的单元测试。
    """

    def setUp(self):
        """
        在每个测试用例运行前，设置一个干净的 ArgumentParser 和生成器实例。
        """
        self.parser = argparse.ArgumentParser()
        self.generator = RosReleaseGenerator()
        
        # <<< 核心修复 >>>
        # 手动添加 'interactive' 参数，模拟 bloom 主程序添加的全局参数。
        # 这是解决 AttributeError 的关键。
        self.parser.add_argument('--interactive', action='store_true', default=True)
        
        # 让生成器准备好它自己的参数定义
        self.generator.prepare_arguments(self.parser)

    def test_rosdistro_defaults_to_loong(self):
        """
        测试场景1: 当不提供 --rosdistro 参数时，它应该默认为 'loong'。
        """
        print("\n---> 1. 测试默认发行版...")
        # 模拟没有命令行参数的情况
        args = self.parser.parse_args([])
        self.generator.handle_arguments(args)
        
        # 断言结果是否符合预期
        self.assertEqual(self.generator.rosdistro, 'loong')
        print("     成功: rosdistro 默认值为 'loong'。")

    def test_rosdistro_can_be_overridden(self):
        """
        测试场景2: 当提供 --rosdistro jazzy 参数时，它应该覆盖默认值。
        """
        print("\n---> 2. 测试覆盖默认发行版...")
        # 模拟命令行输入 --rosdistro jazzy
        args = self.parser.parse_args(['--rosdistro', 'jazzy'])
        self.generator.handle_arguments(args)

        # 断言结果是否符合预期
        self.assertEqual(self.generator.rosdistro, 'jazzy')
        print("     成功: rosdistro 被正确覆盖为 'jazzy'。")

    def test_help_message_is_updated(self):
        """
        测试场景3: 验证帮助信息是否已更新为我们修改后的静态文本。
        """
        print("\n---> 3. 测试帮助信息...")
        # argparse会将参数定义存储在 _actions 列表中。我们找到 --rosdistro 对应的定义。
        action = None
        for act in self.parser._actions:
            if '--rosdistro' in act.option_strings:
                action = act
                break
        
        # 断言找到了参数定义
        self.assertIsNotNone(action, "未能找到 --rosdistro 参数的定义")
        
        # 断言帮助文本和默认值是否符合预期
        expected_help = "ROS distro to target (default: loong)"
        self.assertEqual(action.help, expected_help)
        print(f"     成功: 帮助文本为 '{action.help}'。")
        
        self.assertEqual(action.default, 'loong')
        print(f"     成功: 参数默认值为 '{action.default}'。")


if __name__ == '__main__':
    print("开始测试优化后的 rosrelease.py ...")
    unittest.main()


# -*- coding: utf-8 -*-

from __future__ import print_function
import sys

# 检查当前Python版本，确保兼容性
if sys.version_info.major < 3:
    print("警告: 建议在Python 3环境下运行此测试脚本。")

try:
    # --- 这是关键的修改 ---
    # 我们明确地告诉Python，要从'bloom'这个包里导入'rosdistro_api'模块
    from bloom.rosdistro_api import get_index, list_distributions, get_distribution_file, get_index_url
    print("成功导入 bloom.rosdistro_api 模块。")
except ImportError:
    print("错误: 无法导入 'bloom.rosdistro_api'。")
    print("请确保:")
    print("1. 您正从项目的根目录 (包含 'bloom' 文件夹的目录) 运行此脚本。")
    print("2. 'bloom' 文件夹下有一个 '__init__.py' 文件。")
    sys.exit(1)


def run_tests():
    
    # 测试 1: 获取索引文件 
    print("\n---> 1. 正在尝试获取索引文件...")
    try:
        # 首先检查 get_index_url 的返回值是否符合预期
        index_url = get_index_url()
        print("     修改后的 get_index_url() 返回: " + index_url)
        if '1.94.193.239' not in index_url:
             print("     警告: get_index_url() 的返回值不包含预期的IP地址！")

        # 然后获取并解析索引对象
        index = get_index()
        assert index is not None, "索引对象不应为空"
        print("     成功获取并解析了索引文件！")
    except Exception as e:
        print("     测试失败: 获取或解析索引文件时出错。")
        print("     错误详情: " + str(e))
        print("     检查: 1. 您的服务器是否正在运行。 2. index.yaml的URL是否正确。 3. index.yaml文件格式是否正确。")
        return

    # 测试 2: 列出发行版并检查 'loong' 
    print("\n---> 2. 正在列出所有可用的发行版...")
    try:
        distros = list_distributions()
        print("     检测到的发行版: " + str(distros))
        assert 'loong' in distros, "'loong' 不在发行版列表中"
        print("     成功在列表中找到了您的 'loong' 发行版！")
    except Exception as e:
        print("     测试失败: 检查发行版列表时出错。")
        print("     错误详情: " + str(e))
        print("     检查: index.yaml 文件中是否包含了 'loong' 的条目。")
        return

    # 测试 3: 获取 'loong' 的 distribution.yaml 
    print("\n---> 3. 正在尝试获取 'loong' 的详细配置文件 (distribution.yaml)...")
    try:
        dist_file = get_distribution_file('loong')
        assert dist_file is not None, "'loong' 的 distribution 文件不应为空"
        print("     成功获取并解析了 'loong' 的 distribution.yaml 文件！")
    except Exception as e:
        print("     测试失败: 获取或解析 'loong' 的 distribution.yaml 时出错。")
        print("     错误详情: " + str(e))
        print("     检查: 1. 您在 index.yaml 中为 'loong' 配置的相对路径是否正确。 2. distribution.yaml 的URL是否可访问。 3. distribution.yaml 文件格式是否正确。")
        return
        
    # 测试 4: 检查 distribution.yaml 中的内容 
    print("\n---> 4. 正在打印 'loong' 中的部分软件包信息...")
    try:
        # 访问一个存在于 distribution.yaml 中的软件包
        package_name_to_check = 'aandd_ekew_driver_py'
        if package_name_to_check in dist_file.repositories:
            repo_info = dist_file.repositories[package_name_to_check]
            print("     在 'loong' 中找到了 '{0}' 软件包。".format(package_name_to_check))
            if repo_info.source_repository:
                print("       - 源码仓库: " + repo_info.source_repository.url)
                print("       - 版本: " + repo_info.source_repository.version)
        else:
            print("     警告: 在 'loong' 的 distribution.yaml 中未找到名为 '{0}' 的示例包。".format(package_name_to_check))

    except Exception as e:
        print("     测试失败: 读取 distribution.yaml 内容时出错。")
        print("     错误详情: " + str(e))
        return
        
    print("\n所有测试通过，rosdistro_api.py 修改和服务器配置是正确的。")


if __name__ == '__main__':
    run_tests()


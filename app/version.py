"""应用版本：tufup 自动更新用它与服务端 targets 比较（semver 字符串）。

发版流程：改此版本号 → commit → git tag v<版本> → push tag（CI 自动构建发布）。
"""
__version__ = "0.2.1"

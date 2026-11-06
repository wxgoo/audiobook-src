# -*- coding: utf-8 -*-
"""pytest 配置：把项目根目录塞进 sys.path（测试在 tests/ 子目录里跑）。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
if PROJECT not in sys.path:
    sys.path.insert(0, PROJECT)

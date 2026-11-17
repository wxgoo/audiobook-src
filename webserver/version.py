#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

# 运行期版本号：4.7.0-build.06 =「上游 mybooks 4.7.0」+「第 06 次本地构建」，自本版起统一启用。
# 旧 4.8.x 号段已封存，与本版本是纯号段重置，不对应任何版本先后关系。
# -build.N 是 semver 预发布标记：整串排序低于 4.6.0（本程序不发布 npm、无 engines 校验，无实际影响）；
# 同一上游基线的本地构建之间用 build.N 区分，版本检测不能只靠 > 比较，须比较 build.N 段。
# 该值由 scripts/check-version-lock.py 锁定，改这里会被测试与打包检查拦下。
VERSION = "4.7.0-build.06"

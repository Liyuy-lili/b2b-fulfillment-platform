# 源码与证据索引

- [项目文件与源码清单](项目文件与源码清单.md)、[当前来源快照](项目审阅快照.json)。
- [本次整理清单](../整理清单.json)：删除项、保留位置、原文件摘要及恢复备份。
- [上次整合清单](../整理迁移清单.json)：历史记录，路径需再经过本次清单映射。
- [规格](../09-项目规范与进度/AI_IMPLEMENTATION_SPEC.md)、[进度](../09-项目规范与进度/PROJECT_STATUS.md)。

维护资料时，在“项目代码”目录执行：

```powershell
python docs/tools/build_study_references.py
python docs/tools/audit_complete_learning.py
python docs/tools/verify_two_folders.py
```

这些工具只检查静态文档、路径、语法、原始字节和历史数字；不启动业务或访问业务数据库。历史验收不可改写为本轮通过。

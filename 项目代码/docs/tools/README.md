# 资料维护工具

学习资料位于工程同级的[学习资料](../../../学习资料/README.md)，代码命令从项目代码目录运行。

1. build_study_references.py：按当前源码生成数据库、接口、证据和题目索引。
2. audit_complete_learning.py：检查完整学习包，输出新的DOC-two-folders-learning-20261020.json。
3. verify_two_folders.py：校验目录、备份、去重、源代码/原始证据摘要和脚本语法，输出DOC-two-folders-20261020.json。
4. project_layout.py：按整理清单定位历史路径。
5. validate_study_materials.py：兼容资料检查命令，转入当前静态检查。
6. reorganize_two_folders.py、Repair-DependencyPaths.ps1：本次一次性迁移与本地依赖重定位；前者检测到新目录后拒绝重复迁移。organize_learning_materials.py已停用，避免重建旧跳转文件。

上述检查不运行应用/业务DB/迁移/压测，历史通过数字不能当作本轮测试。整理前工具源码保存在恢复ZIP中。

# 首轮外层工具异常摘录

来源：2026-10-23 20:57:05–20:57:07 执行工具返回的stderr；人工整理摘录，不是私有脚本内部捕获的日志。

外层退出码1；`runpy.run_path` → `core_metadata_git_root_iocp_probe.py:33` → `fingerprints()` → `Path.relative_to(ROOT)`：

```text
ValueError: 'private\\p8-validation\\core_metadata_git_root_iocp_probe.py' is not in the subpath of 'C:\\Users\\Administrator\\Documents\\Codex\\zhiming-v4-p8' OR one path is relative and the other is absolute.
```

该位置在创建观察器、写观察报告和实例化MetadataGit之前。外层Job前后active1、项目源不变，原始外层回执SHA记录在本轮validation.json中。

`week-oct23-root-iocp-first-run.txt` 是私有脚本内部输出文件，实际长度0；异常在重定向上下文退出后由外层工具返回，所以不能将该空文件当作已捕获异常栈。

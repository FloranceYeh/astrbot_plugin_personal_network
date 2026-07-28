# Changelog

本项目的主要变更记录在此文件中。

## [0.1.0] - 2026-07-28

### Added

- 按 AstrBot 人格隔离的人物卡片、平台身份、有向多关系和证据存储。
- `update_personal_network` LLM 工具及相关人物一跳关系上下文注入。
- 支持关系图、人物卡、完整 CRUD、人物合并和头像上传的中文 WebUI。
- 单人格 schema JSON 导入导出、冲突预检和 WebP 头像迁移。
- 人物别名及平台昵称列表，按使用频率和最近使用时间排序。
- `/关系查询` 命令和只读 `query_personal_network` LLM 工具。

### Fixed

- LLM 工具改用 AstrBot 标准 `@filter.llm_tool` 装饰器注册。
- 移除英文 Page 元数据、英文文档和 WebUI 运行时国际化。

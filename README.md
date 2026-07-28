# 人物关系网络（Personal Network）

Personal Network 是一个按 AstrBot 人格隔离数据的人物关系网络插件。当前人格可通过受限的 LLM 工具记录对话中明确、长期有效的人物与关系信息；后续聊天会按当前消息命中的姓名、别名和发言者身份，注入相关人物及一跳关系上下文。

## 功能

- 每个 AstrBot 人格拥有完全独立的人物与关系网络。
- 人物卡支持姓名、别名、头像、简介、性格、偏好、重要事实和管理员备注。
- 平台身份与群会话分别记录多个昵称，并按使用次数和最近使用时间排序。
- 支持任意人物之间的有向多关系、关系强度、状态、描述和证据摘录。
- 提供基于 Cytoscape.js 的内嵌关系图、人物卡片、搜索和关系筛选。
- WebUI 支持完整增删改、重复人物合并、头像上传和证据查看。
- 支持单人格 JSON 导入导出、冲突预检及 Base64 WebP 头像迁移。

## 使用方法

1. 在 AstrBot 中启用插件。
2. 打开插件详情页中的“人物关系网络” Page。
3. 选择要查看或管理的 AstrBot 人格。
4. 与机器人正常对话；模型会在发现明确、持久的人物关系信息时调用 `update_personal_network`。

所有现有人格默认启用关系网络，也可以在 Page 顶部逐个人格关闭。关闭后，该人格不再写入数据或注入关系上下文。

LLM 工具只能新增或更新人物、身份、关系和证据，不能删除、合并人物或修改管理员备注。删除、合并、头像上传和管理员备注仅允许通过 Dashboard 操作。

## 昵称规则

- 人物别名保存在人物卡的 `aliases` 列表中，由管理员或 LLM 维护。
- 平台昵称按“平台 + 用户 ID + 群会话”隔离，同一群会话可以保存多个历史昵称。
- 已识别人物每次发言时都会累计当前昵称的使用次数。
- API 和 WebUI 按使用次数降序、最近使用时间降序展示昵称。
- 从旧版数据库或 schema v1 JSON 导入时，原单个昵称会自动迁移为计数为 1 的昵称列表。

## 数据与隐私

SQLite 数据库、头像和临时导出文件存放在 AstrBot 插件数据目录，不会写入 AstrBot 核心数据库。删除 AstrBot 人格不会自动删除对应关系网络；WebUI 会将其标记为缺失人格，管理员仍可导出或清理数据。

关系证据只保存最长 300 字的摘录、来源会话、说话者和时间，不保存完整聊天消息。

## 开发

在 AstrBot 仓库根目录运行：

```bash
uv run python -m pytest -q data/plugins/astrbot_plugin_personal_network/tests
uv run ruff format data/plugins/astrbot_plugin_personal_network
uv run ruff check data/plugins/astrbot_plugin_personal_network
```

内置 Cytoscape.js 3.33.1，MIT 许可证位于 `pages/network/vendor/`。

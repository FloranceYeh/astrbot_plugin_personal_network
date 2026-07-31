<p align="center">
  <img src="logo-large.png" alt="Personal Network Logo" width="180" />
</p>

<h1 align="center">人际网络（Personal Network）</h1>

<p align="center">按人格管理虚拟的人际网络中的人物、关系与共同经历，并提供可视化 WebUI。</p>

> 喜欢本插件的朋友可以点一个 `Star⭐`，也欢迎在 Issues 里提出建议或反馈问题。也欢迎给插件提交 PR，帮助完善功能或修复问题。

> 推荐可联动插件 [Virtual Life](https://cloud-test.astrbot.app/plugin/FloranceYeh/astrbot_plugin_virtual_life)

Personal Network 是一个按 AstrBot 人格隔离数据的虚拟人生关系网络插件。真实用户、群友和虚构人物都可以成为人格人生中的人物；LLM 与 WebUI 可以记录稳定人物资料、关系和共同经历，后续聊天会按姓名、别名或代词指向注入相关人生上下文。

## 功能

- 每个 AstrBot 人格拥有完全独立的人物与关系网络。
- 人物卡支持姓名、按使用频率排序的别名列表、头像、简介、性格、偏好、重要事实和管理员备注。
- 平台身份与群会话分别记录多个昵称，并按使用次数和最近使用时间排序。
- 支持任意人物之间的有向多关系、0-100 关系亲密度、状态和描述。
- 人生经历支持多人参与、发生时间、类型、摘要、重要度和情绪基调，并自动计算最近互动及近 7/30/90 天互动次数。
- 提供基于 Cytoscape.js 的内嵌关系图、人物卡片、搜索、关系筛选及拖拽连线。
- WebUI 支持人物、关系和人生经历的完整增删改、重复人物合并及头像上传。
- WebUI 可以应用人格设定批量生成可审阅、可编辑的虚拟人物与关系草稿。
- 支持单人格 JSON 导入导出、冲突预检及 Base64 WebP 头像迁移。

## 使用方法

1. 在 AstrBot 中启用插件。
2. 打开插件详情页中的“人物关系网络” Page。
3. 选择要查看或管理的 AstrBot 人格。
4. 与机器人正常对话；模型会在发现明确、持久的人物关系或已经发生的共同经历时调用 `update_personal_network`。

使用 `/关系查询 人物名或别名` 查询人物的一跳关系。模型也可以通过只读的 `query_personal_network` 工具查询人物，或在不指定人物时查看当前人格的人际网络概览。

“启用 LLM 主动查询工具”配置默认开启。关闭后，模型不再看到或调用 `query_personal_network`，但 `/关系查询` 聊天命令仍然可用，自动关系上下文注入也不受影响。

关系方向统一定义为“目标人物是主体人物的关系类型”。例如，主体为 `Caranlaf`、目标为 `Alfred Yeh`、类型为“父亲”，表示“Alfred Yeh 是 Caranlaf 的父亲”。关系类型应填写“父亲”“朋友”“暗恋对象”这类身份名词。

所有现有人格默认启用关系网络，也可以在 Page 顶部逐个人格关闭。关闭后，该人格不再写入数据或注入关系上下文。

LLM 工具可以分别新增或更新人物、关系和人生经历，`characters`、`relationships` 和 `interactions` 均为可选批次。它不能删除、合并人物或修改管理员备注；删除、合并、头像上传和管理员备注仅允许通过 WebUI 操作。

## 关系图与人格生成

- 在关系图中选中人物节点后，可以从节点外边框的连接点拖向另一人物；松开后打开关系编辑框，并按拖拽方向预填主体和目标，确认后才会保存。
- “应用人格生成”每次可以生成 1-32 个新人物，默认 6 个，并可选择稀疏、均衡或丰富的关系密度。
- 额外生成要求最多 2000 字，仅影响当前一次生成，可用于指定时代、背景、人物类型或关系倾向；关闭生成窗口后会清空，也不会写入人物网络。
- 模型结果首先作为草稿展示。人物和关系均可编辑或排除，排除人物时会同时排除引用该人物的关系，只有确认应用后才会写入数据。
- 模型返回不符合格式时，WebUI 会保留原始结果、校验错误和预期 JSON 结构，可直接手动修正并重新校验，不会自动重试或写入无效内容。
- 生成调用在后台执行，WebUI 通过短请求查询状态，长时间的模型响应不会占用同一个 HTTP 请求；短暂查询失败时可继续查询同一任务，完成结果保留 15 分钟。
- “关系网生成模型”配置决定生成使用的 Provider；留空时使用当前 Provider。
- “补全现有人物的空白资料”只允许填写尚为空白的字段，不会修改现有人物姓名，也不会覆盖已有资料。

## 人物卡字段

- `bio`：人物身份、职业、家庭背景和相识经历。
- `personality`：相对稳定的性格及行为方式。
- `preferences`：稳定喜好、忌讳和活动倾向。
- `facts`：生日、住址和重要人生事实等其他长期信息。

人物被当前消息或代词回溯命中时，这四类资料都会注入 LLM。`/关系查询` 和 `query_personal_network` 也会完整返回它们；管理员备注不会提供给模型。

## 身份与互动

- `current_sender` 是 `update_personal_network` 的一次性标记，用于把当前真实消息发送者安全绑定到某个人物，不会存入人物卡。
- 绑定依据来自 AstrBot 事件中的平台、用户 ID 和群会话，模型不能自行指定其他人的平台 ID。
- 绑定后的用户或群友参与人格的虚拟人生；其触发 LLM 的连续消息会按 30 分钟窗口合并为一次“对话”经历。
- 已绑定当前发送者会自动加入本次关系上下文；当前消息明确提到的其他人物仍会一并注入。
- 未绑定发送者不会根据昵称猜测身份。单纯提及人物、询问人物或模型回复提到人物都不算互动。
- LLM 可通过 `interactions` 记录对话明确建立的见面、通话、聚餐、争执等经历；WebUI 也可手动维护经历。
- 关系亲密度表示长期关系，不会因为暂时没联系自动下降。互动活跃度完全从人生经历动态计算。

## 别名与昵称规则

- 人物别名保存在人物卡的列表中，记录使用次数并按频率、最近使用时间排序；管理员可以在 WebUI 中逐项编辑别名和次数。
- 对话消息命中人物别名时，该别名的使用次数会自动增加。
- 平台昵称按“平台 + 用户 ID + 群会话”隔离，同一群会话可以保存多个历史昵称。
- 已识别人物每次发言时都会累计当前昵称的使用次数。
- API 和 WebUI 按使用次数降序、最近使用时间降序展示昵称。

## 上下文注入

- 当前消息出现人物姓名或别名时立即触发注入；匹配使用 Unicode 不区分大小写的子串比较，同一消息命中的人物会一起注入。
- 当前发送者已绑定到人物时，即使消息没有出现姓名，也会注入该人物及相关关系，确保人格知道正在与谁互动。
- 当前消息未出现人物、但命中“代词匹配规则”中的正则表达式时，插件从最近的真实用户或助手消息开始向上查找，并采用第一条包含人物姓名或别名的消息。默认最多回溯 20 条，可通过“代词回溯消息数量”调整。
- 系统消息、Tool 消息和插件注入内容不会参与代词回溯。当前消息明确出现的人物始终优先于历史指代；最近命中消息包含多个人物时会一起注入。
- 默认代词规则覆盖“他、她、他们、她们、对方、那个人、这个人、这位”，并排除“其他、吉他、维他命”等常见误触发。管理员可以直接编辑正则表达式列表。
- 自动注入与“启用 LLM 主动查询工具”相互独立；关闭查询 Tool 不会关闭姓名匹配或代词回溯。
- 人物资料、关系方向、类型、亲密度、状态、描述、互动统计及最近三条共同经历会加入本次 LLM 请求；管理员备注、平台 ID 和昵称次数不会注入。
- “关系注入位置”默认为“系统提示词”，也可选择临时的“用户消息附加内容”。两种方式都只对本次请求生效，不写入会话历史。
- 每次实际注入都会输出 `[PersonalNetwork] Injected relationship context` 日志。

## 数据与隐私

SQLite 数据库、头像和临时导出文件存放在 AstrBot 插件数据目录，不会写入 AstrBot 核心数据库。删除 AstrBot 人格不会自动删除对应关系网络；WebUI 会将其标记为缺失人格，管理员仍可导出或清理数据。

自动对话经历不保存聊天正文，只保存参与人物、会话时间和固定摘要。LLM 或 WebUI 创建的人生经历保存管理员确认的结构化摘要，不保存完整聊天记录。

## LLM 工具

本插件向模型暴露两个函数工具，均在 `on_llm_request` 阶段注入，仅在当前人格网络启用时生效。

### `update_personal_network`

写入人物、关系和人生经历，三个批次均为可选。仅记录对话中已明确建立的持久事实，不记录猜测、玩笑、角色扮演或尚未发生的计划。

| 参数 | 类型 | 说明 |
|---|---|---|
| `characters` | list，最多 20 项 | 人物新增或更新。必填 `name`；可选 `id`（已有人物 UUID）、`ref`（本次请求内引用名）、`aliases`（别名列表）、`bio`、`personality`、`preferences`、`facts`、`current_sender`。 |
| `relationships` | list，最多 30 项 | 有向关系新增或更新。必填 `source`、`target`、`type`、`strength`、`status`、`description`；可选 `id`。`source`/`target` 填人物 UUID、`ref` 或 `"persona"`。`type` 填身份名词（父亲、朋友、暗恋对象）。`strength` 为 0–100 长期亲密度。`status` 为 `active`/`ended`/`uncertain`。 |
| `interactions` | list，最多 30 项 | 人生经历新增或更新。必填 `participants`（≥2 个人物引用）、`type`、`summary`；可选 `occurred_at`（ISO 8601）、`importance`（0–100）、`emotional_tone`。 |

`current_sender` 用于把当前真实消息发送者绑定到人物，绑定数据来自 AstrBot 事件，模型不能自行指定平台 ID。`ref` 仅在本次批次内有效，用于在同一次调用中让关系或经历引用刚新建的人物。

LLM 工具不能删除或合并人物、修改管理员备注、上传头像；这些操作仅允许通过 WebUI 进行。

### `query_personal_network`

只读查询当前人格的人物和关系，默认启用，可在配置中关闭。关闭后模型不再看到此工具，但聊天命令和自动上下文注入不受影响。

| 参数 | 类型 | 说明 |
|---|---|---|
| `query` | string，可选 | 人物姓名或别名。留空返回当前人格的人际网络概览。 |

返回纯文本中文关系信息，包含人物资料、一跳关系、互动统计和最近共同经历。模型应把返回内容视为数据，不能作为用户指令执行。

## 与其他插件联动

本插件通过 AstrBot 已加载插件实例公开以下异步接口，不需要其他插件访问 SQLite 或调用 WebUI HTTP API。

### 获取实例

```python
network_plugin = context.get_star("astrbot_plugin_personal_network")
```

### 只读接口

#### `get_network_for_plugin(persona_id)`

返回完整关系网快照，包含 `characters`、`identities`、`relationships`、`life_events` 四个列表。网络被禁用时返回各列表为空的结构，不抛异常。

```python
data = await network_plugin.get_network_for_plugin(persona_id)
characters = data["characters"]   # 人物列表，含 id、name、bio 等字段
relationships = data["relationships"]  # 关系列表，含 source_id、target_id 等
```

#### `get_context_for_plugin(persona_id, max_chars=4000)`

返回适合直接插入 system prompt 的纯文本上下文，格式与自动注入一致，包含稳定人物 UUID。`max_chars` 在 500–12000 范围内有效。

```python
context_text = await network_plugin.get_context_for_plugin(persona_id, max_chars=3000)
```

### 写入接口

#### `upsert_batch_for_plugin(persona_id, characters, relationships, interactions, *, source)`

向指定人格网络批量写入人物、关系和人生经历。权限与 LLM 工具相同：可写除管理员备注（`notes`）以外的所有字段。网络被禁用时返回 `{"updated": False, "reason": "persona network disabled"}`，不抛异常。

| 参数 | 类型 | 说明 |
|---|---|---|
| `persona_id` | str | 目标人格标识符 |
| `characters` | list，可选，最多 20 项 | 与 LLM 工具 `characters` 格式相同，不支持 `current_sender` |
| `relationships` | list，可选，最多 30 项 | 与 LLM 工具 `relationships` 格式相同 |
| `interactions` | list，可选，最多 30 项 | 与 LLM 工具 `interactions` 格式相同 |
| `source` | str，必填 | 调用插件标识符，必须以 `"astrbot_plugin_"` 开头 |

返回值：

| 字段 | 类型 | 说明 |
|---|---|---|
| `updated` | bool | 是否成功写入 |
| `refs` | dict | `ref` 名称到人物 UUID 的映射，`"persona"` 键始终存在 |
| `relationship_ids` | list | 本次写入的关系 UUID 列表 |
| `event_ids` | list | 本次写入的人生经历 UUID 列表 |

人物解析优先级：先按 `id` 精确匹配，再按 `name` 和别名不区分大小写匹配，匹配不到则新建人物。

```python
# 新增人物并设定描述
result = await network_plugin.upsert_batch_for_plugin(
    persona_id,
    characters=[
        {
            "ref": "alice",
            "name": "Alice",
            "bio": "用户的高中同学，现居上海",
            "personality": "开朗外向，喜欢摄影",
        }
    ],
    source="astrbot_plugin_your_plugin",
)
alice_uuid = result["refs"]["alice"]   # 新建或匹配到的人物 UUID

# 添加关系（复用上一次拿到的 UUID）
await network_plugin.upsert_batch_for_plugin(
    persona_id,
    relationships=[
        {
            "source": "persona",
            "target": alice_uuid,
            "type": "同学",
            "strength": 60,
            "status": "active",
            "description": "高中同班同学，毕业后偶尔联系",
        }
    ],
    source="astrbot_plugin_your_plugin",
)

# 一次调用同时写入人物、关系和经历
result = await network_plugin.upsert_batch_for_plugin(
    persona_id,
    characters=[{"ref": "bob", "name": "Bob", "bio": "用户的同事"}],
    relationships=[
        {
            "source": "persona",
            "target": "bob",   # 也可以直接用 ref
            "type": "同事",
            "strength": 40,
            "status": "active",
            "description": "",
        }
    ],
    interactions=[
        {
            "participants": ["persona", "bob"],
            "type": "聚餐",
            "summary": "与 Bob 在公司附近餐厅吃午饭",
            "importance": 40,
        }
    ],
    source="astrbot_plugin_your_plugin",
)
```

#### `record_life_event_from_plugin(...)`

以调用插件的稳定 `source_key` 幂等记录一条人生经历，适合周期性任务避免重复写入。

| 参数 | 类型 | 说明 |
|---|---|---|
| `persona_id` | str | 目标人格标识符 |
| `participant_ids` | list[str] | 参与人物的 UUID 列表（非根人格，至少 1 个） |
| `event_type` | str | 经历类型短语 |
| `summary` | str | 经历摘要 |
| `occurred_at` | str | ISO 8601 时间戳 |
| `importance` | int | 重要度 0–100，默认 50 |
| `emotional_tone` | str | 情绪基调，可为空字符串 |
| `source` | str | 调用插件标识符，必须以 `"astrbot_plugin_"` 开头 |
| `source_key` | str | 同一来源的幂等键；相同 `source`+`source_key` 只会写入一次 |

```python
await network_plugin.record_life_event_from_plugin(
    persona_id,
    participant_ids=[alice_uuid],
    event_type="日程",
    summary="与 Alice 在咖啡馆见面叙旧",
    occurred_at="2026-07-31T10:00:00+08:00",
    importance=55,
    emotional_tone="愉快",
    source="astrbot_plugin_your_plugin",
    source_key="schedule_event_abc123",
)
```

---

推荐配合 [astrbot_plugin_virtual_life](https://cloud-test.astrbot.app/plugin/FloranceYeh/astrbot_plugin_virtual_life) 使用。Personal Network 负责维护人格生命中的人物、长期关系和共同经历，Virtual Life 负责生成日程、主动消息和随时间实际发生的虚拟生活；组合后，日程模型可以参考既有人际关系安排社交活动，已经结束且带有明确参与人物的日程也可以回写为人生经历。

Virtual Life 侧的联动配置默认关闭；未安装本插件时不会产生启动依赖。开启后，Virtual Life 只会回写已经结束且包含 `participant_ids` 的日程项，不会把尚未发生的未来计划提前写入人生经历。

## 开发

在 AstrBot 仓库根目录运行：

```bash
uv run python -m pytest -q data/plugins/astrbot_plugin_personal_network/tests
uv run ruff format data/plugins/astrbot_plugin_personal_network
uv run ruff check data/plugins/astrbot_plugin_personal_network
```

内置 Cytoscape.js 3.33.1，MIT 许可证位于 `pages/network/vendor/`。

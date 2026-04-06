# Everybody Tennis AstrBot 插件技术设计文档

## 1. 文档目标

本文档基于 [requirements.md](/home/ubuntu/astrbot_plugin_everybody_tennis/docs/requirements.md) 产出首版技术设计，目标是为后续实现提供明确的工程结构、模块边界、数据模型、命令接口和核心流程。

本设计遵循 `astrbot-plugin-dev` 的工程化建议：

- `main.py` 保持薄，只负责插件注册、生命周期和命令委托。
- 复杂业务流程下沉到 `src/` 分层模块。
- 配置通过 `_conf_schema.json` + `ConfigManager` 管理。
- 持久化数据写入 `data/plugin_data/astrbot_plugin_everybody_tennis/`。

## 2. 设计原则

### 2.1 首版优先级

首版优先保证以下三件事：

- 识别结果可控，必须先确认再入库。
- 统计口径稳定，群内排行和个人战绩能长期累积。
- 代码结构可扩展，后续能继续加修正、报表和更多统计。

### 2.2 关键设计决策

本设计做出以下明确选择：

1. 插件采用工程化分层结构，不继续使用当前模板式单文件实现。
2. 命令入口以 AstrBot 指令组为主，主命令组为 `/网球`。
3. 数据库使用 SQLite，驱动使用异步方式，首版建议 `SQLAlchemy 2.0 + aiosqlite`。
4. 统计结果首版使用实时聚合，不做物化统计表。
5. 多模态提取通过 AstrBot 的 `llm_generate` 能力完成，输入采用“文本 + 图片 URL”消息片段。
6. 首版不引入群成员与游戏昵称绑定，录入和确认直接基于截图中的游戏昵称完成，个人查询时显式指定游戏昵称。

## 3. 总体架构

### 3.1 架构概览

```text
AstrBot Command/Event
        |
        v
     main.py
        |
        v
Application Services
        |
        +--> Domain Services
        |
        +--> Repositories (Interface)
        |
        +--> Infrastructure
              |- LLM Extractor
              |- SQLite Persistence
              |- Image Storage
              |- Config Manager
              |- Result Renderer
```

### 3.2 分层职责

#### `main.py`

职责仅包括：

- 注册插件类与命令。
- 处理 AstrBot 生命周期，例如 `on_platform_loaded`、`terminate`。
- 初始化依赖对象。
- 将命令事件委托给应用服务。

不在 `main.py` 中实现：

- LLM 提取提示词编排
- 数据库 SQL 细节
- 统计逻辑
- 昵称驱动查询规则
- 复杂结果格式化

#### `application/`

负责业务编排，用例级流程在这一层完成。

建议模块：

- `ingest_service.py`：处理截图录入请求。
- `confirmation_service.py`：处理确认、取消、删除。
- `query_service.py`：按游戏昵称处理个人战绩和最近比赛。
- `ranking_service.py`：处理群排行。

#### `domain/`

负责 AstrBot 无关的核心业务规则。

建议模块：

- `entities/`：`Match`、`Player`、`Group`、`MatchPlayerStat`
- `value_objects/`：`MatchStatus`、`RankingMetric`、`ExtractionResult`
- `services/`：`StatCalculator`、`MatchNormalizer`、`DuplicateDetector`
- `repositories/`：仓储接口定义

#### `infrastructure/`

负责与外部系统交互。

建议模块：

- `config/config_manager.py`
- `llm/multimodal_extractor.py`
- `persistence/db.py`
- `persistence/models.py`
- `persistence/repositories/`
- `storage/image_store.py`
- `messaging/result_renderer.py`
- `platform/message_parser.py`

## 4. 目录结构设计

建议重构后的目录结构如下：

```text
astrbot_plugin_everybody_tennis/
├── main.py
├── metadata.yaml
├── requirements.txt
├── _conf_schema.json
├── README.md
├── docs/
│   ├── requirements.md
│   └── technical_design.md
└── src/
    ├── application/
    │   ├── services/
    │   │   ├── confirmation_service.py
    │   │   ├── ingest_service.py
    │   │   ├── query_service.py
    │   │   └── ranking_service.py
    │   └── dto/
    ├── domain/
    │   ├── entities/
    │   ├── repositories/
    │   ├── services/
    │   └── value_objects/
    ├── infrastructure/
    │   ├── config/
    │   ├── llm/
    │   ├── messaging/
    │   ├── persistence/
    │   ├── platform/
    │   └── storage/
    └── shared/
```

## 5. 生命周期设计

### 5.1 初始化模式

插件应采用幂等初始化，避免 AstrBot 重载或平台延迟加载时重复创建资源。

建议模式：

- 在 `__init__` 中只保存上下文、配置和少量轻量对象。
- 在 `@filter.on_platform_loaded()` 中执行 `_run_initialization()`。
- 初始化阶段完成以下动作：
  - 创建 `ConfigManager`
  - 初始化数据库连接与 schema
  - 初始化图片存储目录
  - 组装应用服务

### 5.2 卸载模式

在 `terminate()` 中保证：

- 不再接收新请求
- 关闭数据库连接
- 取消后台任务

首版不要求复杂后台任务，但应保留 `_background_tasks` 管理模式，方便后续增加过期清理和报表调度。

待确认记录过期清理首版采用惰性策略：

- 每次访问确认、取消、查询待确认记录前，先把已过期 `pending` 记录标记为 `cancelled` 或 `expired`
- 后续如果需要，再升级为定时任务清理

## 6. 命令设计

### 6.1 主命令组

技术上建议使用 AstrBot 的命令组能力，以 `/网球` 作为主命令组。

建议命令：

- `/网球 录入`
- `/网球 确认 <记录号>`
- `/网球 取消 <记录号>`
- `/网球 战绩 <游戏昵称>`
- `/网球 最近 <游戏昵称> [条数]`
- `/网球 排行 [指标] [人数]`
- `/网球 删除 <记录号>`
- `/网球 帮助`

### 6.2 为什么改为“查询时指定昵称”

当前截图里天然存在的是游戏内昵称，而不是稳定的平台用户映射。若首版强行要求用户先做绑定，会直接阻塞录入和确认链路。

因此首版改为：

- 录入时直接保存截图识别出的原始昵称和标准化昵称。
- 默认在录入阶段就校验字段完整性和胜负可判定，满足条件则直接入库。
- 只有识别字段缺失时才保留待确认记录。
- 查询时由用户显式指定游戏昵称。
- 排行按标准化后的游戏昵称聚合。

这样能先把“录入 -> 自动入库 -> 需要时再取消”主链路跑通。后续如果确实需要跨昵称合并，再补独立的别名/身份映射能力。

### 6.3 录入命令交互

建议首版交互如下：

1. 用户发送 `/网球 录入` 并附带截图。
2. 插件返回识别预览，包含：
   - 记录号
   - 双方昵称
   - 主要统计
   - 是否存在缺失字段
3. 若字段完整，插件直接入库，并提示用户如有需要可发送 `/网球 取消 <记录号>` 撤销。
4. 若字段缺失，插件保留为 `pending`，再提示用户发送 `/网球 确认 <记录号>` 或 `/网球 取消 <记录号>`。

首版不依赖多轮会话等待器。完整记录自动入库，只有残缺记录才需要显式确认。

## 7. 核心业务流程设计

### 7.1 截图录入流程

```text
用户发命令和截图
  -> main.py 命令入口
  -> MessageParser 提取群、用户、图片信息
  -> ImageStore 保存原图并计算 sha256
  -> MultimodalExtractor 调用 LLM 提取 JSON
  -> MatchNormalizer 标准化字段
  -> DuplicateDetector 检查是否疑似重复
  -> 完整记录写入 confirmed
  -> 不完整记录写入 pending
  -> ResultRenderer 输出预览
```

### 7.2 确认流程

```text
用户发送确认命令
  -> 查询 pending 记录
  -> 校验操作者权限和记录状态
  -> 校验字段完整性
  -> 将状态改为 confirmed
  -> 查询端后续基于 confirmed 数据聚合统计
```

### 7.3 删除流程

首版采用软删除：

- `status` 改为 `deleted`
- 保留原始记录和截图路径
- 排行和战绩查询自动忽略 `deleted`

这样更适合后续审计和问题排查。

## 8. 昵称聚合设计

### 8.1 设计目标

首版统计主体直接使用截图中的游戏昵称，避免“先绑定才能用”的高门槛交互。

### 8.2 聚合策略

昵称聚合规则如下：

1. 对截图提取出的玩家名称做标准化处理，例如去首尾空格、去内部空格、统一大小写。
2. `match_player_stats.normalized_player_name` 作为首版查询和排行聚合键。
3. `raw_player_name` 保留原始展示名称，查询和排行默认展示最近一次出现的写法。
4. 后续若要支持别名合并，在此基础上再追加映射表，而不是阻塞当前主链路。

### 8.3 关键规则

- 昵称匹配应先做标准化，例如去首尾空格、统一大小写。
- 只有字段完整、胜负可判定的比赛才允许进入正式统计。
- 同一标准化昵称默认视为同一统计主体。

### 8.4 首版边界

首版只做群内昵称聚合，不做跨群统一用户，也不做别名合并。

## 9. 多模态提取设计

### 9.1 调用方式

AstrBot 内部消息片段支持 `TextPart` 和 `ImageURLPart`，因此提取器设计为：

1. 解析出消息中的图片 URL 或本地可访问图片资源。
2. 通过 `self.context.get_current_chat_provider_id(umo)` 获取当前会话模型，或使用配置中指定的 provider。
3. 调用 `self.context.llm_generate(...)`，将文本提示与图片片段一起传入。

推荐的逻辑优先级：

- 若配置中指定 `llm.provider_id`，优先使用该 provider。
- 否则回退到当前会话绑定 provider。

### 9.2 提取器输入

输入包括：

- 图片 URL
- 标准化提示词
- 可选上下文：
  - 当前群名
  - 提交人昵称
  - 被 @ 的对手昵称

### 9.3 提取器输出 JSON Schema

提取器的目标不是输出自然语言，而是输出稳定 JSON。建议 schema 如下：

```json
{
  "players": [
    {
      "side": 1,
      "name": "ntr",
      "points_won": 24,
      "winners": 19,
      "serve_points_won": 3,
      "errors": 1,
      "double_faults": 0,
      "net_play_rate": 0.466
    },
    {
      "side": 2,
      "name": "幸",
      "points_won": 12,
      "winners": 11,
      "serve_points_won": 1,
      "errors": 0,
      "double_faults": 0,
      "net_play_rate": 0.2
    }
  ],
  "set_count": 1,
  "game_count": 6,
  "duration_seconds": 233,
  "max_rally_count": 4,
  "missing_fields": [],
  "is_complete": true
}
```

### 9.4 标准化规则

`MatchNormalizer` 负责：

- 把百分比字符串转成 `0-1` 小数
- 把 `00:03:53` 转成秒数
- 去除昵称两侧空白
- 将无法解析的字段登记到 `missing_fields`
- 根据双方 `points_won` 自动推导 `winner_side`，不依赖模型显式给出

### 9.5 失败处理

提取失败时分为三类：

- `image_missing`：消息中没有图片
- `provider_unavailable`：当前 provider 不可用或不支持图片
- `extraction_invalid`：模型输出无法解析为目标 JSON

这三类错误都需要给出用户可理解的提示文本，并写入日志。

## 10. 数据存储设计

### 10.1 存储路径

插件数据统一保存到：

```text
data/plugin_data/astrbot_plugin_everybody_tennis/
├── tennis.db
└── images/
    └── YYYYMM/
```

### 10.2 技术选型

首版建议：

- ORM/数据库层：`SQLAlchemy 2.0`
- SQLite 驱动：`aiosqlite`
- schema 初始化：插件启动时执行 `create_all`

不在首版引入 Alembic。等 schema 稳定后再考虑迁移体系。

### 10.3 表设计

#### `groups`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | INTEGER PK | 内部主键 |
| `platform` | TEXT | 平台标识 |
| `external_group_id` | TEXT | 平台群 ID |
| `group_name` | TEXT | 群名称 |
| `created_at` | DATETIME | 创建时间 |

约束：

- 唯一索引：`(platform, external_group_id)`

#### `players`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | INTEGER PK | 内部主键 |
| `group_id` | INTEGER FK | 所属群 |
| `platform_user_id` | TEXT NULL | 平台用户 ID |
| `display_name` | TEXT | 当前展示名称 |
| `normalized_display_name` | TEXT | 标准化展示名称 |
| `created_at` | DATETIME | 创建时间 |
| `updated_at` | DATETIME | 更新时间 |

说明：

- 首版按群建模，不做跨群合并身份。
- `platform_user_id` 当前主要用于标记提交人和操作权限，不参与首版统计聚合。

#### `player_aliases`

该表保留为后续扩展预留，首版主链路不依赖它完成录入、确认和查询。

#### `matches`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | INTEGER PK | 内部主键 |
| `match_code` | TEXT UNIQUE | 面向用户展示的记录号 |
| `group_id` | INTEGER FK | 所属群 |
| `status` | TEXT | `pending/confirmed/cancelled/expired/deleted` |
| `submitted_by_user_id` | TEXT | 提交人平台用户 ID |
| `submitted_by_name` | TEXT | 提交人名称 |
| `source_image_path` | TEXT | 本地截图路径 |
| `source_image_sha256` | TEXT | 图片哈希 |
| `raw_extraction_json` | TEXT | 模型原始结构化输出 |
| `normalized_json` | TEXT | 标准化后的 JSON |
| `missing_fields_json` | TEXT | 缺失字段列表 |
| `duplicate_of_match_id` | INTEGER NULL | 疑似重复记录引用 |
| `set_count` | INTEGER | 盘数 |
| `game_count` | INTEGER | 局数 |
| `duration_seconds` | INTEGER | 对局时长秒数 |
| `max_rally_count` | INTEGER | 最长回合 |
| `winner_player_id` | INTEGER NULL | 胜者 |
| `loser_player_id` | INTEGER NULL | 负者 |
| `expires_at` | DATETIME NULL | 待确认过期时间 |
| `confirmed_at` | DATETIME NULL | 确认时间 |
| `cancelled_at` | DATETIME NULL | 取消时间 |
| `deleted_at` | DATETIME NULL | 删除时间 |
| `created_at` | DATETIME | 创建时间 |
| `updated_at` | DATETIME | 更新时间 |

索引建议：

- `(group_id, status, created_at)`
- `(group_id, status, expires_at)`
- `(group_id, confirmed_at)`
- `(source_image_sha256)`

#### `match_player_stats`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | INTEGER PK | 主键 |
| `match_id` | INTEGER FK | 比赛 |
| `side` | INTEGER | 1 或 2 |
| `raw_player_name` | TEXT | 提取出的昵称 |
| `normalized_player_name` | TEXT | 标准化昵称 |
| `player_id` | INTEGER NULL | 解析后的玩家 ID |
| `is_winner` | BOOL | 是否获胜 |
| `points_won` | INTEGER | 点数取得次数 |
| `winners` | INTEGER | 胜球次数 |
| `serve_points_won` | INTEGER | 发球得分次数 |
| `errors` | INTEGER | 失误球次数 |
| `double_faults` | INTEGER | 双发失误次数 |
| `net_play_rate` | REAL | 网前截击率 |
| `created_at` | DATETIME | 创建时间 |

约束：

- 唯一索引：`(match_id, side)`

说明：

- `player_id` 允许在待确认阶段为空。
- 确认前必须解析并写入双方 `player_id`。

#### `extraction_logs`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | INTEGER PK | 主键 |
| `match_id` | INTEGER FK | 对应比赛 |
| `provider_id` | TEXT | 使用的 provider |
| `model_name` | TEXT | 模型名 |
| `prompt_version` | TEXT | 提示词版本 |
| `request_payload_json` | TEXT | 发送给模型的请求摘要 |
| `response_text` | TEXT | 原始响应文本 |
| `parse_success` | BOOL | 是否解析成功 |
| `parse_error` | TEXT NULL | 解析错误 |
| `latency_ms` | INTEGER | 调用耗时 |
| `created_at` | DATETIME | 创建时间 |

### 10.4 记录号设计

建议给用户使用的记录号采用可读字符串，例如：

- `TEN-20260405-0001`

优点：

- 用户确认、删除时更容易输入。
- 运维排查时更直观。
- 不暴露数据库自增主键。

## 11. 状态机设计

### 11.1 `matches.status`

状态流转如下：

```text
pending -> confirmed
pending -> cancelled
pending -> expired
pending -> deleted
confirmed -> deleted
```

不允许：

- `confirmed -> pending`
- `cancelled -> confirmed`
- `expired -> confirmed`
- `deleted -> confirmed`

### 11.2 状态校验规则

- 只有 `pending` 状态允许确认。
- 只有记录提交人或管理员可以取消 `pending` 记录。
- 只有提交人或管理员可以删除记录。
- `missing_fields` 非空或 `player_id` 未完全解析时，不允许确认。

## 12. 统计与排行设计

### 12.1 聚合策略

首版采用查询时实时聚合，不维护汇总表。

原因：

- 群场景数据量有限。
- 软删除和后续修正逻辑更容易保持一致。
- MVP 阶段避免缓存失效和重算复杂度。

### 12.2 统计基础过滤条件

所有正式统计必须满足：

- `matches.status = confirmed`
- `matches.deleted_at IS NULL`
- `match_player_stats.player_id IS NOT NULL`

### 12.3 支持的核心指标

个人战绩：

- 总场次
- 胜场
- 负场
- 胜率
- 场均得分
- 场均胜球
- 场均发球得分
- 场均失误
- 场均双误
- 平均网前截击率

群排行：

- 胜场榜
- 胜率榜
- 场次榜
- 场均得分榜
- 场均胜球榜

### 12.4 时间范围设计

首版支持：

- `全部`
- `近7天`
- `本月`

实现方式：

- 应用层把自然语言时间范围解析为 `start_at/end_at`
- 仓储层仅接受结构化时间条件

### 12.5 胜率排行门槛

默认最少场次门槛由配置控制，默认值建议为 `3`。

## 13. 重复数据检测设计

### 13.1 MVP 规则

首版采用保守策略，只做“疑似重复提示”，不自动拒绝。

检测依据：

- 相同 `source_image_sha256`
- 或同群内双方昵称一致、时长一致、局数一致，且在短时间窗口内已存在一条记录

### 13.2 行为

- 若命中疑似重复，预览结果中提醒用户。
- 管理员可后续删除重复数据。

## 14. 消息渲染设计

### 14.1 首版输出形式

首版统一输出纯文本，必要时使用简洁表格风格。

原因：

- 先稳定数据链路。
- 文本调试成本低。
- 后续可无缝扩展为 `html_render` 榜单图片。

### 14.2 典型预览格式

```text
网球记录预览
记录号: TEN-20260405-0001
状态: 待确认
玩家1: ntr -> 已匹配 @张三
玩家2: 幸 -> 未匹配
比分字段: 点数 24:12
时长: 00:03:53
最长回合: 4
缺失字段: 无

请发送:
/网球 确认 TEN-20260405-0001
或
/网球 取消 TEN-20260405-0001
```

## 15. 配置设计

### 15.1 `_conf_schema.json` 分组

建议配置分组如下：

- `basic`
- `llm`
- `storage`
- `ranking`
- `prompts`
- `debug`

### 15.2 配置项建议

#### `basic`

- `enabled: bool = true`
- `group_only: bool = true`
- `allow_submitter_delete: bool = true`

#### `llm`

- `provider_id: string = ""`
- `prompt_version: string = "v1"`
- `strict_json: bool = true`
- `timeout_seconds: int = 60`

#### `storage`

- `keep_source_image: bool = true`
- `pending_expire_hours: int = 24`

#### `ranking`

- `min_matches_for_win_rate: int = 3`
- `default_top_n: int = 10`

#### `prompts`

- `extraction_system_prompt: text`
- `extraction_user_prompt_template: text`

#### `debug`

- `debug_mode: bool = false`
- `log_llm_response: bool = false`

### 15.3 `ConfigManager` 职责

`ConfigManager` 负责：

- 提供类型安全的读取方法
- 隐藏配置分组细节
- 提供默认值
- 集中管理提示词版本和排行阈值

## 16. 关键类设计

### 16.1 `MultimodalExtractor`

职责：

- 构造模型请求
- 发送“文本 + 图片 URL”上下文
- 记录调用耗时
- 返回原始文本和解析后 JSON

输入：

- `provider_id`
- `image_url`
- `prompt_context`

输出：

- `ExtractionResult`

### 16.2 `IngestService`

职责：

- 校验命令输入
- 触发截图保存、提取、标准化、查重、待确认写库
- 返回录入预览 DTO

### 16.3 `QueryService`

职责：

- 按游戏昵称查询个人战绩
- 按游戏昵称查询最近比赛
- 格式化统计结果 DTO

### 16.4 `RankingService`

职责：

- 校验排行指标
- 按标准化游戏昵称执行群维度聚合
- 应用最少场次阈值

## 17. 实现顺序建议

建议按下面顺序落地：

1. 重构项目骨架和分层目录。
2. 建立 `_conf_schema.json` 和 `ConfigManager`。
3. 建立数据库 schema、Repository 和图片存储。
4. 实现截图录入和待确认流程。
5. 实现确认、取消、删除。
6. 实现按游戏昵称查询的个人战绩和最近比赛。
7. 实现群排行。
8. 最后再补更好的文本样式和图片榜单。

## 18. 主要风险与应对

### 18.1 模型输出不稳定

应对：

- 强制 JSON 输出
- 使用标准 schema 校验
- 保存原始响应
- 必须走确认流程

### 18.2 同名或改名导致统计歧义

应对：

- 首版统一按标准化昵称聚合
- 查询时显式要求输入游戏昵称
- 后续再补别名合并和人工修正

### 18.3 重复录入污染统计

应对：

- 保存图片哈希
- 做疑似重复提示
- 保留软删除能力

### 18.4 后续字段扩展

应对：

- 比赛统计按 `matches` + `match_player_stats` 拆表
- 额外原始 JSON 保留在库中

## 19. 结论

这份技术设计的核心不是把所有功能都写复杂，而是先把后续最容易失控的三个点设计稳定：

- 工程结构
- 身份映射
- 确认入库状态流

只要这三层先定住，AstrBot 插件首版就可以在较低复杂度下跑通完整业务链路，后续再继续追加修正、图表和更多排行能力。

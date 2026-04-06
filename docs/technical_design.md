# Everybody Tennis AstrBot 插件技术设计文档

## 1. 文档目标

本文档描述 `astrbot_plugin_everybody_tennis` 当前实现的真实技术方案，重点服务于后续维护、重构和扩展，而不是停留在早期方案讨论。

维护者应优先把这份文档当作：

- 当前代码结构总览
- 关键业务规则说明
- 模块修改入口索引
- 扩展时的影响面清单

如果文档与代码不一致，以代码为准，并在修改代码后同步更新本文档。

## 2. 当前实现概览

插件目标是收集群聊中的网球比赛截图，通过多模态模型提取结构化比赛数据，沉淀为群维度的历史战绩，并提供查询与排行能力。

当前版本的核心行为如下：

1. 用户在群聊发送 `/网球 录入` 并附带截图。
2. 用户也可以发送 `/网球 双打录入` 录入 4 人双打截图。
3. 插件解析图片、保存原图、调用多模态模型提取比赛数据。
4. 单打按双方 `points_won` 判定胜负；双打按前两名与后两名的队伍总点数判定胜负。
5. 若字段完整且胜负可判定，则记录直接写入 `confirmed`。
6. 若字段有缺失，则记录写入 `pending`，用户可后续 `/网球 确认` 或 `/网球 取消`。
7. 当前单打查询和排行仅统计 `confirmed` 的 `singles` 记录，双打已支持战绩和最近比赛查询，双打排行后续再补。

首版已经明确放弃的方案：

- 不做平台用户与游戏昵称绑定
- 不做别名映射
- 不做汇总表或缓存表
- 不做数据库迁移兼容，schema 变更时允许直接删库重建

## 3. 代码结构

当前工程结构如下：

```text
astrbot_plugin_everybody_tennis/
├── main.py
├── README.md
├── _conf_schema.json
├── requirements.txt
├── docs/
│   ├── requirements.md
│   └── technical_design.md
├── src/
│   ├── application/
│   │   ├── dto/
│   │   └── services/
│   ├── infrastructure/
│   │   ├── config/
│   │   ├── llm/
│   │   ├── messaging/
│   │   ├── persistence/
│   │   ├── platform/
│   │   └── storage/
│   └── shared/
└── tests/
```

### 3.1 分层职责

#### `main.py`

只负责：

- AstrBot 插件注册
- 生命周期管理
- 依赖组装
- 命令入口与异常转用户提示

不负责：

- SQL 细节
- 多模态提示词和解析逻辑
- 统计聚合
- 文本渲染细节

#### `src/application/services/`

负责业务用例编排，是最主要的维护入口。

- [ingest_service.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/application/services/ingest_service.py)
  录入主流程，决定自动确认还是进入 `pending`
- [confirmation_service.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/application/services/confirmation_service.py)
  处理 `pending -> confirmed` 和 `pending/confirmed -> cancelled`
- [delete_service.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/application/services/delete_service.py)
  处理软删除
- [query_service.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/application/services/query_service.py)
  按游戏昵称查询个人统计和最近比赛
- [ranking_service.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/application/services/ranking_service.py)
  群排行聚合
- [\_scope.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/application/services/_scope.py)
  共用的群范围查询助手，避免多处重复写 group/match 定位逻辑

#### `src/infrastructure/`

负责与外部系统交互。

- [config_manager.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/infrastructure/config/config_manager.py)
  配置读取入口
- [multimodal_extractor.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/infrastructure/llm/multimodal_extractor.py)
  多模态模型调用、JSON 提取与标准化
- [result_renderer.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/infrastructure/messaging/result_renderer.py)
  用户可见文本输出
- [message_parser.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/infrastructure/platform/message_parser.py)
  从 AstrBot 事件中提取图片文件路径
- [db.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/infrastructure/persistence/db.py)
  数据库初始化和 session 管理
- [models.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/infrastructure/persistence/models.py)
  SQLAlchemy 模型定义
- [image_store.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/infrastructure/storage/image_store.py)
  原图归档和 SHA256 计算

#### `src/shared/`

放跨层通用工具。

- [text.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/shared/text.py)
  昵称标准化
- [time.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/shared/time.py)
  统一 UTC 时间入口

## 4. 运行与生命周期

### 4.1 初始化

插件类在 [main.py](/home/ubuntu/astrbot_plugin_everybody_tennis/main.py) 中注册。初始化策略是幂等的：

- `__init__` 中构建依赖对象
- `@filter.on_platform_loaded()` 触发 `_run_initialization()`
- `_ensure_ready()` 在命令执行前兜底初始化

这样做的原因：

- AstrBot 平台加载顺序并不总是稳定
- 避免重复初始化数据库
- 避免插件重载后出现状态不一致

### 4.2 卸载

`terminate()` 只做两件事：

- 阻止后续请求继续使用旧实例
- 关闭数据库连接

当前没有后台任务，也没有定时调度器。后续如果新增清理任务或报表任务，优先保持这个边界，不要把任务逻辑直接塞进命令处理函数。

## 5. 命令与业务行为

当前命令以 `/网球` 为主命令组：

- `/网球 帮助`
- `/网球 录入`
- `/网球 双打录入`
- `/网球 确认 <记录号>`
- `/网球 取消 <记录号>`
- `/网球 删除 <记录号>`
- `/网球 战绩 <游戏昵称>`
- `/网球 最近 <游戏昵称> [条数]`
- `/网球 双打战绩 <游戏昵称>`
- `/网球 双打最近 <游戏昵称> [条数]`
- `/网球 排行 [指标] [人数]`

### 5.1 录入

录入流程由 [ingest_service.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/application/services/ingest_service.py) 负责：

1. 保存原图到本地。
2. 调用多模态模型提取结构化 JSON。
3. 解析 `missing_fields`。
4. 根据比赛类型自动推导 `winner_side`。
5. 若 `missing_fields` 为空且 `winner_side` 有效，则直接入库为 `confirmed`。
6. 否则写入 `pending` 并记录过期时间。

当前自动确认条件是：

- `missing_fields == []`
- `winner_side in {1, 2}`

双打补充规则：

- 使用 `match_type = doubles`
- 固定 4 名玩家
- 前两名归属 `side = 1`
- 后两名归属 `side = 2`
- 双打新增球员字段 `max_serve_speed_kmh`

### 5.2 确认

确认流程由 [confirmation_service.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/application/services/confirmation_service.py) 负责。

当前规则：

- 只能确认 `pending`
- 只能由提交人本人确认
- 记录未过期
- 当前记录必须仍能识别出一方胜、一方负

注意：

- `missing_fields` 非空不再自动阻止确认
- 这是当前代码的有意设计，因为有些缺失字段并不影响胜负判定和核心统计

### 5.3 取消

取消也在 [confirmation_service.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/application/services/confirmation_service.py) 中处理。

当前规则：

- 提交人可以取消 `pending`
- 提交人也可以撤销已自动入库的 `confirmed`
- 取消后状态变为 `cancelled`

### 5.4 删除

删除由 [delete_service.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/application/services/delete_service.py) 负责。

当前规则：

- 管理员可以删除任意记录
- 若配置允许，提交人也可以删除自己的记录
- 删除为软删除，状态改为 `deleted`

### 5.5 查询与排行

查询与排行全部按游戏昵称工作，不依赖平台身份绑定。

- 查询入口在 [query_service.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/application/services/query_service.py)
- 排行入口在 [ranking_service.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/application/services/ranking_service.py)

统计只基于：

- `matches.status == "confirmed"`
- `matches.match_type == "singles"`

双打查询当前基于：

- `matches.status == "confirmed"`
- `matches.match_type == "doubles"`

当前排行支持的指标别名见 [ranking_service.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/application/services/ranking_service.py) 中的 `METRIC_ALIASES`。

## 6. 核心数据流

```text
群消息 + 图片
  -> main.py 命令入口
  -> MessageParser 提取图片路径
  -> ImageStore 归档图片并计算 SHA256
  -> MultimodalExtractor 调用模型并标准化
  -> IngestService 写入 matches / match_player_stats
  -> ResultRenderer 输出预览
```

双打模式下，`players` 需要输出 4 个对象，并按截图中的玩家顺序排列。系统会将前两名映射到队伍1，后两名映射到队伍2。

确认、取消、删除、查询、排行都不再依赖原图，只依赖数据库中的结构化数据。

## 7. 多模态提取设计

多模态提取逻辑在 [multimodal_extractor.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/infrastructure/llm/multimodal_extractor.py)。

### 7.1 Provider 选择顺序

1. 若配置了 `llm.provider_id`，优先使用配置值
2. 否则回退到当前会话绑定的 provider

### 7.2 模型输入

当前通过 `context.llm_generate(...)` 调用，实际传入：

- `chat_provider_id`
- `prompt`
- `image_urls=[image_path]`
- `system_prompt`
- `temperature=0`

### 7.3 模型输出要求

模型被要求输出 JSON 对象，核心字段如下：

```json
{
  "players": [
    {
      "side": 1,
      "name": "ntr",
      "points_won": 24,
      "winners": 10,
      "serve_points_won": 8,
      "errors": 3,
      "double_faults": 1,
      "net_play_rate": 0.5
    },
    {
      "side": 2,
      "name": "幸(18级)",
      "points_won": 12,
      "winners": 4,
      "serve_points_won": 3,
      "errors": 6,
      "double_faults": 2,
      "net_play_rate": 0.25
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

### 7.4 标准化规则

提取器内部会做这些事：

- 从纯文本、代码块或混杂文本中抽 JSON
- 统一数字字段为整数
- 将百分比解析成 `0-1` 小数
- 将 `HH:MM:SS` 解析为秒数
- 对空昵称登记缺失字段
- 去掉模型传回的 `winner_side` 缺失项
- 根据比赛类型自动推导 `winner_side`

这意味着：

- `winner_side` 是系统推导值，不是模型可信输入
- 若双方点数相同或任一方点数缺失，系统无法判定胜负

### 7.5 失败处理

多模态失败时，当前实现会区分这些常见场景：

- 未配置可用 provider
- provider 不支持图片输入
- provider 额度不足或被限流
- 模型输出不是可解析 JSON

用户可见文案统一由 [result_renderer.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/infrastructure/messaging/result_renderer.py) 输出。

## 8. 持久化设计

### 8.1 数据位置

插件数据保存在：

```text
data/plugin_data/astrbot_plugin_everybody_tennis/
├── tennis.db
└── images/
    └── YYYYMM/
```

### 8.2 数据库模型

当前只保留 3 张核心表：

- `groups`
- `matches`
- `match_player_stats`

没有保留旧版本中的：

- `players`
- `player_aliases`
- `extraction_logs`

### 8.3 表职责

#### `groups`

表示群维度范围，唯一键是：

- `(platform, external_group_id)`

#### `matches`

表示一条比赛记录，承载：

- 状态流转
- 比赛类型
- 提交人信息
- 原图路径和图片哈希
- 原始提取 JSON 与标准化 JSON
- 比赛公共字段
- 各类时间戳

#### `match_player_stats`

表示单场比赛中的单个玩家统计，承载：

- 原始昵称
- 标准化昵称
- 队伍 side 与球员顺位
- 胜负
- 技术指标

### 8.4 当前索引

在 [models.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/infrastructure/persistence/models.py) 中定义的关键索引有：

- `ix_matches_group_status_created`
- `ix_matches_group_status_expires`
- `ix_matches_group_confirmed_at`
- `ix_matches_source_image_sha256`
- `uq_match_player_stats_match_side`

### 8.5 记录号

当前记录号由 [ingest_service.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/application/services/ingest_service.py) 生成，格式为：

- `TEN-YYYYMMDD-HHMMSS-ABCD`

这是用户交互主键，不应替换为数据库自增 ID。

## 9. 状态机

`matches.status` 当前有效值：

- `pending`
- `confirmed`
- `cancelled`
- `expired`
- `deleted`

允许的状态流转：

```text
pending -> confirmed
pending -> cancelled
pending -> expired
pending -> deleted
confirmed -> cancelled
confirmed -> deleted
```

当前没有实现这些逆向流转：

- `cancelled -> confirmed`
- `deleted -> confirmed`
- `expired -> confirmed`

如果后续需要“误取消后恢复”，建议新增显式恢复命令，不要偷偷复用确认逻辑。

## 10. 统计口径

### 10.1 统计主体

当前统计主体是 `match_player_stats.normalized_player_name`。

昵称标准化逻辑见 [text.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/shared/text.py)。

### 10.2 统计范围

当前所有查询和排行都按群隔离，不做跨群合并。

### 10.3 当前指标

个人统计当前输出：

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

群排行当前支持：

- 胜场
- 胜率
- 场次
- 场均得分
- 场均胜球

注意：

- 技术统计已改为平均值，不再展示累计值
- 排行中的“得分”“胜球”别名已映射到平均值指标

## 11. 配置设计

当前配置由 [_conf_schema.json](/home/ubuntu/astrbot_plugin_everybody_tennis/_conf_schema.json) 定义，由 [config_manager.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/infrastructure/config/config_manager.py) 读取。

当前仅保留 5 组配置：

- `basic`
- `llm`
- `storage`
- `ranking`
- `prompts`

### 11.1 当前使用中的配置项

#### `basic`

- `enabled`
- `group_only`
- `allow_submitter_delete`

#### `llm`

- `provider_id`

#### `storage`

- `pending_expire_hours`

#### `ranking`

- `min_matches_for_win_rate`
- `default_top_n`

#### `prompts`

- `extraction_system_prompt`
- `extraction_user_prompt_template`

### 11.2 配置维护原则

- 新增配置时，必须同时修改 `_conf_schema.json` 和 `ConfigManager`
- 未在 `ConfigManager` 暴露的配置，不要直接在业务代码中 `config.get(...)`
- 废弃配置时，优先同时删掉 schema、读取逻辑和 README 文档

## 12. 维护指南

这一节是给后续维护者的直接操作索引。

### 12.1 想改命令行为，看哪里

- 命令注册和参数签名： [main.py](/home/ubuntu/astrbot_plugin_everybody_tennis/main.py)
- 录入行为： [ingest_service.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/application/services/ingest_service.py)
- 确认/取消： [confirmation_service.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/application/services/confirmation_service.py)
- 删除： [delete_service.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/application/services/delete_service.py)
- 文本提示： [result_renderer.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/infrastructure/messaging/result_renderer.py)

### 12.2 想新增一个比赛字段，看哪里

至少需要检查这些位置：

1. [multimodal_extractor.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/infrastructure/llm/multimodal_extractor.py)
   更新提示词 schema、标准化逻辑和缺失字段规则
2. [models.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/infrastructure/persistence/models.py)
   决定字段落在 `matches` 还是 `match_player_stats`
3. [ingest_service.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/application/services/ingest_service.py)
   入库时写入该字段
4. `src/application/dto/`
   若用户要看到它，更新 DTO
5. [query_service.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/application/services/query_service.py) / [ranking_service.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/application/services/ranking_service.py)
   若参与统计，补聚合逻辑
6. [result_renderer.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/infrastructure/messaging/result_renderer.py)
   若需要展示，补文本格式
7. [tests/test_service_flows.py](/home/ubuntu/astrbot_plugin_everybody_tennis/tests/test_service_flows.py)
   增补回归测试

### 12.3 想新增一个排行指标，看哪里

至少要改：

- [ranking_service.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/application/services/ranking_service.py) 的 `METRIC_ALIASES`
- [ranking_service.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/application/services/ranking_service.py) 的 `_metric_value`
- [result_renderer.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/infrastructure/messaging/result_renderer.py) 的指标名称和展示格式
- [README.md](/home/ubuntu/astrbot_plugin_everybody_tennis/README.md) 的使用说明

### 12.4 想改昵称策略，看哪里

- 标准化规则： [text.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/shared/text.py)
- 入库时保存： [ingest_service.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/application/services/ingest_service.py)
- 查询匹配： [query_service.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/application/services/query_service.py)
- 排行聚合： [ranking_service.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/application/services/ranking_service.py)

如果后续要引入“昵称别名表”，建议新增独立表和服务，不要把别名逻辑塞进 `normalize_name()`。

### 12.5 想改确认规则，看哪里

- 自动确认条件： [ingest_service.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/application/services/ingest_service.py)
- 手动确认条件： [confirmation_service.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/application/services/confirmation_service.py)
- 预览提示文案： [result_renderer.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/infrastructure/messaging/result_renderer.py)
- 需求/设计文档： [README.md](/home/ubuntu/astrbot_plugin_everybody_tennis/README.md)、[requirements.md](/home/ubuntu/astrbot_plugin_everybody_tennis/docs/requirements.md)、[technical_design.md](/home/ubuntu/astrbot_plugin_everybody_tennis/docs/technical_design.md)

### 12.6 想改数据库结构，看哪里

- 模型定义： [models.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/infrastructure/persistence/models.py)
- 初始化逻辑： [db.py](/home/ubuntu/astrbot_plugin_everybody_tennis/src/infrastructure/persistence/db.py)
- 测试： [tests/test_service_flows.py](/home/ubuntu/astrbot_plugin_everybody_tennis/tests/test_service_flows.py)

注意：

- 当前项目不做迁移兼容
- schema 发生不兼容变更后，建议直接删除旧库重建

旧库路径通常是：

- `data/plugin_data/astrbot_plugin_everybody_tennis/tennis.db`

## 13. 测试与验证

当前已有的服务流回归测试在 [tests/test_service_flows.py](/home/ubuntu/astrbot_plugin_everybody_tennis/tests/test_service_flows.py)。

当前至少应执行：

```bash
python -m unittest discover -s tests -p 'test_*.py'
python -m compileall main.py src tests
```

建议后续新增测试时优先覆盖：

- 录入自动确认
- `pending -> confirmed`
- `confirmed -> cancelled`
- 删除权限
- 新增统计字段或排行指标
- provider 错误提示分支

## 14. 已知简化与后续扩展点

当前实现有一些明确保留的简化：

- 最近比赛查询会按每条记录单独查一次对手，数据量小的群场景可以接受
- 重复检测目前只基于图片哈希提示，不做复杂判重
- 没有管理端待确认列表
- 没有人工修正入口
- 没有时间范围筛选
- 没有别名合并

后续如果扩展，请优先遵守这些原则：

- `main.py` 继续保持薄
- 业务逻辑继续下沉到 service
- 用户提示统一走 renderer
- 配置统一走 `ConfigManager`
- 不要把数据库结构性判断分散到多个命令函数里

## 15. 结论

当前这套结构已经从“概念原型”收敛为“可维护的小型工程”：

- 边界清楚
- 关键状态流明确
- 文档与代码基本一致
- 允许后续在不推翻架构的前提下继续扩展

后续维护时，优先守住三件事：

- 文档和代码一致
- 统计口径一致
- 新增能力时不要破坏现有服务边界

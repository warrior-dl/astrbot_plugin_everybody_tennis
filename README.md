# 大众网球战绩插件

`astrbot_plugin_everybody_tennis` 是一个 AstrBot 群聊插件，用来收集网球游戏对战截图，借助多模态 LLM 提取结构化比赛数据，并沉淀个人战绩与群排行。

当前版本已经具备首版核心闭环：

- 提交截图并默认直接入库
- 取消已录入记录
- 删除记录
- 按游戏昵称查询个人战绩
- 按游戏昵称查询最近比赛
- 查询群排行

## 项目目标

插件面向群聊使用场景：

1. 群友发送指令并附带比赛截图。
2. 插件调用多模态模型提取双方比赛数据。
3. 插件回显识别预览。
4. 字段完整且可判定胜负时自动入库；字段缺失时保留为待确认记录。
5. 后续可查询个人战绩、最近比赛和群排行。

设计文档见：

- [需求文档](./docs/requirements.md)
- [技术设计文档](./docs/technical_design.md)

## 当前实现状态

已实现：

- `/网球 帮助`
- `/网球 录入`
- `/网球 确认 <记录号>`
- `/网球 取消 <记录号>`
- `/网球 删除 <记录号>`
- `/网球 战绩 <游戏昵称>`
- `/网球 最近 <游戏昵称> [条数]`
- `/网球 排行 [指标] [人数]`

已落地的基础设施：

- 工程化分层目录结构
- `_conf_schema.json` 配置分组
- SQLite 持久化
- 图片本地归档
- 自动入库与撤销状态流转
- 基于游戏昵称的统计聚合

尚未完成：

- `@用户` 查询他人战绩
- 时间范围筛选
- 管理员查看待确认列表
- 人工修正识别结果
- 更精细的重复记录处理
- 图片榜单 / 报表渲染

## 目录结构

```text
astrbot_plugin_everybody_tennis/
├── main.py
├── metadata.yaml
├── requirements.txt
├── _conf_schema.json
├── README.md
├── docs/
└── src/
    ├── application/
    ├── infrastructure/
    └── shared/
```

`main.py` 只负责插件注册、生命周期和命令委托，业务逻辑下沉到 `src/`。

## 安装与运行

### 1. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

当前插件额外依赖：

- `SQLAlchemy`
- `aiosqlite`

### 2. 安装到 AstrBot 插件目录

将本项目放到 AstrBot 插件目录，确保 AstrBot 能加载：

```text
data/plugins/astrbot_plugin_everybody_tennis/
```

或按你的实际插件部署方式接入。

### 3. 配置插件

插件使用 `_conf_schema.json` 暴露配置项，当前分组如下：

- `basic`
- `llm`
- `storage`
- `ranking`
- `prompts`

关键配置：

- `basic.enabled`：启用插件
- `basic.group_only`：仅允许群聊使用
- `basic.allow_submitter_delete`：允许提交人删除自己的记录
- `llm.provider_id`：指定用于截图提取的多模态 Provider，必须选择支持看图的聊天模型
- `storage.pending_expire_hours`：待确认记录过期时间
- `ranking.min_matches_for_win_rate`：胜率榜最少比赛场次

如果执行 `/网球 录入` 时出现“Provider 不支持图片输入”或类似 `image_url` 反序列化错误，通常表示这里没有配置成支持多模态图片输入的模型。

### 4. 数据存储位置

插件运行后会把数据写入：

```text
data/plugin_data/astrbot_plugin_everybody_tennis/
├── tennis.db
└── images/
```

其中：

- `tennis.db` 为 SQLite 数据库
- `images/` 保存归档后的比赛截图

如果你本地跑过旧版本，建议删除旧的 `data/plugin_data/astrbot_plugin_everybody_tennis/tennis.db` 后再启动，让当前精简后的 schema 直接重建。

## 使用说明

### 1. 提交比赛截图

在群聊发送：

```text
/网球 录入
```

并附带一张比赛截图。

插件会：

- 解析图片消息
- 保存原图
- 调用多模态模型提取 JSON
- 若字段完整则直接入库
- 若字段缺失则保留为 `pending`
- 返回识别预览和记录号

### 2. 取消或补确认

大多数完整截图会自动入库。如需撤销，可继续：

```text
/网球 取消 TEN-20260405-0001
```

只有字段缺失的记录，才需要再执行：

```text
/网球 确认 TEN-20260405-0001
```

### 3. 删除记录

```text
/网球 删除 TEN-20260405-0001
```

当前规则：

- 管理员可以删除
- 提交人本人是否可删由配置项 `allow_submitter_delete` 决定

删除为软删除，后续统计会自动忽略该记录。

### 4. 查询数据

个人战绩：

```text
/网球 战绩 ntr
```

最近比赛：

```text
/网球 最近 ntr
/网球 最近 ntr 3
```

群排行：

```text
/网球 排行
/网球 排行 胜率
/网球 排行 场均得分 5
```

当前支持的排行指标：

- `胜场`
- `胜率`
- `场次`
- `场均得分`
- `场均胜球`

## 识别流程说明

当前录入链路如下：

```text
群消息图片
  -> MessageParser 提取图片
  -> ImageStore 保存图片并计算 SHA256
  -> MultimodalExtractor 调用 LLM 提取 JSON
  -> 完整记录直接写入 confirmed
  -> 不完整记录写入 pending
  -> 用户可取消，或对 pending 记录补确认
```

之所以保留确认入口，是因为图片识别天然存在误差。当前策略是：完整记录自动入库，只有字段缺失时才进入显式确认流程。

## 数据模型概览

当前核心表：

- `groups`
- `matches`
- `match_player_stats`

记录状态：

- `pending`
- `confirmed`
- `cancelled`
- `expired`
- `deleted`

## 开发说明

### 本地验证

当前开发过程中已经验证过：

- `python -m compileall main.py src`
- SQLite schema 初始化
- 自动入库 / 补确认 / 取消 / 删除状态流
- 按游戏昵称的战绩 / 最近比赛 / 群排行聚合

### 注意事项

- 插件默认按群维度建模，不做跨群身份合并
- 统计仅基于 `confirmed` 且未删除的记录
- 当前版本无需绑定昵称，查询时直接指定游戏内昵称
- 真实多模态识别效果依赖 AstrBot 当前配置的 Provider 能否处理图片输入

## 后续计划

下一阶段优先项：

- 接真实 AstrBot 宿主做端到端联调
- 提升多模态提取稳定性
- 支持管理员查看待确认记录
- 支持人工修正识别结果
- 支持按时间范围筛选
- 支持更丰富的排行和图片报表

## 参考

- [AstrBot 仓库](https://github.com/AstrBotDevs/AstrBot)
- [AstrBot 插件开发文档（中文）](https://docs.astrbot.app/dev/star/plugin-new.html)
- [AstrBot 插件开发文档（英文）](https://docs.astrbot.app/en/dev/star/plugin-new.html)

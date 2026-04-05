# 全民网球战绩插件

`astrbot_plugin_everybody_tennis` 是一个 AstrBot 群聊插件，用来收集网球游戏对战截图，借助多模态 LLM 提取结构化比赛数据，并沉淀个人战绩与群排行。

当前版本已经具备首版核心闭环：

- 绑定游戏昵称
- 提交截图录入待确认记录
- 确认或取消记录
- 删除记录
- 查询个人战绩
- 查询最近比赛
- 查询群排行

## 项目目标

插件面向群聊使用场景：

1. 群友发送指令并附带比赛截图。
2. 插件调用多模态模型提取双方比赛数据。
3. 插件生成待确认记录，避免误识别直接污染统计。
4. 用户确认后入库。
5. 后续可查询个人战绩、最近比赛和群排行。

设计文档见：

- [需求文档](./docs/requirements.md)
- [技术设计文档](./docs/technical_design.md)

## 当前实现状态

已实现：

- `/网球 帮助`
- `/网球 绑定 <游戏昵称>`
- `/网球 别名`
- `/网球 录入`
- `/网球 确认 <记录号>`
- `/网球 取消 <记录号>`
- `/网球 删除 <记录号>`
- `/网球 战绩`
- `/网球 最近 [条数]`
- `/网球 排行 [指标] [人数]`

已落地的基础设施：

- 工程化分层目录结构
- `_conf_schema.json` 配置分组
- SQLite 持久化
- 图片本地归档
- 待确认状态流转
- 身份映射与别名绑定

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
    ├── domain/
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
- `pydantic`

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
- `debug`

关键配置：

- `basic.enabled`：启用插件
- `basic.group_only`：仅允许群聊使用
- `basic.allow_submitter_delete`：允许提交人删除自己的记录
- `llm.provider_id`：指定用于截图提取的多模态 Provider
- `storage.pending_expire_hours`：待确认记录过期时间
- `ranking.min_matches_for_win_rate`：胜率榜最少比赛场次

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

## 使用说明

### 1. 先绑定游戏昵称

截图里识别到的是游戏昵称，不一定等于群昵称，所以建议先绑定：

```text
/网球 绑定 ntr
/网球 别名
```

### 2. 提交比赛截图

在群聊发送：

```text
/网球 录入
```

并附带一张比赛截图。

插件会：

- 解析图片消息
- 保存原图
- 调用多模态模型提取 JSON
- 生成一条 `pending` 记录
- 返回识别预览和记录号

### 3. 确认或取消

收到预览后，可继续：

```text
/网球 确认 TEN-20260405-0001
/网球 取消 TEN-20260405-0001
```

只有确认后的记录才会进入正式统计。

### 4. 删除记录

```text
/网球 删除 TEN-20260405-0001
```

当前规则：

- 管理员可以删除
- 提交人本人是否可删由配置项 `allow_submitter_delete` 决定

删除为软删除，后续统计会自动忽略该记录。

### 5. 查询数据

个人战绩：

```text
/网球 战绩
```

最近比赛：

```text
/网球 最近
/网球 最近 3
```

群排行：

```text
/网球 排行
/网球 排行 胜率
/网球 排行 得分 5
```

当前支持的排行指标：

- `胜场`
- `胜率`
- `场次`
- `得分`
- `胜球`

## 识别流程说明

当前录入链路如下：

```text
群消息图片
  -> MessageParser 提取图片
  -> ImageStore 保存图片并计算 SHA256
  -> MultimodalExtractor 调用 LLM 提取 JSON
  -> IdentityService 解析昵称绑定
  -> pending 记录写入 SQLite
  -> 用户确认 / 取消
  -> confirmed 记录进入正式统计
```

之所以要求确认，是因为图片识别天然存在误差。首版优先保证统计可信度，而不是追求零交互自动入库。

## 数据模型概览

当前核心表：

- `groups`
- `players`
- `player_aliases`
- `matches`
- `match_player_stats`
- `extraction_logs`

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
- 昵称绑定 / 别名查询
- 录入待确认链路
- 确认 / 取消 / 删除状态流
- 个人战绩 / 最近比赛 / 群排行聚合

### 注意事项

- 插件默认按群维度建模，不做跨群身份合并
- 统计仅基于 `confirmed` 且未删除的记录
- 若未绑定昵称，个人查询和确认流程可能无法完成
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

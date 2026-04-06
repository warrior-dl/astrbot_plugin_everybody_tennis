# 大众网球战绩插件

`astrbot_plugin_everybody_tennis` 是一个 AstrBot 群聊插件，用来收集网球游戏对战截图，借助多模态 LLM 提取结构化比赛数据，并沉淀群内战绩与排行。

当前版本已经打通主链路：

- 提交比赛截图
- 提交双打比赛截图
- 自动提取结构化数据
- 完整记录自动入库
- 缺失字段记录进入待确认
- 按游戏昵称查询战绩和最近比赛
- 查看群排行
- 撤销或删除记录

相关文档：

- [需求文档](./docs/requirements.md)
- [技术设计文档](./docs/technical_design.md)

## 当前版本说明

当前版本采用这些明确规则：

- 数据按群隔离，不做跨群总榜
- 统计按游戏昵称聚合，不做平台账号绑定
- `winner_side` 由系统根据双方 `points_won` 自动推导
- 双打按前两名一队、后两名一队建模
- 完整记录默认自动确认，不强制所有记录手动确认
- 正式统计只基于 `confirmed` 记录

这意味着：

- 当前无需绑定昵称
- 查询时直接指定游戏昵称
- 若图片识别结果不完整，才需要再执行确认命令
- 双打当前支持录入、战绩查询和最近比赛，双打排行后续补

## 当前已实现

命令：

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

基础设施：

- 工程化分层目录结构
- `_conf_schema.json` 配置分组
- SQLite 持久化
- 图片本地归档
- 多模态提取与标准化
- 单打 / 双打比赛类型隔离
- 自动确认 / 待确认 / 取消 / 删除状态流
- 按游戏昵称的统计聚合

暂未实现：

- 双打排行
- 时间范围筛选
- 管理员查看待确认列表
- 人工修正识别结果
- 更细的重复记录处理
- 图片化榜单 / 报表渲染
- 别名映射和身份绑定

## 目录结构

```text
astrbot_plugin_everybody_tennis/
├── main.py
├── metadata.yaml
├── requirements.txt
├── _conf_schema.json
├── README.md
├── docs/
├── src/
│   ├── application/
│   ├── infrastructure/
│   └── shared/
└── tests/
```

`main.py` 只负责插件注册、生命周期和命令分发，主要业务逻辑下沉到 `src/`。

## 安装与运行

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

当前插件额外依赖：

- `SQLAlchemy`
- `aiosqlite`

### 2. 放入 AstrBot 插件目录

将本项目放到 AstrBot 插件目录，例如：

```text
data/plugins/astrbot_plugin_everybody_tennis/
```

### 3. 配置插件

插件使用 `_conf_schema.json` 暴露配置项，当前分组为：

- `basic`
- `llm`
- `storage`
- `ranking`
- `prompts`

关键配置：

- `basic.enabled`
- `basic.group_only`
- `basic.allow_submitter_delete`
- `llm.provider_id`
- `storage.pending_expire_hours`
- `ranking.min_matches_for_win_rate`
- `ranking.default_top_n`

其中 `llm.provider_id` 必须指向一个支持图片输入的聊天模型。

如果执行 `/网球 录入` 时出现“Provider 不支持图片输入”或类似 `image_url` 反序列化错误，通常表示当前 provider 不支持多模态图片输入。

### 4. 数据存储位置

插件运行后会写入：

```text
data/plugin_data/astrbot_plugin_everybody_tennis/
├── tennis.db
└── images/
```

其中：

- `tennis.db` 为 SQLite 数据库
- `images/` 保存归档后的比赛截图

如果你本地跑过旧版本，建议删除旧的 `data/plugin_data/astrbot_plugin_everybody_tennis/tennis.db` 后再启动，让当前 schema 直接重建。

## 使用说明

### 1. 录入比赛截图

在群聊发送：

```text
/网球 录入
```

并附带一张比赛截图。

插件会：

- 解析图片消息
- 保存原图
- 调用多模态模型提取 JSON
- 计算双方胜负
- 若字段完整则直接入库
- 若字段缺失则保留为 `pending`
- 返回识别预览和记录号

双打录入使用：

```text
/网球 双打录入
```

当前双打规则：

- 固定识别 4 名玩家
- 前两名为队伍1，后两名为队伍2
- 以同队两人的 `points_won` 总和判定胜负
- `发球最高球速（km/h）` 仅在双打提取

### 2. 确认或取消

大多数完整截图会自动入库。如需撤销，可发送：

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
- 提交人本人是否可删由 `basic.allow_submitter_delete` 控制

删除为软删除，后续统计会自动忽略该记录。

### 4. 查询数据

个人战绩：

```text
/网球 战绩 ntr
```

双打战绩：

```text
/网球 双打战绩 幸
```

最近比赛：

```text
/网球 最近 ntr
/网球 最近 ntr 3
```

双打最近：

```text
/网球 双打最近 幸
/网球 双打最近 幸 3
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

## 识别与统计说明

当前录入链路如下：

```text
群消息图片
  -> MessageParser 提取图片
  -> ImageStore 保存图片并计算 SHA256
  -> MultimodalExtractor 调用 LLM 提取 JSON
  -> 系统根据 points_won 自动推导 winner_side
  -> 完整记录写入 confirmed
  -> 不完整记录写入 pending
  -> 用户可取消，或对 pending 记录补确认
```

当前统计说明：

- 单打统计仅基于 `confirmed` 且未删除的 `singles` 记录
- 当前双打录入已落库，但不进入现有单打查询/排行
- 查询和排行按标准化后的游戏昵称聚合
- 技术指标以平均值为主，不再展示累计值

## 开发与验证

当前开发过程中已经验证过：

- `python -m unittest discover -s tests -p 'test_*.py'`
- `python -m compileall main.py src tests`

当前已有的回归测试覆盖：

- 自动确认录入
- 双打录入与单打统计隔离
- `pending -> confirmed`
- 查询与排行聚合
- 取消后的统计排除

## 维护提示

后续维护时，优先保持这些基线不变：

- 录入主链路仍以“自动确认 + 待确认补充”为主
- 查询入口仍然是“指定游戏昵称”
- 胜负仍然由系统根据点数判定
- 正式统计只基于 `confirmed`

如果后续要引入身份绑定、别名映射、跨群排行或时间范围筛选，建议先同步更新需求文档和技术设计文档，再动代码。

## 参考

- [AstrBot 仓库](https://github.com/AstrBotDevs/AstrBot)
- [AstrBot 插件开发文档（中文）](https://docs.astrbot.app/dev/star/plugin-new.html)
- [AstrBot 插件开发文档（英文）](https://docs.astrbot.app/en/dev/star/plugin-new.html)

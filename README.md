# AstrBot JM 下载器

![插件封面](logo.png)

在 QQ 中搜索 JM 内容、查看作品信息，并将指定章节下载为 PDF，由机器人发送给你。支持群聊和私聊，提供下载次数限制、群开关与黑名单管理。

首次使用可以按下面的步骤直接安装；使用过 NoneBot2 原插件的用户，也可以[从原插件迁移配置](#从原插件迁移配置)，导入账号设置、群配置和用户数据。

## 功能

- **搜索与查询**：按关键词搜索、翻页浏览，按 JM 号查看信息，查询封面经过模糊处理。
- **PDF 下载**：下载指定章节并发送 PDF，群聊可指定文件夹。
- **群管理**：控制哪些群可以使用，管理群黑名单，设置屏蔽 ID 和标签。
- **配置迁移**：从 NoneBot2 原插件导入配置、管理员、群开关和用户剩余次数。

## 快速开始

### 1. 安装插件

需要 **AstrBot 4.16+（4.x）**，并通过 **OneBot v11** 接入 QQ，例如使用 NapCat。对应的平台适配器是 `aiocqhttp`。

在 AstrBot 管理面板“插件 → 安装插件”中填写仓库地址：

```text
https://github.com/YuuKi-Z/astrbot_plugin_jmdownloader
```

也可以从 [Releases](https://github.com/YuuKi-Z/astrbot_plugin_jmdownloader/releases) 下载 ZIP，通过面板上传安装。依赖会由 AstrBot 自动安装。

### 2. 配置使用权限

在插件配置中，将自己的 QQ 号加入 `jmcomic_superusers`，或使用已设置为 AstrBot 管理员的账号。后文的“超级用户”指这两类账号。

用户名和密码默认留空，表示不登录 JM。如需使用账号，在 `jmcomic_username` 和 `jmcomic_password` 中填写；登录会在首次请求时执行。

### 3. 启用群聊

**群聊默认关闭。** 超级用户在需要使用插件的群中发送：

```text
开启jm
```

也可以将 `jmcomic_allow_groups` 设为 `true`，让未单独设置过的群默认启用。私聊可以直接使用。

### 4. 开始使用

先发送 `jm帮助` 查看命令，再尝试：

```text
jm搜索 关键词
jm下一页
jm查询 JM号
jm下载 JM号
jm次数
```

将“关键词”和“JM号”替换为实际内容。普通用户默认每周可下载 **5 次**，周一零点重置；超级用户不消耗次数。Docker 部署时，请同时检查[文件上传设置](#docker-文件上传)。

## 命令说明

命令与第一个参数之间**加空格、不加空格都可以**，例如 `jm搜索 若叶睦` 和 `jm搜索若叶睦`、`jm设置文件夹 文档` 和 `jm设置文件夹文档`。关键词和文件夹名称内部的空格会保留；多个群号、ID 或标签之间仍需用空格分隔。

命令支持 `JM` 大写、可选 `/` 前缀，也可以直接发送。`jm下一页` 和 `jm 下一页` 均可使用；关闭群聊也支持 `关闭jm 确认` 和 `关闭jm确认`。

| 命令 | 作用 / 权限 |
| --- | --- |
| `jm下载 JM号` | 下载指定章节并发送 PDF |
| `jm查询 JM号` | 查询信息，发送模糊封面 |
| `jm搜索 关键词`、`jm下一页` | 搜索及翻页，搜索记录 30 分钟内有效 |
| `jm次数`、`jm帮助` | 查询剩余下载次数、查看帮助 |
| `jm设置文件夹 名称` | 查找或创建群文件夹；超级用户、群主、群管理员可用 |
| `jm拉黑 @成员`、`jm解除拉黑 @成员`、`jm黑名单` | 管理群黑名单；超级用户、群主、群管理员可用，管理员仅能操作普通成员 |
| `jm启用群 群号...`、`jm禁用群 群号...` | 批量设置群开关；超级用户可用 |
| `开启jm` | 启用当前群；超级用户可用 |
| `关闭jm` | 关闭当前群；超级用户、群主、群管理员可用，两分钟内发送 `确认`，或直接发送 `关闭jm 确认` |
| `jm禁用id JM号...`、`jm禁用tag 标签...` | 追加屏蔽规则；超级用户可用 |

未启用的群和黑名单成员无法使用下载、查询、搜索。普通群成员尝试下载被屏蔽的内容时，会被加入该群 JM 黑名单，并尝试禁言 24 小时；机器人拥有管理权限时禁言才会成功。这项规则沿用原插件行为。

## 配置说明

首次安装时通常只需设置管理员、按需填写登录信息，并启用目标群。以下默认值沿用 [原插件 v1.0.4 配置](https://github.com/Misty02600/nonebot-plugin-jmdownloader/blob/v1.0.4/nonebot_plugin_jmdownloader/config.py)。

| 配置项 | 默认值 | 用途 |
| --- | --- | --- |
| `jmcomic_username` | 空 | JM 登录用户名；与密码都填写后才会登录 |
| `jmcomic_password` | 空 | JM 登录密码 |
| `jmcomic_allow_groups` | `false` | 未单独设置过的群是否默认启用 |
| `jmcomic_user_limits` | `5` | 普通用户每周下载次数 |
| `jmcomic_results_per_page` | `20` | 每次展示的搜索结果数 |
| `jmcomic_thread_count` | `10` | 图片下载线程数 |
| `jmcomic_proxies` | `system` | 代理设置；`system` 表示使用系统代理 |
| `jmcomic_log` | `false` | 是否开启 JMComic 日志 |
| `jmcomic_modify_real_md5` | `false` | 是否修改上传副本的 MD5 |
| `jmcomic_blocked_message` | `猫猫吃掉了一个不豪吃的本子` | 被屏蔽搜索结果的提示 |

AstrBot 额外配置：

| 配置项 | 默认值 | 用途 |
| --- | --- | --- |
| `jmcomic_superusers` | `[]` | 超级用户 QQ 号列表；AstrBot 管理员同时有效 |
| `timezone` | `Asia/Shanghai` | 下载次数重置与缓存清理的时区，与原插件的默认维护时区一致 |
| `onebot_file_base` | 空 | OneBot 协议端看到的 AstrBot data 目录；双方路径相同时留空 |

初始屏蔽 ID 和标签沿用原版公开默认值。每周一 00:00 重置下载次数，每日 03:00 清理下载缓存；下载或上传失败会退还本次扣除的次数。配置和用户数据保存在 AstrBot 的 `data` 目录，更新插件时保留。

## Docker 文件上传

如果下载成功但 PDF 发送失败，请先确认 NapCat 等 OneBot 协议端能读取生成的文件。

建议将同一个宿主机数据目录挂载到 AstrBot 与 NapCat 中，并让双方使用相同的容器路径，例如 `/AstrBot/data`。此时 `onebot_file_base` 留空即可。

如果双方挂载路径不同，填写**协议端看到的 AstrBot data 目录**，例如 `/shared/data`。双方仍须实际共享同一目录，单独填写路径不能代替共享挂载。

## 从原插件迁移配置

适用于已经使用 [NoneBot2 JM 下载器 v1.0.4](https://github.com/Misty02600/nonebot-plugin-jmdownloader/tree/v1.0.4) 的用户。首次安装的新用户可直接使用默认配置。

迁移可以导入全部 10 个 `JMCOMIC_*` 配置项、`SUPERUSERS`，以及群开关、群黑名单、群文件夹 ID、用户剩余次数和屏蔽规则。原 JSON 中的扩展字段也会保留，首次加载不会重置已迁移的剩余次数。

### 1. 准备原配置与数据

先备份原项目的 `.env*`、`pyproject.toml`、插件源码，以及 `nonebot_plugin_localstore` 的数据和配置目录。原插件默认数据文件位于运行 NoneBot 的用户目录：

```text
~/.local/share/nonebot2/nonebot_plugin_jmdownloader/jmcomic_data.json
```

如果设置过 `LOCALSTORE_*`，请使用实际存储位置。迁移前停止 AstrBot 中的本插件，避免迁移时已有数据被运行中的插件写回。

### 2. 执行迁移

在 **NoneBot 原虚拟环境**中执行以下命令，将示例路径替换为实际路径。该环境需要 `python-dotenv`；原插件环境通常已安装此依赖。

```bash
/path/to/nonebot/.venv/bin/python /path/to/plugin/migrate.py \
  --env /path/to/nonebot/.env \
  --env /path/to/nonebot/.env.prod \
  --source-data /path/to/nonebot/data/jmcomic_data.json \
  --astrbot-data /path/to/astrbot/data
```

按原项目使用的配置文件填写 `--env`，可以重复指定，后面的文件优先；没有 `.env.prod` 时删去对应参数。`--astrbot-data` 指向 AstrBot 的 **data 目录**，不是插件目录。迁移只读取原文件，不启动或修改原机器人。

如果已有导出的 JSON 迁移快照，也可使用：

```bash
python migrate.py --snapshot /private/migration-export.json --astrbot-data /path/to/astrbot/data
```

目标配置或数据已经存在时，默认拒绝覆盖。确认需要替换后，在命令末尾加上 `--overwrite`；脚本会先备份已有目标文件。

### 3. 加载并检查

迁移完成后重新加载插件，检查插件配置、群开关和 `jm次数`。登录信息不会出现在迁移命令的输出中。

| 迁移内容 | AstrBot 保存位置 |
| --- | --- |
| 原配置、超级用户 | `data/config/astrbot_plugin_jmdownloader_config.json` |
| 群配置、用户次数、屏蔽规则及扩展字段 | `data/plugin_data/astrbot_plugin_jmdownloader/jmcomic_data.json` |
| 完整原始快照 | 同一数据目录的 `nonebot_migration_snapshot.json` |

请自行保留原备份。真实 `.env`、密码、迁移快照和用户数据应存放在私人目录，不要提交到公开仓库或打入发布 ZIP。

## 开发与打包

插件使用 `jmcomic 2.7.7`，兼容 JM API 中带 UTF-8 BOM 的响应。开发验证需额外安装 `python-dotenv`、`pikepdf` 和 `ruff`。

```bash
python -m unittest discover -s tests -v
ruff check .
ruff format --check .
python scripts/build_release.py
```

打包脚本使用明确的文件清单，只打包源码、封面和说明文件。测试使用模拟协议端，不向实际 QQ 用户发送消息。已在 AstrBot 4.28.2 上验证。

## 来源与许可

移植自 [Misty02600/nonebot-plugin-jmdownloader v1.0.4](https://github.com/Misty02600/nonebot-plugin-jmdownloader/tree/v1.0.4)，原项目 MIT 许可和版权声明见 [LICENSE](LICENSE)、[NOTICE](NOTICE)。

下载库：[JMComic-Crawler-Python](https://github.com/hect0x7/JMComic-Crawler-Python)。插件开发参考：[AstrBot 官方指南](https://docs.astrbot.app/dev/star/plugin-new.html)。

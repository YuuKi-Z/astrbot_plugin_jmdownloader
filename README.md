# AstrBot JM 下载器

![插件封面](logo.png)

移植自 [Misty02600/nonebot-plugin-jmdownloader v1.0.4](https://github.com/Misty02600/nonebot-plugin-jmdownloader/tree/v1.0.4)，支持搜索、查询、PDF 下载、群管理及旧配置导入。原项目 MIT 许可和版权声明见 LICENSE、NOTICE。

使用 **jmcomic 2.7.7** 下载库，通过本插件专用客户端兼容接口响应中的 UTF-8 BOM。下载库项目：[JMComic-Crawler-Python](https://github.com/hect0x7/JMComic-Crawler-Python)。

支持 AstrBot 4.16+ / OneBot v11（`aiocqhttp`，如 NapCat）。按 [AstrBot 官方插件开发指南](https://docs.astrbot.app/dev/star/plugin-new.html) 适配，已在 AstrBot 4.28.2 上验证。

## 安装

在 AstrBot 管理面板“插件 → 安装插件”中填写仓库地址：

```text
https://github.com/YuuKi-Z/astrbot_plugin_jmdownloader
```

也可以从 [Releases](https://github.com/YuuKi-Z/astrbot_plugin_jmdownloader/releases) 下载 ZIP，通过面板上传安装。AstrBot 会安装 `requirements.txt` 中的依赖。

在插件配置中填写登录信息或导入旧配置。登录在首次请求时执行，网络故障不会阻止 AstrBot 加载插件。配置和数据保存在 AstrBot 的 `data` 目录，更新插件时保留。

## 默认配置

以下 10 项沿用 [原插件 v1.0.4 默认配置](https://github.com/Misty02600/nonebot-plugin-jmdownloader/blob/v1.0.4/nonebot_plugin_jmdownloader/config.py)。用户名、密码为空表示不登录；原插件的 `None` 用 AstrBot 配置界面的空字符串表示。

| 配置项 | 默认值 |
| --- | --- |
| `jmcomic_log` | `false` |
| `jmcomic_proxies` | `system` |
| `jmcomic_thread_count` | `10` |
| `jmcomic_username` | 空 |
| `jmcomic_password` | 空 |
| `jmcomic_allow_groups` | `false` |
| `jmcomic_user_limits` | `5` |
| `jmcomic_modify_real_md5` | `false` |
| `jmcomic_blocked_message` | `猫猫吃掉了一个不豪吃的本子` |
| `jmcomic_results_per_page` | `20` |

AstrBot 额外配置：`jmcomic_superusers=[]`、`onebot_file_base=""`。维护时区 `timezone=Asia/Shanghai`，与原插件使用的 NoneBot APScheduler 默认时区一致。初始屏蔽 ID 和标签同样沿用原版公开默认值；群开关、用户次数和黑名单由各安装实例自行保存。

## 保留旧配置

不要将真实 `.env`、登录密码、迁移快照或用户数据放进插件源码、Git 或安装 ZIP。

先备份原项目 `.env*`、`pyproject.toml`、实际安装的插件源码和 `nonebot_plugin_localstore` 的数据/配置目录。旧版默认数据文件位于运行 NoneBot 的用户目录：

```text
~/.local/share/nonebot2/nonebot_plugin_jmdownloader/jmcomic_data.json
```

如果设置过 `LOCALSTORE_*`，以实际存储位置为准。在 **NoneBot 原虚拟环境**中执行下面的导入命令，其已有 `python-dotenv` 依赖。导入只读源文件，不启动或修改旧机器人：

```bash
/path/to/nonebot/.venv/bin/python /path/to/plugin/migrate.py \
  --env /path/to/nonebot/.env \
  --env /path/to/nonebot/.env.prod \
  --source-data /path/to/nonebot/data/jmcomic_data.json \
  --astrbot-data /path/to/astrbot/data
```

也支持已导出的 JSON 快照：

```bash
python migrate.py --snapshot /private/migration-export.json --astrbot-data /path/to/astrbot/data
```

目标配置已经存在时默认拒绝覆盖；显式使用 `--overwrite` 会先备份目标文件。迁移命令的输出仅包含路径、数量和校验状态，不包含密码。

| 原有设置/数据 | AstrBot 保存位置或处理方式 |
| --- | --- |
| 全部 10 个 `JMCOMIC_*` 配置项 | `data/config/astrbot_plugin_jmdownloader_config.json`，沿用原键名 |
| `SUPERUSERS` | 插件配置 `jmcomic_superusers`；AstrBot 自身管理员也有效 |
| 群开关、群黑名单、群文件夹 ID | `data/plugin_data/astrbot_plugin_jmdownloader/jmcomic_data.json` |
| 用户剩余次数、屏蔽 ID/tag、未知扩展字段 | 原 JSON 完整保留，不将空列表重置成默认值 |
| 原始导入快照 | 同一数据目录的 `nonebot_migration_snapshot.json`，权限 600 |
| 定时维护记录 | 同一数据目录的 `maintenance.json` |
| 下载缓存和上传副本 | 同一数据目录的 `cache/` 和 `uploads/` |

`JMCOMIC_USER_LIMITS` 是**每周**限额，周一 00:00 按插件 `timezone` 重置。每日 03:00 清理下载缓存；首次启动不清空已迁移的剩余次数。运行中中断下载或上传失败会退还本次扣除的次数。请自行保留原 `.env*` 备份。

## 命令

原命令仍可使用，支持 `JM` 大写、可选 `/` 前缀及不带前缀的旧用法。搜索关键词和管理参数请用空格分隔，例如 `jm搜索 关键词`。`jm下一页` 和 `jm 下一页` 均支持。

| 命令 | 权限/作用 |
| --- | --- |
| `jm下载 123456` | 下载指定章节并发送 PDF |
| `jm查询 123456` | 查询信息，发送模糊封面 |
| `jm搜索 关键词`、`jm下一页` | 搜索及翻页，30 分钟内有效，同一会话内隔离 |
| `jm次数`、`jm帮助` | 查询剩余次数、帮助 |
| `jm设置文件夹 名称` | 超级用户、群主、群管理员；查找或创建群文件夹 |
| `jm拉黑 @成员`、`jm解除拉黑 @成员`、`jm黑名单` | 超级用户、群主、群管理员；管理员仅能操作普通成员 |
| `jm启用群 群号...`、`jm禁用群 群号...` | 超级用户；批量设置群开关 |
| `开启jm` | 超级用户；启用当前群 |
| `关闭jm` | 超级用户、群主、群管理员；同一用户在两分钟内发送 `确认`，或直接 `关闭jm 确认` |
| `jm禁用id 编号...`、`jm禁用tag 标签...` | 超级用户；追加屏蔽规则 |

未启用的群和黑名单成员不触发下载/查询/搜索。私聊沿用旧版的可用行为；超级用户不消耗次数。普通群成员尝试下载被屏蔽内容时，沿用旧插件的禁言 24 小时并加入该群 JM 黑名单的规则；只有机器人具备管理权限时禁言才会成功。

本插件使用 AstrBot 正则事件注册，保留 NoneBot `COMMAND_START=[""]` 的行为，不需要改动 AstrBot 全局唤醒前缀。命令列表见 `jm帮助`。

## Docker 文件上传

OneBot 协议端必须能读取 PDF。建议将同一个宿主机数据目录挂载到 AstrBot 与 NapCat 中，并让两端使用相同的容器路径（例如 `/AstrBot/data`），此时 `onebot_file_base` 留空即可。如果两端挂载路径不同，填写**协议端看到的 AstrBot data 目录**，例如 `/shared/data`。路径映射不能替代实际的共享挂载。

`jmcomic_modify_real_md5` 只修改本次上传副本，不破坏原缓存 PDF。上传副本在协议 API 返回后删除；缓存清理等待 JM 线程完成，不影响仍在上传的副本。

## 验证与打包

```bash
python -m unittest discover -s tests -v
ruff check .
ruff format --check .
python scripts/build_release.py
```

打包脚本只包含明确列出的源码、封面和说明文件，不包含配置、密码、备份、用户数据或虚拟环境。测试使用模拟协议端，不向实际 QQ 用户发送消息。运行测试还需安装 `python-dotenv`、`pikepdf`；代码检查需安装 `ruff`。

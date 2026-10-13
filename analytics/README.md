# SaiyuDoc · Umami 统计

博客主地址 `https://www.wangsaiyu.com/`，根域名同样直接访问。两个域名统一上报到同一 Umami 网站，不对博客主机作迁移。

## 线上资源

- Umami 3.4.0：`https://stats.wangsaiyu.com`，管理入口 `/login`。
- 公开入口：`https://stats.wangsaiyu.com/`，自动进入原生 Umami 公开看板，默认最近 30 天、按日展示。博客不再提供「统计」栏目；旧 `/stats/` 只作静态跳转。管理入口仍为 `/login?locale=zh-CN`。
- 网站 ID：`dd0320cd-bbf6-4ec2-81cb-cf3c77493fa7`。公开标识，无管理权限。
- 广州轻量服务器：`lhins-if4y3vqn`，`134.175.20.232`；2 核 4GB、60GB SSD、5Mbps、每月 500GB 流量；月付 65 元。首次购买至 2026-11-13，手动续费。
- PostgreSQL 17、Umami 使用 Docker Compose；配置在 `/opt/saiyudoc-umami`，持久卷 `saiyudoc-umami_db-data`。仅 Nginx 暴露 80/443，应用端口 3000 只绑定回环，数据库不映射公网端口。
- Let's Encrypt 免费证书，由 certbot 定时续期。
- `/public/articles.json` 是每分钟生成的匿名汇总，缓存 60 秒。定时任务 `/etc/cron.d/saiyudoc-umami`，失败保留上次成功文件，前端在超过 10 分钟未更新时提示延迟。
- 加密异地备份：COS `saiyudoc-stats-1301596189/private/umami-backups/`，生命周期 30 天。每天服务器时间 03:30 备份，服务器本地保留 7 天。专用 CAM 子用户 `saiyudoc_umami_backup` 仅有此目录的 PutObject 权限，策略 `289678676`，无控制台登录权限。

管理员密码、SSH 私钥、数据库密码和备份解密密钥仅保存在部署主机及操作者本机私有目录，不进入 Git、网页或 CI。操作者本机目录：`~/.local/share/saiyudoc-umami/`；`credentials.json` 是应用凭证，`server-key` 是 SSH 私钥，`backup.key` 是备份解密密钥。目录权限 700，凭证文件 600。

## 指标

- 原生看板显示访客、访问次数、浏览量、每日趋势、页面排名、来源和设备等。只开放 overview/breakdown，sessions/realtime/events 及原始事件属性不共享。
- 一次页面打开只发送一个 pageview。所有查询参数、片段和来源路径被移除，hostname 统一为 `www.wangsaiyu.com`。旧 RUM 标识 Cookie 自动删除，不新增身份 Cookie；保留退出统计的偏好 Cookie。
- 原生 UV 使用 Umami 的匿名会话摘要，盐按月轮换，不等于精确人数，跨月可能重复计数。分享页日期按浏览器时区；附加阅读汇总固定北京时间。
- `blog_read` 事件上报每次页面打开的临时 ID 和累计前台毫秒数，页面初始的零时长存在 pageview 数据中。聚合按同一临时 ID、路径和匿名会话取最大值，排除重复心跳；按初次事件日期归属。平均前台时长 = 累计前台秒数 / 同期 PV。脚本或退出请求被拦截时会低估。单次最多四小时。
- 心跳不增加 PV；它属于互动事件，会影响 Umami 跳出率。Umami 自带的会话时长仍基于页面浏览间隔，不等于前台阅读时长；单页访问可能为零。
- 访客量、每日趋势、页面排名和原生访问时长直接在 Umami 看板查看。博客仅显示文章累计阅读数，不再嵌入看板或额外阅读明细表。前台阅读心跳及附加汇总保留，供进一步分析；不会替换 Umami 的原生时长指标。没有云 API 密钥、管理员 token 或数据库密码发给浏览器。
- 统计从此次接入开始；旧系统数据保留，不伪造历史补数。客户端统计无法防止有意伪造访问，不用于计费结算。

## 发布与维护

前端沿用 GitHub master → Hugo → COS → CDN 刷新。修改源码后：

```sh
node --test analytics/test_*.cjs
python3 -m unittest discover -s analytics -p 'test_*.py'
hugo --minify
```

服务器文件来自 `analytics/umami/`；备份上传还依赖 `analytics/cloud.py`。服务启动：

```sh
sudo docker compose --project-directory /opt/saiyudoc-umami up -d
sudo python3 /opt/saiyudoc-umami/export.py
sudo sh /opt/saiyudoc-umami/backup.sh
```

只替换需要更新的文件，保留 `.env`、`site.json`、`backup.key`、`backup-credentials.json` 与数据卷。不要直接以仓库中的 HTTP 模板覆盖已由 certbot 添加 TLS 的线上 Nginx 配置。升级前先备份，固定版本更新并验证分享权限、采集和数据库兼容性。禁止 `docker compose down -v`。

恢复加密备份：

```sh
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
  -pass file:/opt/saiyudoc-umami/backup.key -in backup.dump.enc -out backup.dump
# 对准备好的空数据库执行；不直接覆盖当前生产数据库
sudo docker compose --project-directory /opt/saiyudoc-umami exec -T db \
  pg_restore -U umami -d restore_database --exit-on-error < backup.dump
```

备份包含数据库，不包含 TLS 私钥和应用环境密钥；后两者分别通过证书重签与私有配置恢复。查看服务状态用 `docker compose ps`，日志用 `docker compose logs --tail 50`；汇总与备份日志按周轮转。

旧 RUM 实施记录在 `rum-legacy.md`，相关部署脚本仅作历史参考，不应再次启用。2026-10-13 已将 RUM 项目 `159725` 采样率设为 0，并删除云函数 `saiyudoc-analytics` 的定时触发器 `aggregate-every-10-minutes`；再次查询确认没有剩余触发器。旧函数、RUM 项目和历史数据保留作回退参考，当前博客不再加载 RUM SDK 或读取旧汇总。COS 桶继续复用作加密备份。低流量下除服务器外只有少量 COS 开销；超过套餐流量另按腾讯云规则计费。

上线验收记录见 [umami/ACCEPTANCE.md](umami/ACCEPTANCE.md)。

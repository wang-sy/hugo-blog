# 博客公开统计

上线范围：腾讯 RUM（广州）→ 每 10 分钟运行一次的云函数 → COS 公开汇总 JSON → 博客 `/stats/` 与文章阅读数。

## 资源

| 资源 | 标识 |
| --- | --- |
| RUM 业务系统 | `rum-DDsO7rS3Mgd9qZ` |
| RUM 应用 | `159725`，上报 ID `5GWQ1CeGPyjLLRLa4g`（公开项目标识，不是云 API 密钥） |
| 地域 | `ap-guangzhou` |
| 云函数 | `saiyudoc-analytics`，Python 3.10，256 MB，120 秒超时 |
| 定时器 | `aggregate-every-10-minutes`，`0 */10 * * * * *` |
| 执行角色 | `SaiyuDocAnalyticsRole`，ID `4611686018449591489` |
| 权限策略 | `SaiyuDocAnalyticsAccess`，ID `289674693` |
| 统计专用存储桶 | `saiyudoc-stats-1301596189` |
| 私有状态 | `private/state.json.gz` |
| 公开数据 | `https://saiyudoc-stats-1301596189.cos.ap-guangzhou.myqcloud.com/public/stats.json` |

专用桶与网站发布桶分开，网站 CI 的清理上传不会删掉统计历史。桶只放行公开 JSON 的匿名 GET；私有状态不可匿名读取。COS CORS 仅允许 GET/HEAD。浏览器不持有云 API 密钥；云函数使用执行角色颁发的临时凭证。

RUM 的 `DescribeRumLogDetailsV2` 实际鉴权返回资源 `*`，不支持按项目限定该 API；角色只授予这一个只读 API，代码固定读取博客项目。COS 权限精确限定两个对象的读写。并发内存配额 256 MB 限制同时最多一个实例，不开预置实例、不创建公网入口、不创建 CLS 日志主题；异常可从云函数调用结果和监控查看。

## 数据口径与边界

- 从 2026-10-13 开始采集，无历史访问补数。PV 是页面打开次数；UV 是随机浏览器标识的去重数量，不等于精确人数。
- 通过同域 Cookie 合并 www 和根域名，查询参数不参与 URL 分组，也不发送给 RUM。禁止额外错误、接口、资源、点击与录屏采集；允许 SDK 的项目配置查询和 PV、自定义统计日志。
- 顶部和每日表的平均前台停留使用全站页面时长 / 页面访问次数；文章排行分别计算各篇文章的平均值。不是跨页面会话时长。
- 每次页面打开生成独立 visit ID。每分钟和失焦/隐藏/退出时上报累计前台时长；汇总取同一 visit 的最大值，重试、重复拉取不会重复计数。前台时间要求页面可见且窗口获焦，休眠中超过 5 秒的计时间隔不累加，单次上限 4 小时。
- 北京时间按访问开始日归属。周期包含今天；7/30/90 天 UV 是周期内重新去重，不是每日 UV 相加。跨午夜的长阅读归在开始日。
- 每次汇总延后 2 分钟，并重读前 15 分钟防止短暂入库延迟。超过该窗口才入库的迟到事件可能漏计。脚本拦截、DNT/GPC、退出上报失败也会造成低估。
- 私有状态只保留加盐不可逆访客摘要、visit ID、路径、文章标记和累计时长，按北京时间保留最近 90 天；每日汇总和文章累计量长期保留。公开 JSON 从字段白名单重新构造，不含 IP、访客 ID、visit ID 或盐。
- 数据 45 分钟不更新时，看板提示延迟；API 拉取异常不会推进检查点。单轮最多 4,000 条原始日志，超过时保留检查点并报错，需调小批次时间窗或提高汇总频率后追平。
- RUM 上报 ID 是公开的，普通客户端分析不能抵御有意伪造访问；这些数字用于博客流量观察，不作为结算依据。

## 验证与发布

```sh
python3 -m unittest discover -s analytics -p 'test_*.py'
node --test analytics/test_clock.cjs
hugo --minify
```

网站沿用 GitHub `master` 发布流水线。后端修改需使用当前已登录的 tccli 凭证手动更新：

```sh
python3 analytics/deploy.py update
python3 analytics/deploy.py status
python3 analytics/deploy.py invoke
```

`deploy.py` 的 storage/role/create/schedule 子命令用于明确创建或配置资源，不能作为无审核的常规构建步骤。凭证只从当前进程环境或 tccli 登录文件读取，不写入代码包和仓库。

本地预览默认不上报；`?analytics_preview=1` 使用 test 环境并在配置节点的 data 属性记录调试结果。生产页面可以用 `?analytics_debug=1` 查看同样的 SDK 响应诊断，查询参数不会被上报。生产 RUM 域名白名单会拒绝 localhost 上报；不要为本地预览放开生产白名单。完整验收在生产页面实际打开、等待、切换焦点后，核对 RUM 日志和下一轮公开汇总。测试环境日志不会进入公开数字。

回滚网站可撤回统计相关提交并重新发布；停用后台可关闭博客定时触发器。保留专用 COS 私有状态即可保留累计历史，勿删除存储桶。禁用统计不影响静态文章阅读。

## 费用

按量计费，低流量预估 2～5 元/月只是预算估算，10 元不是硬上限。RUM 广州免费日志额度与账号其他应用共享，超过额度及 COS 请求/流量、云函数执行均可产生费用。未开 CLS 日志主题和预置实例，避免固定空闲开销。真实费用以腾讯云账单为准。

官方说明：[RUM 计费](https://cloud.tencent.com/document/product/248/87074)、[云函数计费](https://cloud.tencent.com/document/product/583/12281)、[RUM 查询字段](https://cloud.tencent.com/document/product/248/87223)。

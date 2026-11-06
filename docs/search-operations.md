# 博客搜索收录与 HTTPS

标准域名为 `https://www.wangsaiyu.com/`。不带 www 的域名在腾讯云 CDN
以 301 跳转到相同路径，保留查询参数；HTTP 也使用 301 升级到 HTTPS。
文章地址保持不变，包括已有的 `/archives/` 链接。

## 站点文件

- `/sitemap.xml`：Hugo 生成的完整站点地图。
- `/sitemap-articles.xml`：正文专用地图，按实际修改时间排序，供有限配额的提交使用。
- `/robots.txt`：允许抓取并声明以上两个地图。
- `lastmod`：显式 front matter 优先，其次文章文件的 Git 修改时间，再其次发布日期。
- 页面摘要：文章自身描述优先，旧文章回退到正文摘要；首页使用真实站点介绍。
- `/indexnow-key.txt`：IndexNow 要求公开部署的站点验证文件，不是云账号凭证。

## 发布与每日检查

`Build and deploy` 在 PR 上只构建和测试；master 发布后分别显示部署与搜索提交结果。
每日北京时间 09:17 仅重新构建验证、检查线上文件和证书、补交未完成的文章，不重新部署。

构建检查所有地图地址的页面是否存在、canonical 是否一致、是否误加 noindex/跳转、
是否有真实描述及合法修改时间，并从首页沿静态链接和分页验证所有正文可发现、
robots 允许 Googlebot、bingbot、Baiduspider 抓取。线上检查两个域名的证书、地图与构建产物一致性、
robots、IndexNow 文件和代表文章。证书剩余不足 21 天会使检查失败。

IndexNow 与百度各有独立的成功提交记录，保存在 GitHub Actions cache 中。
只提交新文章或 HTML 有变化的文章；缓存被平台清理时允许重新提交，不会丢文章。
百度每次先提交一篇，按返回的剩余额度停止，每轮最多 20 篇，未完成部分下一天继续。
API 错误、配额不足都会产生明确的失败结果，已成功部分仍保留；不把网站部署成功当作提交成功。
IndexNow 200 表示接口接受；202 表示已收到但站点验证仍待处理。两者都不保证实际收录。

本地检查：

```sh
hugo --minify
python3 -m unittest discover -s scripts -p 'test_*.py'
python3 scripts/verify_search.py
python3 scripts/submit_search.py --engine indexnow --dry-run
python3 scripts/verify_search.py --live
```

百度密钥只使用现有 GitHub Secret `BAIDU_TOKEN`，不写入仓库或输出请求 URL。
Google 的普通博客不能使用仅针对特定内容类型的 Indexing API 代替 Search Console。
Google 站点验证与地图提交需使用站点所有者能登录的 Google 账号；公开 robots 地图声明仍然有效。

## 2026-11-06 修复记录

- 腾讯云已有有效证书覆盖 apex 与 www，但只有 apex 更新过，www 仍绑定过期证书。
  已将 www 的 CDN `Https.CertInfo.CertId` 改为 apex 正在使用的有效证书；不重置其他 HTTPS 设置。
  两个入口实际握手证书均到期于 2027-01-11。
- 百度后台的 Sitemap 今日/存量额度均为 0，且没有已提交的地图文件。
  此平台限制不能通过更改 XML 或反复提交绕过，需在百度后台申请恢复/核实权限。
- 旧发布日志返回 `over quota`，旧脚本仍退出成功；现已改为明确报告失败并保存待提交文章。

续证后必须同时检查 `wangsaiyu.com` 与 `www.wangsaiyu.com` 的 CDN 绑定及真实 TLS 握手。
仅取得新证书，或只更新一个域名，均不算完成。每日检查只是提前发现问题，不会自动购买证书。

搜索验收分别记录：文件可抓取 → 接口接受 → 站长后台已索引 → 搜索曝光/点击。
不得用其中前一步替代后一步。

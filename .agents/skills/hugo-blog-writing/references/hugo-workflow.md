# Hugo 写入与预览

## 项目位置与现有约定

仓库根目录是包含 `hugo.toml`、`content/` 和 `static/` 的目录，不依赖某台电脑的绝对路径。此 skill 位于仓库的 `.agents/skills/hugo-blog-writing/`。

- 文章：`content/posts/<分类>/<slug>.md`。
- 配图：`static/images/<slug>/`；文章中使用 `/images/<slug>/...svg`。
- 主题：以 [hugo.toml](../../../../hugo.toml) 为准，本 skill 创建时使用 LoveIt。
- 构建版本：查看 [.github/workflows/hugo.yml](../../../../.github/workflows/hugo.yml)，本 skill 创建时为 Hugo extended 0.141.0。执行时以仓库当前声明为准。

先查看当前改动，避免覆盖其他工作。用户要求写博客时，沿用原生版式和主题，不额外创建 HTML 页面或修改主题来容纳文章。

## 文章和图片

新文章可以沿用同类文章的 YAML front matter，包含标题、日期、草稿状态、描述、分类和标签。有配图时启用 `lightgallery: true`。开篇之后用 `<!--more-->` 确定首页摘要的边界。

修改旧文保留原来的日期、发布状态及地址设置。中文标题变化不要求重命名 Markdown 文件或变更 URL。

正文从 `##` 开始组织章节，按需要使用 `###` 子节，不在正文重复顶层文章标题。长篇可以使用简短编号，局部说明不必为了凑编号继续拆分。

本项目图片使用原生 shortcode，例如：

```text
{{< image src="/images/agent-deployment/03-context-storage.svg" alt="消息字段、历史顺序、检查点及模型输入" caption="图 3：消息与上下文的逻辑结构，字段为示意" width="1000" height="665" >}}
```

`width`、`height` 对应 SVG 画布；`alt` 说明图中内容，`caption` 提供图名及必要的示意说明。先确认图片文件存在，不能只放一个尚未生成的路径。

不要把本 skill 的资产目录当作网站图片地址。模板需要复制到该篇文章的图片目录后再引用。

## 本地构建

优先复用已存在、属于本项目的预览环境。没有可用环境时，使用与 CI 匹配的 Hugo；临时构建输出、缓存和资源目录放在仓库外，避免写入无关文件。

下面展示构建方式。`repo_root` 是本次确认的仓库绝对路径，`preview_dir` 是仓库外的临时目录，`preview_port` 是已确认可用的端口，`hugo_bin` 指向匹配版本的 Hugo。先确定这些值再运行，不覆盖已占用端口。

```sh
cat > "$preview_dir/preview.toml" <<EOF
resourceDir = "$preview_dir/resources"
cacheDir = "$preview_dir/cache"
EOF

"$hugo_bin" --source "$repo_root" \
  --config "$repo_root/hugo.toml,$preview_dir/preview.toml" \
  --destination "$preview_dir/public" \
  --baseURL "http://127.0.0.1:$preview_port/" \
  --environment development --buildDrafts --noBuildLock --minify

python3 -m http.server "$preview_port" --bind 127.0.0.1 \
  --directory "$preview_dir/public"
```

在工具中以后台服务方式保留预览，不让前台服务阻塞后续操作。`--buildDrafts` 只用于本地看稿，文章自身仍保留对应的草稿状态。

默认直接构建仓库当前文件。如果因权限限制必须先制作外部改稿，使用临时预览配置；取得授权写回后，再从实际仓库重建并核对，避免预览仍来自另一份旧内容。

## 页面检查

- 在原生文章中检查目录、标题层级、正文、图注和表格，确认 shortcode 已渲染。
- 新增或重画的 SVG 逐张确认已加载。主题可能延迟加载图片，滚动进入视口后再检查，不能把占位图当成成功。
- 桌面按正常正文宽度查看；手机检查外层是否溢出，以及表格和图片放大后的可读性。
- 改标题时同时核对首页、文章标题及页面标题；没有必要因此重写文章或重跑不相关业务测试。
- 若浏览器缓存仍显示旧稿，刷新或使用新的预览查询参数，并核对实际响应。不要只凭文件已保存就宣称浏览器已更新。

写作和本地预览不等于发布。交付时说明实际完成的范围，提供当前文章或预览链接；不要顺带提交、推送或触发部署。

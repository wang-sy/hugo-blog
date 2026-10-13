(function () {
  'use strict';
  if (!document.getElementById('public-stats')) return;
  var index = JSON.parse(document.getElementById('stats-article-index').textContent);
  var period = '30', sort = 'pageViews', data;
  var nf = new Intl.NumberFormat('zh-CN');
  var byId = function (id) { return document.getElementById(id); };
  var value = function (id, text) { byId(id).textContent = text; };
  function duration(seconds) {
    if (!Number.isFinite(seconds)) return '—';
    seconds = Math.round(seconds);
    return seconds >= 60 ? Math.floor(seconds / 60) + '分' + (seconds % 60) + '秒' : seconds + '秒';
  }
  function average(item) { return item.measuredReads ? duration(item.activeSeconds / item.measuredReads) : '—'; }
  function dateInChina(time) { return new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).format(time); }
  function cell(tr, text) { var td = document.createElement('td'); td.textContent = text; tr.appendChild(td); return td; }
  function days() {
    var end = dateInChina(new Date(data.generatedAt));
    var result = [], lookup = new Map(data.daily.map(function (d) { return [d.date, d]; }));
    for (var i = Number(period) - 1; i >= 0; i--) {
      var date = dateInChina(new Date(new Date(end + 'T12:00:00+08:00').getTime() - i * 86400000));
      result.push(lookup.get(date) || { date: date, pageViews: 0, uniqueVisitors: 0, articleViews: 0, activeSeconds: 0, measuredReads: 0 });
    }
    return result;
  }
  function svgElement(name, attributes) {
    var node = document.createElementNS('http://www.w3.org/2000/svg', name);
    Object.keys(attributes).forEach(function (key) { node.setAttribute(key, String(attributes[key])); });
    return node;
  }
  function chart(rows) {
    var width = 960, height = 220, left = 42, top = 12, bottom = 28, plot = width - left - 12;
    var max = Math.max(4, Math.ceil(Math.max.apply(null, rows.map(function (d) { return d.pageViews; })) / 4) * 4);
    var step = plot / rows.length;
    var y = function (v) { return height - bottom - (height - top - bottom) * v / max; };
    var svg = svgElement('svg', { viewBox: '0 0 ' + width + ' ' + height, 'aria-hidden': 'true', preserveAspectRatio: 'none' });
    for (var tick = 0; tick <= 4; tick++) {
      var amount = tick * max / 4, position = y(amount);
      svg.appendChild(svgElement('line', { x1: left, y1: position, x2: width - 12, y2: position, class: 'chart-grid' }));
      var label = svgElement('text', { x: left - 10, y: position + 4, 'text-anchor': 'end' }); label.textContent = nf.format(amount); svg.appendChild(label);
    }
    var points = [];
    rows.forEach(function (row, i) {
      var x = left + step * (i + 0.5);
      var bar = svgElement('rect', { x: x - step * .29, y: y(row.pageViews), width: Math.max(1, step * .58), height: Math.max(0, height - bottom - y(row.pageViews)), rx: 2, class: 'chart-bar' });
      var title = svgElement('title', {}); title.textContent = row.date + '：' + row.pageViews + ' 次浏览，' + row.uniqueVisitors + ' 位独立访客'; bar.appendChild(title); svg.appendChild(bar);
      points.push(x + ',' + y(row.uniqueVisitors));
      if (i === 0 || i === rows.length - 1 || i % Math.ceil(rows.length / 6) === 0) {
        var text = svgElement('text', { x: x, y: height - 5, 'text-anchor': 'middle' }); text.textContent = row.date.slice(5); svg.appendChild(text);
      }
    });
    svg.appendChild(svgElement('polyline', { points: points.join(' '), class: 'chart-line' }));
    byId('stats-chart').replaceChildren(svg);
    byId('stats-chart').setAttribute('aria-label', '近 ' + period + ' 天访问趋势，下方可展开每日数据表');
    var body = byId('stats-daily'); body.replaceChildren();
    rows.slice().reverse().forEach(function (row) { var tr = document.createElement('tr'); cell(tr, row.date); cell(tr, nf.format(row.pageViews)); cell(tr, nf.format(row.uniqueVisitors)); cell(tr, nf.format(row.articleViews)); cell(tr, average(row)); body.appendChild(tr); });
    value('stats-range', rows[0].date + ' — ' + rows[rows.length - 1].date);
  }
  function articles() {
    if (!data) return;
    var query = byId('stats-search').value.trim().toLowerCase();
    var current = data.periods[period].articles;
    var rows = index.filter(function (a) { return a.title.toLowerCase().includes(query); }).map(function (a) {
      var path = decodeURIComponent(a.path), metric = current[path] || { pageViews: 0, uniqueVisitors: 0, activeSeconds: 0 };
      return { article: a, pageViews: metric.pageViews, uniqueVisitors: metric.uniqueVisitors,
        duration: metric.pageViews ? metric.activeSeconds / metric.pageViews : 0,
        cumulative: (data.articles[path] || {}).pageViews || 0 };
    }).sort(function (a, b) { return b[sort] - a[sort] || b.cumulative - a.cumulative || b.article.date.localeCompare(a.article.date); });
    var body = byId('stats-articles'); body.replaceChildren();
    rows.forEach(function (row) {
      var tr = document.createElement('tr'), titleCell = cell(tr, ''), link = document.createElement('a'), date = document.createElement('small');
      link.href = row.article.path; link.textContent = row.article.title; date.textContent = row.article.date;
      titleCell.append(link, date); cell(tr, nf.format(row.pageViews)); cell(tr, nf.format(row.uniqueVisitors));
      cell(tr, row.pageViews ? duration(row.duration) : '—'); cell(tr, nf.format(row.cumulative)); body.appendChild(tr);
    });
    byId('stats-articles-empty').hidden = rows.length > 0;
    value('stats-article-subtitle', '近 ' + period + ' 天 · ' + rows.length + ' 篇文章');
    document.querySelectorAll('[data-sort]').forEach(function (button) {
      var labels = { pageViews: '阅读次数', uniqueVisitors: '独立访客', duration: '平均停留' };
      button.textContent = labels[button.dataset.sort] + (sort === button.dataset.sort ? ' ↓' : '');
      button.dataset.active = String(sort === button.dataset.sort);
    });
  }
  function render() {
    var current = data.periods[period];
    value('metric-pv', nf.format(current.pageViews)); value('metric-uv', nf.format(current.uniqueVisitors));
    value('metric-duration', average(current)); value('metric-total', nf.format(data.totals.articleViews));
    value('stats-started', '自 ' + dateInChina(new Date(data.startedAt)) + ' 启用以来');
    value('stats-updated', '更新于 ' + new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(data.generatedAt)));
    var stale = Date.now() - new Date(data.generatedAt).getTime() > 45 * 60000;
    var notice = byId('stats-notice');
    notice.hidden = !stale && current.pageViews > 0;
    notice.textContent = stale ? '统计更新暂有延迟，当前展示最近一次成功汇总的数据。' : '统计刚刚启用，接入前的访问不会补记。新访问会在下一次汇总后显示。';
    document.querySelectorAll('[data-period]').forEach(function (button) { button.setAttribute('aria-pressed', String(button.dataset.period === period)); });
    chart(days()); articles();
  }
  document.querySelectorAll('[data-period]').forEach(function (button) { button.addEventListener('click', function () { period = button.dataset.period; if (data) render(); }); });
  document.querySelectorAll('[data-sort]').forEach(function (button) { button.addEventListener('click', function () { sort = button.dataset.sort; articles(); }); });
  byId('stats-search').addEventListener('input', articles);
  byId('stats-retry').addEventListener('click', function () { location.reload(); });
  window.blogStatsPromise.then(function (result) { data = result; render(); }).catch(function () {
    value('stats-updated', '暂时无法读取统计'); value('stats-notice', '统计数据暂不可用，请稍后重试。文章阅读不受影响。');
    byId('stats-retry').hidden = false;
  });
})();

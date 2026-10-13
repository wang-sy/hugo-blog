(function () {
  'use strict';
  if (!document.getElementById('public-stats')) return;
  var articles = JSON.parse(document.getElementById('stats-article-index').textContent);
  var body = document.getElementById('stats-articles'), search = document.getElementById('stats-search');
  var notice = document.getElementById('stats-notice'), period = '30', stats;
  function count(n) { return new Intl.NumberFormat('zh-CN').format(n || 0); }
  function duration(n) { return n >= 60 ? Math.floor(n / 60) + '分' + (n % 60) + '秒' : n + '秒'; }
  function render() {
    if (!stats) return;
    body.replaceChildren();
    var rows = articles.filter(function (a) { return a.title.toLowerCase().includes(search.value.trim().toLowerCase()); });
    var values = stats.periods[period] || {};
    rows.sort(function (a, b) { return ((values[decodeURI(b.path)] || {}).pageViews || 0) - ((values[decodeURI(a.path)] || {}).pageViews || 0); });
    rows.forEach(function (a) {
      var path = decodeURI(a.path), value = values[path] || {};
      var tr = document.createElement('tr'), td = document.createElement('td'), link = document.createElement('a');
      link.href = a.path; link.textContent = a.title; td.appendChild(link); tr.appendChild(td);
      [count(value.pageViews), count(value.uniqueVisitors), value.pageViews ? duration(value.averageSeconds || 0) : '—', count((stats.articles[path] || {}).pageViews)].forEach(function (text) {
        var cell = document.createElement('td'); cell.textContent = text; tr.appendChild(cell);
      });
      body.appendChild(tr);
    });
    notice.hidden = rows.length > 0; notice.textContent = rows.length ? '' : '没有找到匹配的文章。';
  }
  document.querySelectorAll('[data-period]').forEach(function (button) {
    button.addEventListener('click', function () {
      period = button.dataset.period;
      document.querySelectorAll('[data-period]').forEach(function (b) { b.setAttribute('aria-pressed', String(b === button)); });
      render();
    });
  });
  search.addEventListener('input', render);
  if (!window.blogStatsPromise) return;
  window.blogStatsPromise.then(function (data) {
    stats = data;
    var date = new Date(data.generatedAt), stale = Date.now() - date.getTime() > 600000;
    document.getElementById('stats-updated').textContent = (stale ? '更新延迟，上次 ' : '更新于 ') + date.toLocaleString('zh-CN', {timeZone: 'Asia/Shanghai', hour12: false}) + '（北京时间）';
    render();
  }).catch(function () { notice.hidden = false; notice.textContent = '文章数据暂时无法读取，请稍后刷新。上方看板可以独立使用。'; });
})();

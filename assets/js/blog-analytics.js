(function () {
  'use strict';
  var node = document.getElementById('blog-analytics-config');
  if (!node) return;
  var config = JSON.parse(node.textContent);
  function cookie(name) {
    var part = document.cookie.split('; ').find(function (s) { return s.indexOf(name + '=') === 0; });
    return part ? part.substring(name.length + 1) : '';
  }
  function setCookie(name, value, age) {
    var domain = /(^|\.)wangsaiyu\.com$/.test(location.hostname) ? '; Domain=wangsaiyu.com' : '';
    document.cookie = name + '=' + value + '; Path=/; Max-Age=' + age + '; SameSite=Lax' + domain + '; Secure';
  }
  // Retire the former RUM identifier; Umami uses a rotating anonymous hash.
  if (cookie('saiyudoc_visitor')) setCookie('saiyudoc_visitor', '', 0);
  var optedOut = cookie('saiyudoc_stats_optout') === '1';
  var button = document.getElementById('analytics-optout');
  if (button) {
    button.textContent = optedOut ? '恢复此浏览器的匿名统计' : '停止统计此浏览器的访问';
    button.addEventListener('click', function () {
      setCookie('saiyudoc_stats_optout', optedOut ? '' : '1', optedOut ? 0 : 31536000);
      location.reload();
    });
  }
  var counter;
  if (config.article) {
    var meta = document.querySelector('.post-meta-line:last-child');
    if (meta) {
      var link = document.createElement('a');
      link.className = 'article-view-count'; link.href = config.host + '/';
      link.target = '_blank'; link.rel = 'noopener';
      link.title = 'Umami 接入以来的累计浏览次数，约每分钟更新';
      link.appendChild(document.createTextNode(' · 阅读 '));
      counter = document.createElement('span'); counter.textContent = '—';
      link.appendChild(counter); link.appendChild(document.createTextNode(' 次')); meta.appendChild(link);
    }
  }
  if (counter) {
    var abort = new AbortController();
    var timeout = setTimeout(function () { abort.abort(); }, 10000);
    window.blogStatsPromise = fetch(config.host + '/public/articles.json', {credentials: 'omit', signal: abort.signal})
      .then(function (r) { if (!r.ok) throw new Error('统计服务暂不可用'); return r.json(); })
      .then(function (data) {
        if (data.version !== 2 || !data.articles || !data.periods) throw new Error('统计数据格式异常');
        if (counter) counter.textContent = new Intl.NumberFormat('zh-CN').format((data.articles[decodeURI(config.path)] || {}).pageViews || 0);
        return data;
      }).finally(function () { clearTimeout(timeout); });
    window.blogStatsPromise.catch(function () { if (counter) counter.textContent = '—'; });
  }
  if (!/^(www\.)?wangsaiyu\.com$/.test(location.hostname) || !config.track || optedOut ||
      navigator.doNotTrack === '1' || navigator.globalPrivacyControl === true ||
      /bot|crawler|spider|headless|lighthouse/i.test(navigator.userAgent)) return;
  var readId = crypto.randomUUID();
  var clock = new window.BlogAnalyticsCore.ForegroundClock(performance.now());
  var lastSent = -1, ready = false;
  window.blogBeforeSend = function (type, payload) {
    if (type !== 'event') return null;
    payload.hostname = 'www.wangsaiyu.com'; payload.url = config.path;
    if (payload.referrer) {
      try {
        var ref = new URL(payload.referrer, location.origin);
        payload.referrer = /^(www\.)?wangsaiyu\.com$/.test(ref.hostname) ? '' : ref.origin + '/';
      } catch (_) { payload.referrer = ''; }
    }
    return payload;
  };
  var script = document.createElement('script');
  script.src = config.host + '/script.js'; script.async = true;
  script.dataset.websiteId = config.websiteId; script.dataset.autoTrack = 'false';
  script.dataset.beforeSend = 'blogBeforeSend'; script.dataset.excludeSearch = 'true';
  script.dataset.excludeHash = 'true'; script.dataset.doNotTrack = 'true';
  script.onload = function () {
    if (!window.umami) return;
    // Manual mode prevents duplicate pageviews from hash/history changes.
    window.umami.track(function (payload) {
      payload.data = {read_id: readId, active_ms: 0};
      return payload;
    }).then(function () {
      ready = true; clock.setActive(!document.hidden && document.hasFocus(), performance.now());
      lastSent = 0; node.dataset.analyticsStatus = 'ready';
    });
  };
  script.onerror = function () { node.dataset.analyticsStatus = 'unavailable'; };
  document.head.appendChild(script);
  function emit() {
    var active = clock.tick(performance.now());
    if (!ready || active === lastSent) return;
    // Cumulative time makes duplicate exit/heartbeat requests harmless.
    // The official tracker uses fetch keepalive, including on page exit.
    window.umami.track('blog_read', {read_id: readId, active_ms: active}); lastSent = active;
  }
  function visibility() {
    clock.setActive(ready && !document.hidden && document.hasFocus(), performance.now());
    if (!clock.active) emit();
  }
  document.addEventListener('visibilitychange', visibility);
  window.addEventListener('focus', visibility); window.addEventListener('blur', visibility);
  window.addEventListener('pagehide', function () { clock.setActive(false, performance.now()); emit(); });
  window.addEventListener('pageshow', visibility);
  setInterval(function () { clock.tick(performance.now()); }, 1000);
  setInterval(emit, 30000);
})();

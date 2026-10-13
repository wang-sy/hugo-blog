(function () {
  'use strict';
  var configNode = document.getElementById('blog-analytics-config');
  if (!configNode) return;
  var config = JSON.parse(configNode.textContent);
  var number = new Intl.NumberFormat('zh-CN');
  function cookie(name) {
    var value = document.cookie.split('; ').find(function (part) { return part.indexOf(name + '=') === 0; });
    return value ? value.substring(name.length + 1) : '';
  }
  function setCookie(name, value, maxAge) {
    var domain = /(^|\.)wangsaiyu\.com$/.test(location.hostname) ? '; Domain=wangsaiyu.com' : '';
    document.cookie = name + '=' + value + '; Path=/; Max-Age=' + maxAge + '; SameSite=Lax' + domain + (location.protocol === 'https:' ? '; Secure' : '');
  }
  var optedOut = cookie('saiyudoc_stats_optout') === '1';
  var optout = document.getElementById('analytics-optout');
  if (optout) {
    optout.textContent = optedOut ? '恢复此浏览器的匿名统计' : '停止统计此浏览器的访问';
    optout.addEventListener('click', function () {
      setCookie('saiyudoc_stats_optout', optedOut ? '' : '1', optedOut ? 0 : 31536000);
      if (!optedOut) setCookie('saiyudoc_visitor', '', 0);
      location.reload();
    });
  }

  var counter;
  if (config.article) {
    var meta = document.querySelector('.post-meta-line:last-child');
    if (meta) {
      var link = document.createElement('a');
      link.className = 'article-view-count';
      link.href = '/stats/';
      link.title = '自统计启用以来的浏览次数，约每 10 分钟更新';
      link.appendChild(document.createTextNode(' · 阅读 '));
      counter = document.createElement('span');
      counter.textContent = '—';
      link.appendChild(counter);
      link.appendChild(document.createTextNode(' 次'));
      meta.appendChild(link);
    }
  }

  // Public, aggregate-only data. No Tencent API credential is delivered to browsers.
  if (counter || document.getElementById('public-stats')) {
    var controller = new AbortController();
    var timeout = setTimeout(function () { controller.abort(); }, 10000);
    window.blogStatsPromise = fetch(config.statsUrl, { credentials: 'omit', cache: 'no-cache', signal: controller.signal })
      .then(function (response) { if (!response.ok) throw new Error('统计数据暂不可用'); return response.json(); })
      .then(function (data) {
        if (data.version !== 1 || !data.articles || !data.periods) throw new Error('统计数据格式异常');
        if (counter) counter.textContent = number.format((data.articles[decodeURIComponent(config.path)] || {}).pageViews || 0);
        return data;
      }).finally(function () { clearTimeout(timeout); });
    // Article counters fail quietly; the dashboard gives a visible retry action.
    window.blogStatsPromise.catch(function () { if (counter) counter.textContent = '—'; });
  }

  var localPreview = /^(localhost|127\.0\.0\.1)$/.test(location.hostname) && new URLSearchParams(location.search).get('analytics_preview') === '1';
  var diagnostics = localPreview || new URLSearchParams(location.search).get('analytics_debug') === '1';
  var productionHost = /^(www\.)?wangsaiyu\.com$/.test(location.hostname);
  if ((!productionHost && !localPreview) || !config.track || optedOut || navigator.doNotTrack === '1' || navigator.globalPrivacyControl === true) return;
  if (/bot|crawler|spider|headless|lighthouse/i.test(navigator.userAgent)) return;

  var visitor = cookie('saiyudoc_visitor');
  if (!/^[a-f0-9-]{36}$/.test(visitor)) {
    visitor = crypto.randomUUID();
    setCookie('saiyudoc_visitor', visitor, 31536000);
  }
  var visit = crypto.randomUUID();
  var started = Date.now();
  var clock = new window.BlogAnalyticsCore.ForegroundClock(performance.now());
  var aegis;
  var lastSent = -1;
  var sdk = document.createElement('script');
  sdk.src = config.sdkUrl;
  sdk.async = true;
  sdk.onload = function () {
    if (diagnostics) configNode.dataset.rumStatus = window.Aegis ? 'sdk-loaded' : 'sdk-unavailable';
    if (!window.Aegis) return;
    aegis = new window.Aegis({
      id: config.rumId, aid: visitor, uin: '', env: localPreview ? 'test' : 'production',
      version: 'blog-analytics-1', hostUrl: 'https://rumt-zh.com',
      pageUrl: 'https://www.wangsaiyu.com' + config.path,
      urlHandler: function () { return 'https://www.wangsaiyu.com' + config.path; },
      spa: false, onError: false, reportApiSpeed: false, reportAssetSpeed: false,
      pagePerformance: false, webVitals: false, consoleLog: false, clickElementLog: false,
      whiteListUrl: '', offlineLog: false, delay: 100, repeat: 0, random: 1,
      afterRequest: function (result) {
        if (diagnostics) {
          configNode.dataset.rumStatus = result.logType + ':' + (result.isErr ? 'failed' : 'sent');
          configNode.dataset.rumResponse = JSON.stringify(result.result).slice(0, 300);
        }
      },
      onBeforeRequest: function (request) {
        var url = new URL(request.url);
        ['from', 'originFrom'].forEach(function (key) {
          if (url.searchParams.has(key)) url.searchParams.set(key, 'https://www.wangsaiyu.com' + config.path);
        });
        url.searchParams.delete('referer');
        request.url = url.toString();
        return request;
      },
      beforeRequest: function (data) {
        // SDK configuration requests must complete before its rate-limit queue can drain.
        if (data.logType === 'pv' || data.logType === 'whiteList') return data;
        if (data.logType === 'log' && data.logs && data.logs.ext1 === 'saiyudoc_metric_v1') {
          data.logs.originFrom = 'https://www.wangsaiyu.com' + config.path;
          return data;
        }
        return false;
      }
    });
    updateVisibility();
    emit(false);
  };
  sdk.onerror = function () { if (diagnostics) configNode.dataset.rumStatus = 'sdk-failed'; };
  document.head.appendChild(sdk);

  function emit(beacon) {
    var active = clock.tick(performance.now());
    if (!aegis || active === lastSent) return;
    var previousSendNow = aegis.sendNow;
    // SDK's immediate-send mode flushes through navigator.sendBeacon on page hide.
    aegis.sendNow = beacon;
    aegis.infoAll({
      msg: JSON.stringify({ v: 1, visit: visit, started: started, path: config.path,
        article: config.article, activeMs: active }),
      ext1: 'saiyudoc_metric_v1'
    });
    aegis.sendNow = previousSendNow;
    lastSent = active;
  }
  function updateVisibility() {
    clock.setActive(!document.hidden && document.hasFocus(), performance.now());
    if (!clock.active) emit(true);
  }
  document.addEventListener('visibilitychange', updateVisibility);
  window.addEventListener('focus', updateVisibility);
  window.addEventListener('blur', updateVisibility);
  window.addEventListener('pagehide', function () { clock.setActive(false, performance.now()); emit(true); });
  window.addEventListener('pageshow', updateVisibility);
  setInterval(function () { clock.tick(performance.now()); }, 1000);
  setInterval(function () { emit(false); }, 60000);
})();

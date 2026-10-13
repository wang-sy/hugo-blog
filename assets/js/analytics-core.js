(function (root) {
  'use strict';
  function ForegroundClock(now) {
    this.last = now;
    this.total = 0;
    this.active = false;
  }
  ForegroundClock.prototype.tick = function (now) {
    var delta = now - this.last;
    // A suspended browser or sleeping computer is not reading time.
    if (this.active && delta > 0 && delta <= 5000) this.total += delta;
    this.last = now;
    return Math.min(Math.round(this.total), 14400000);
  };
  ForegroundClock.prototype.setActive = function (active, now) {
    this.tick(now);
    this.active = active;
  };
  var api = { ForegroundClock: ForegroundClock };
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.BlogAnalyticsCore = api;
})(typeof window !== 'undefined' ? window : globalThis);

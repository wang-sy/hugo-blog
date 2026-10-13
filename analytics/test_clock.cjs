const test = require('node:test');
const assert = require('node:assert/strict');
const {ForegroundClock} = require('../assets/js/analytics-core.js');

test('foreground only: hidden, blur and system suspension do not accrue time', () => {
  const clock = new ForegroundClock(0);
  clock.setActive(true,0);
  assert.equal(clock.tick(1000),1000);
  clock.setActive(false,2000);
  assert.equal(clock.tick(12000),2000);
  clock.setActive(true,12000);
  assert.equal(clock.tick(13000),3000);
  assert.equal(clock.tick(90000),3000);
  assert.equal(clock.tick(91000),4000);
});

test('long article reads accumulate beyond 60 seconds and are capped at four hours', () => {
  const clock = new ForegroundClock(0); clock.setActive(true,0);
  for(let n=1;n<=20000;n++) clock.tick(n*1000);
  assert.equal(clock.tick(20000000),14400000);
});

// Run: node --test tools/test/linear-inequality-region.test.cjs
// Offline regression tests: lesson DOM interactions, mathematics, and entry points.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.join(__dirname, '../..');
const article = fs.readFileSync(path.join(root, 'math-ii/linear-inequality-region-sweep.html'), 'utf8');
const match = article.match(/<script>([\s\S]*?)<\/script>/);
assert.ok(match, 'one inline JavaScript block must be present');
const script = match[1];
new vm.Script(script); // syntax guard

class Element {
  constructor(id) {
    this.id = id;
    this.attributes = {};
    this.handlers = {};
    this.children = [];
    this.dataset = {};
    this.style = {};
    this.value = '';
    this.checked = false;
    this.textContent = '';
    this.innerHTML = '';
    this.classList = {toggle() {}};
  }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name]; }
  appendChild(child) { this.children.push(child); return child; }
  addEventListener(name, fn) { this.handlers[name] = fn; }
  emit(name, evt = {}) {
    assert.equal(typeof this.handlers[name], 'function', 'missing event listener');
    this.handlers[name](evt);
  }
}
function launch() {
  const names = [...article.matchAll(/\bid="([^"]+)"/g)].map(m => m[1]);
  assert.equal(names.length, new Set(names).size, 'duplicate HTML id');
  const elements = new Map(names.map(id => [id, new Element(id)]));
  const events = {};
  const queued = new Map();
  let nextFrame = 1;
  const document = {
    getElementById(id) { assert.ok(elements.has(id), 'missing DOM id ' + id); return elements.get(id); },
    createElementNS(_ns, tag) { return new Element(tag); },
    addEventListener(name, fn) { events[name] = fn; },
    documentElement: {requestFullscreen: async () => {}},
    exitFullscreen: async () => {},
    fullscreenElement: null,
    hidden: false,
  };
  const ctx = vm.createContext({
    document,
    requestAnimationFrame(fn) { const id = nextFrame++; queued.set(id, fn); return id; },
    cancelAnimationFrame(id) { queued.delete(id); },
  });
  vm.runInContext(script, ctx, {filename: 'linear-inequality-region-sweep.html'});
  return {
    get: id => elements.get(id),
    evaluate: code => vm.runInContext(code, ctx),
    click: id => elements.get(id).emit('click'),
    input: value => elements.get('k').emit('input', {target: {value: String(value)}}),
    change: (id, prop, value) => elements.get(id).emit('change', {target: {[prop]: value}}),
    frame: t => { const first = queued.entries().next().value; assert.ok(first); queued.delete(first[0]); first[1](t); },
    key: key => events.keydown({key, code: key === ' ' ? 'Space' : key, target: {tagName:'DIV', isContentEditable: false}, preventDefault(){}}),
  };
}

test('revised lesson embeds math glyphs and has no remote runtime dependency', () => {
  assert.match(article, /const MATH_GLYPHS=/);
  assert.doesNotMatch(article, /<script\b[^>]*\bsrc=/);
  assert.doesNotMatch(article, /<link\b[^>]*\bhref=/);
  assert.match(article, /ここから上がOK/);
  assert.match(article, /ここから下がOK/);
});

test('x=k including -1.7 shows visible, correct boundary and upward ray', () => {
  const app = launch();
  assert.equal(app.evaluate('kValue()'), 0);
  assert.equal(app.evaluate('limitValue()'), -1);
  assert.equal(app.get('swept').getAttribute('visibility'), 'hidden');
  assert.equal(app.get('endpoint').getAttribute('fill'), '#fff');
  app.input(-1.7);
  assert.equal(app.evaluate('kValue()'), -1.7);
  assert.equal(app.evaluate('limitValue()'), -4.4);
  assert.equal(app.get('heightEquation').dataset.math, '2k−1=−4.4');
  assert.equal(app.get('numericEquation').dataset.math, 'y>−4.4');
  assert.equal(Number(app.get('endpoint').getAttribute('cy')), app.evaluate('Y(-4.4)'));
  assert.match(app.get('rayArrow').getAttribute('d'), /^M/);
  assert.equal(app.get('directionText').textContent, 'ここから上がOK');
  for (const k of [-4, -3.4, 0, 2.6, 4]) {
    app.input(k);
    const endpoint = Number(app.get('endpoint').getAttribute('cy'));
    assert.ok(endpoint >= app.evaluate('TOP') && endpoint <= app.evaluate('BOTTOM'), 'endpoint is visible');
    assert.equal(app.evaluate('limitValue()'), 2 * k - 1);
  }
});

test('collect mode retains swept positions when slider moves backward', () => {
  const app = launch();
  app.click('collect');
  assert.equal(app.evaluate('state.mode'), 'collect');
  app.input(-1.7);
  app.input(2);
  app.input(-3);
  assert.equal(app.evaluate('state.lo'), -4);
  assert.equal(app.evaluate('state.hi'), 2);
  assert.equal(app.get('swept').getAttribute('visibility'), 'visible');
  assert.ok(app.get('swept').getAttribute('d').includes(String(app.evaluate('X(2)'))));
  app.click('finish');
  assert.equal(app.evaluate('state.mode'), 'all');
  assert.equal(app.get('finish').getAttribute('aria-pressed'), 'true');
  app.click('single');
  assert.equal(app.get('swept').getAttribute('visibility'), 'hidden');
});

test('below, inclusive and exclusive cases update ray and boundary', () => {
  const app = launch();
  app.change('direction', 'value', 'lower');
  assert.equal(app.get('directionText').textContent, 'ここから下がOK');
  assert.equal(app.get('numericEquation').dataset.math, 'y<−1');
  app.change('inclusive', 'checked', true);
  assert.equal(app.get('numericEquation').dataset.math, 'y≦−1');
  assert.equal(app.get('endpoint').getAttribute('fill'), '#087c9d');
  assert.equal(app.get('boundary').getAttribute('stroke-dasharray'), 'none');
  assert.match(app.get('boundaryNote').textContent, /境界直線は実線/);
  app.change('direction', 'value', 'upper');
  assert.equal(app.get('numericEquation').dataset.math, 'y≧−1');
});

test('play, pause, reset, arrow keys work', () => {
  const app = launch();
  app.key('ArrowRight');
  assert.equal(app.evaluate('kValue()'), 0.1);
  app.click('play');
  assert.equal(app.evaluate('state.running'), true);
  assert.equal(app.evaluate('kValue()'), -4);
  app.frame(1000);
  app.frame(1080);
  assert.ok(app.evaluate('kValue()') > -4);
  app.click('play');
  assert.equal(app.evaluate('state.running'), false);
  app.click('reset');
  assert.equal(app.evaluate('kValue()'), 0);
  assert.equal(app.evaluate('state.mode'), 'single');
});

test('math II index preserves page order and Pick Up', () => {
  const index = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
  const org = fs.readFileSync(path.join(root, 'index.org'), 'utf8');
  assert.match(index, /class="featured-section"/);
  assert.match(index, /href="\.\/math-ii\/linear-inequality-region-sweep\.html"/);
  assert.match(org, /:PATH: \.\/math-ii\/linear-inequality-region-sweep\.html/);
  assert.match(org, /:PAGE: 91/);
  const section = index.split('<h2>数II</h2>')[1].split('<h2>数B</h2>')[0];
  assert.deepEqual([...section.matchAll(/深進数学II p\.(\d+)/g)].map(m => +m[1]), [9,10,88,89,91,106]);
});


test('lesson links back to the index and shows textbook page 91', () => {
  assert.match(article, /<a\b[^>]*href="\.\.\/index\.html"[^>]*>← 教材一覧へ戻る<\/a>/);
  assert.match(article, /数学II \/ 図形と方程式 \/ 教科書 P\.91/);
  assert.match(article, /class="header-actions"/);
  const index = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
  assert.match(index, /href="\.\/math-ii\/linear-inequality-region-sweep\.html">縦線を集めると領域になる<\/a>/);
  assert.match(index, /深進数学II p\.91/);
});

const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const path=require('node:path');const vm=require('node:vm');
const html=fs.readFileSync(path.join(__dirname,'../../index.html'),'utf8');
const script=html.match(/<!-- math-visual-gallery-script:start -->\s*<script>([\s\S]*?)<\/script>/)[1];
function node(tag) {
  const listeners = {};
  return {
    tag, children: [], style: {}, attrs: {},
    addEventListener(type, fn) { (listeners[type] ??= []).push(fn); },
    fire(type, event = {}) { for (const fn of listeners[type] ?? []) fn(event); },
    append(child) { this.children.push(child); },
    replaceChildren() { this.children = []; },
    setAttribute(key, value) { this.attrs[key] = value; },
    removeAttribute(key) { delete this.attrs[key]; },
  };
}
function boot() {
  const classes = new Set(), timers = new Map();
  let seq = 0, now = 0;
  const body = node('body'), document = node('document'), window = node('window');
  const toggle = { ...node('input'), checked: true }, controls = { hidden: true };
  const card = node('article'), other = node('article');
  const description = { textContent: '数式 x+y=k と\nその解説。' };
  card.querySelector = selector => selector === '.item-description'
    ? description : { textContent: 'HTML / 公開・更新' };
  other.querySelector = () => ({ textContent: '別の教材' });
  card.getBoundingClientRect = () => ({ left: 700, top: 385, bottom: 595 });
  other.getBoundingClientRect = () => ({ left: 20, top: 30, bottom: 230 });
  window.innerHeight = 620; window.innerWidth = 760;
  let typesetCount = 0;
  window.MathJax = { typesetClear() {}, typeset() { typesetCount++; } };
  body.classList = { toggle: (c, v) => v ? classes.add(c) : classes.delete(c) };
  Object.assign(document, {
    getElementById: () => toggle, querySelector: () => controls,
    querySelectorAll: () => [card, other], body,
    createElement: tag => ({ ...node(tag), offsetHeight: 100, offsetWidth: 300 }),
  });
  vm.runInNewContext(script, {
    document, window,
    setTimeout(fn, delay) { timers.set(++seq, { fn, at: now + delay }); return seq; },
    clearTimeout(id) { timers.delete(id); },
  });
  function tick(ms) {
    now += ms;
    for (const [id, timer] of timers) if (timer.at <= now) {
      timers.delete(id); timer.fn();
    }
  }
  return { toggle, controls, classes, document, window, card, other, description, tick,
    preview: body.children[0], typesetCount: () => typesetCount };
}
test('default compact; checking reveals details; repeat and history reset', () => {
  const x = boot();
  assert.equal(x.toggle.checked, false);
  assert.equal(x.controls.hidden, false);
  for (let i = 0; i < 6; i++) {
    assert.deepEqual([...x.classes], ['compact-gallery']);
    x.toggle.checked = true; x.toggle.fire('change');
    assert.equal(x.classes.size, 0);
    x.toggle.checked = false; x.toggle.fire('change');
  }
  x.toggle.checked = true; x.toggle.fire('change'); x.window.fire('pageshow');
  assert.equal(x.toggle.checked, false);
  assert.deepEqual([...x.classes], ['compact-gallery']);
});
test('no persistent preferences or dead no-JS toggle, label and existing assets remain',()=>{assert.doesNotMatch(script,/localStorage|sessionStorage/);assert.match(html,/<div class="gallery-controls" hidden>/);assert.match(html,/<label class="gallery-toggle"><input id="gallery-details-toggle" type="checkbox" autocomplete="off">詳しい情報を表示<\/label>/);assert.doesNotMatch(html,/<body[^>]*compact-gallery/);assert.equal((html.match(/class="entry-image"/g)||[]).length,21);assert.equal((html.match(/class="item-title"/g)||[]).length,21);assert.doesNotMatch(html,/<section class="featured-section"/);});

test('compact view hides descriptions and metadata, never textbook pages', () => {
  const css = html.match(/\/\* math-visual-gallery-css:start \*\/([\s\S]*?)\/\* math-visual-gallery-css:end \*\//)[1];
  assert.match(css, /\.compact-gallery \.material-card \.item-description,\s*\.compact-gallery \.material-card \.item-meta-inline \{ display: none; \}/);
  assert.doesNotMatch(css, /item-book-page/);
  assert.equal((html.match(/class="item-book-page"/g) || []).length, 21);
});

test('hover waits, shows both hidden fields, fits the viewport, and can be hovered', () => {
  const x = boot(), mouse = { pointerType: 'mouse' };
  x.description.textContent = 'Already typeset by MathJax';
  x.card.fire('pointerenter', mouse); x.tick(499);
  assert.equal(x.preview.hidden, true);
  x.tick(1);
  assert.equal(x.preview.hidden, false);
  assert.deepEqual(x.preview.children.map(n => n.textContent), ['数式 x+y=k と\nその解説。', 'HTML / 公開・更新']);
  assert.equal(x.typesetCount(), 1);
  assert.equal(x.preview.style.top, '279px');
  assert.equal(x.preview.style.left, '448px');
  x.card.fire('pointerleave', mouse); x.tick(100);
  x.preview.fire('pointerenter'); x.tick(200);
  assert.equal(x.preview.hidden, false);
  x.preview.fire('pointerleave'); x.tick(160);
  assert.equal(x.preview.hidden, true);
});
test('no stale hover, touch or expanded previews; keyboard and Escape work', () => {
  const x = boot(), mouse = { pointerType: 'mouse' };
  x.card.fire('pointerenter', { pointerType: 'touch' }); x.tick(600);
  assert.equal(x.preview.hidden, true);
  x.card.fire('pointerenter', mouse); x.card.fire('pointerleave', mouse);
  x.other.fire('pointerenter', mouse); x.tick(500);
  assert.equal(x.preview.children[0].textContent, '別の教材');
  x.toggle.checked = true; x.toggle.fire('change'); x.tick(600);
  assert.equal(x.preview.hidden, true);
  x.card.fire('pointerenter', mouse); x.tick(600);
  assert.equal(x.preview.hidden, true);
  x.toggle.checked = false; x.toggle.fire('change');
  const link = node('a'); link.matches = s => s === 'a:focus-visible';
  x.card.fire('focusin', { target: link }); x.tick(500);
  assert.equal(x.preview.hidden, false);
  assert.equal(link.attrs['aria-describedby'], 'gallery-card-preview');
  x.document.fire('keydown', { key: 'Escape' });
  assert.equal(x.preview.hidden, true);
  assert.equal(link.attrs['aria-describedby'], undefined);
});

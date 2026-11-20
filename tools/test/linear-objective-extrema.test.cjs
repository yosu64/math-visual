// Run: node --test tools/test/linear-objective-extrema.test.cjs
// Source-based regression tests; no network, browser, or third-party packages.
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '../..');
const source = fs.readFileSync(path.join(root, 'math-ii/linear-objective-extrema.html'), 'utf8');
const script = source.match(/<script>([\s\S]*?)<\/script>/);
assert.ok(script, 'lesson has its inline script');
new vm.Script(script[1], {filename: 'linear-objective-extrema.html'});

function mathContext() {
  const start = script[1].indexOf('function slice(tick=state.tick){');
  const end = script[1].indexOf('let G=null;', start);
  assert.ok(start >= 0 && end > start, 'actual slice, inDomain and witnessPoint code present');
  const context = vm.createContext({});
  vm.runInContext(
    'const state={tick:100,alpha:50}; const kValue=()=>state.tick/100;\n' +
    script[1].slice(start,end), context);
  return {
    sample(k, alpha=50) {
      vm.runInContext('state.tick='+Math.round(k*100)+';state.alpha='+alpha+';', context);
      return vm.runInContext('({slice:slice(),point:witnessPoint(),k:kValue()})', context);
    },
  };
}
const eps=1e-9;
function satisfies(p) {
  return p.x>=-eps && p.y>=-eps &&
    p.x+2*p.y<=8+eps && 3*p.x+p.y<=9+eps;
}

test('source preserves the approved lesson shape and offline runtime', () => {
  assert.match(source, /数学II · P\.95 · 例題15/);
  assert.match(source, /href="\.\.\/index\.html"/);
  for (const id of ['intro','raise','maximum','beyond','nearMax','atMax','overMax','minimum','linePlay','pointPlay','kSlider','pointSlider']) {
    assert.ok(source.includes('id="'+id+'"'), 'missing '+id);
  }
  assert.doesNotMatch(source, /<script\b[^>]*\bsrc=/);
  assert.doesNotMatch(source, /<link\b[^>]*\bhref=/);
});

test('three distinct points on x+y=1 all have the same sum', () => {
  const math=mathContext();
  const expected=[[0,1],[0.5,0.5],[1,0]];
  for (const [i,alpha] of [0,50,100].entries()) {
    const result=math.sample(1,alpha);
    assert.equal(result.slice.kind,'segment');
    assert.ok(Math.abs(result.point.x-expected[i][0])<eps);
    assert.ok(Math.abs(result.point.y-expected[i][1])<eps);
    assert.ok(satisfies(result.point));
  }
});

test('entire allowable range of k is exactly 0 through 5 inclusive', () => {
  const math=mathContext();
  for (let tick=-50;tick<=600;tick++) {
    const k=tick/100;
    const value=math.sample(k);
    const expected=k>=0 && k<=5;
    assert.equal(value.slice.kind!=='empty',expected,'k='+k);
    if (expected) {
      assert.equal(value.point.valid,true);
      assert.ok(satisfies(value.point),'out of D at '+k);
      assert.ok(Math.abs(value.point.x+value.point.y-k)<eps,'wrong sum at '+k);
    } else assert.equal(value.point.valid,false);
  }
});

test('maximum and minimum are actually attained at their unique points', () => {
  const math=mathContext();
  for (const [k,x,y] of [[0,0,0],[5,2,3]]) {
    const result=math.sample(k);
    assert.equal(result.slice.kind,'point');
    assert.ok(Math.abs(result.point.x-x)<eps && Math.abs(result.point.y-y)<eps);
    assert.ok(satisfies(result.point));
  }
  assert.equal(math.sample(5.01).slice.kind,'empty');
  assert.equal(math.sample(-0.01).slice.kind,'empty');
});

test('movable witness stays in D and on the objective line for every sample', () => {
  const math=mathContext();
  for (const k of [0.01,0.5,1,1.25,2,3,4,4.9,4.99]) {
    for (const alpha of [0,1,25,50,75,99,100]) {
      const {slice,point}=math.sample(k,alpha);
      assert.equal(slice.kind,'segment');
      assert.ok(satisfies(point),'witness outside D at '+k+' '+alpha);
      assert.ok(Math.abs(point.x+point.y-k)<eps);
    }
  }
});

test('page 95 is linked in correct math II textbook order without the removed Pick Up', () => {
  const index = fs.readFileSync(path.join(root,'index.html'),'utf8');
  const org = fs.readFileSync(path.join(root,'index.org'),'utf8');
  assert.doesNotMatch(index, /class="featured-section"/);
  assert.match(index,/href="\.\/math-ii\/linear-objective-extrema\.html"/);
  assert.match(org, /:PATH: \.\/math-ii\/linear-objective-extrema\.html\n:TEXTBOOK: 深進数学II\n:PAGE: 95/);
  const section=index.split('<h2>数II</h2>')[1].split('<h2>数B</h2>')[0];
  const pages=[...section.matchAll(/深進数学II p\.(\d+)/g)].map(m=>Number(m[1]));
  assert.deepEqual(pages,[9,10,88,89,91,92,95,106]);
});

test('P.95 retains one catalog card and prominently links the optional interactive view', () => {
  const index = fs.readFileSync(path.join(root,'index.html'),'utf8');
  const org = fs.readFileSync(path.join(root,'index.org'),'utf8');
  const v2 = fs.readFileSync(path.join(root,'math-ii/linear-objective-extrema-v2.html'),'utf8');
  assert.match(source, /<\/header>\s*<a class="lesson-v2" href="\.\/linear-objective-extrema-v2\.html">[^\n]*グラフを動かして学ぶ/);
  assert.match(v2, /href="https:\/\/yosu64\.github\.io\/math-visual\/math-ii\/linear-objective-extrema\.html"/);
  assert.match(v2, /<title>和が同じ点を一本の直線に。和の値は、y 切片で読める。<\/title>/);
  assert.match(v2, /<h1><span>和が同じ点を一本の直線に。<\/span><span>和の値は、<i>y<\/i> 切片で読める。<\/span><\/h1>/);
  assert.doesNotMatch(v2, /<script\b[^>]*\bsrc=|<link\b[^>]*\bhref=/);
  assert.doesNotMatch(index+org, /linear-objective-extrema-v2\.html/);
  assert.equal([...index.matchAll(/class="item-title"><a href="\.\/math-ii\/linear-objective-extrema\.html"/g)].length,1);
  const manifest = JSON.parse(fs.readFileSync(path.join(root,'images/entries/manifest.json'),'utf8'));
  const entry = manifest.images.find(image => image.article === './math-ii/linear-objective-extrema.html');
  assert.ok(entry?.approved && index.includes(entry.image));
  const hash = data => require('node:crypto').createHash('sha256').update(data).digest('hex');
  assert.equal(entry.article_sha256,hash(source));
  assert.equal(entry.sha256,hash(fs.readFileSync(path.join(root,entry.image))));
});

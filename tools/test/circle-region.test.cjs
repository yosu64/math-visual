// Run from repository root: node --test tools/test/circle-region.test.cjs
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const file = path.resolve(__dirname, '../../math-ii/circle-region-concentric-level-sets.html');
const html = fs.readFileSync(file, 'utf8');
const match = html.match(/<script>([\s\S]*?)<\/script>/);
assert.ok(match, 'inline lesson script exists');
const script = match[1];
new vm.Script(script);
class Element {
  constructor(id) {
    this.id=id; this.dataset={}; this.attributes={}; this.handlers={}; this.children=[];
    this.value=''; this.checked=false; this.hidden=false; this.innerHTML=''; this.textContent='';
    this.clientWidth=1200; this.clientHeight=660;
    this.classList={toggle() {}};
  }
  setAttribute(name,value) {this.attributes[name]=String(value);}
  getAttribute(name) {return this.attributes[name];}
  appendChild(child){this.children.push(child);return child;}
  replaceChildren(...children){this.children=children;}
  addEventListener(name,handler){this.handlers[name]=handler;}
  emit(name,event={}){assert.equal(typeof this.handlers[name],'function',this.id+'/'+name);this.handlers[name](event);}
}
function lesson() {
  const names=[...html.matchAll(/\bid="([^"]+)"/g)].map(x=>x[1]);
  assert.equal(names.length,new Set(names).size,'duplicate DOM id');
  const nodes=new Map(names.map(x=>[x,new Element(x)]));
  const events={}; let frameHandler;
  const document={
    getElementById(id){assert.ok(nodes.has(id),id);return nodes.get(id);},
    createElementNS(_ns,tag){return new Element(tag);},
    addEventListener(key,fn){events[key]=fn;},
    documentElement:{requestFullscreen:async()=>{}},exitFullscreen:async()=>{},hidden:false,fullscreenElement:null
  };
  const context=vm.createContext({document,ResizeObserver:class{observe(){}},
    requestAnimationFrame(fn){frameHandler=fn;return 1;},cancelAnimationFrame(){}});
  vm.runInContext(script,context,{filename:file});
  return {run:s=>vm.runInContext(s,context),node:id=>nodes.get(id),
    click:id=>nodes.get(id).emit('click'),change:(id,field,value)=>nodes.get(id).emit('change',{target:{[field]:value}}),
    frame:t=>frameHandler(t),events};
}
test('lesson is standalone, linked to the index and marked P.92',()=>{
  assert.match(html,/数学II · P\.92/);
  assert.match(html,/href="\.\.\/index\.html"/);
  assert.doesNotMatch(html,/<script\b[^>]*src=/);
  assert.doesNotMatch(html,/<link\b[^>]*href=/);
});
test('inside comprises all 0 <= t < 4, including center, excluding boundary',()=>{
  const a=lesson();
  assert.equal(a.run('tValue()'),3);
  assert.equal(a.run('accepted(0) && accepted(2) && accepted(3.99)'),true);
  assert.equal(a.run('accepted(4) || accepted(5)'),false);
  assert.equal(a.node('currentEquation').dataset.math,'(x−1)²+(y−3)²=3');
  a.click('finish');
  assert.equal(a.run('collectedContains(0) && collectedContains(3.9999)'),true);
  assert.equal(a.run('collectedContains(4) || collectedContains(5)'),false);
  assert.equal(a.node('centerPoint').getAttribute('visibility'),'visible');
  a.change('inclusive','checked',true);
  assert.equal(a.run('collectedContains(4)'),true);
});
test('outside comprises t > 4 with no upper limit; boundary option is exact',()=>{
  const a=lesson();a.click('outside');
  assert.equal(a.run('tValue()'),5);
  assert.equal(a.run('accepted(5) && !accepted(4) && !accepted(3)'),true);
  a.click('finish');
  assert.equal(a.run('collectedContains(1000000) && !collectedContains(4)'),true);
  a.change('inclusive','checked',true);
  assert.equal(a.run('collectedContains(4) && !collectedContains(3.999)'),true);
});
test('preset t=0 is the center point; example t=2 and t=3 are correct circles',()=>{
  const a=lesson();
  a.click('example1'); assert.equal(a.run('tValue()'),2);
  assert.equal(a.run('currentRadius()'),Math.sqrt(2));
  a.click('example0'); assert.equal(a.run('tValue()'),3);
  a.click('example3'); assert.equal(a.run('tValue()'),0);
  assert.equal(a.node('centerPoint').getAttribute('visibility'),'visible');
  assert.match(a.node('liveHeading').textContent,/中心の1点/);
});
test('sweep shades exactly the traversed level interval and retains it on reverse',()=>{
  const a=lesson();a.click('play');
  a.run('pause();setT(2);');
  assert.equal(a.run('collectedContains(2) && collectedContains(3) && !collectedContains(4)'),true);
  assert.equal(a.run('collectedContains(1)'),false);
  a.run('setT(3);');
  assert.equal(a.run('collectedContains(2) && !collectedContains(1)'),true);
  assert.match(a.node('accumulated').getAttribute('d'),/^M/);
});

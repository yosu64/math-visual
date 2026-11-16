// node --test tools/test/linear-inequality-region.test.cjs
// Browser-independent checks of the interactive lesson's own JavaScript.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.join(__dirname,'../..');
const article = fs.readFileSync(path.join(root,'math-ii/linear-inequality-region-sweep.html'),'utf8');
const html = fs.readFileSync(path.join(root,'index.html'),'utf8');
const org = fs.readFileSync(path.join(root,'index.org'),'utf8');
const script = article.match(/<script>([\s\S]*?)<\/script>/);
assert.ok(script,'lesson includes an inline script');
class Element {
 constructor(id){
  this.id=id;this.attributes={};this.handlers={};this.children=[];
  this.value='';this.checked=false;this.textContent='';
  this.classList={toggle:()=>{}};
 }
 setAttribute(k,v){this.attributes[k]=String(v);}
 appendChild(v){this.children.push(v);return v;}
 addEventListener(name,cb){this.handlers[name]=cb;}
 emit(name,evt={}){assert.ok(this.handlers[name],'listener '+this.id+'/'+name);this.handlers[name](evt);}
}
function load(){
 const ids=new Set(Array.from(article.matchAll(/\bid="([^"]+)"/g),m=>m[1]));
 assert.equal(ids.size,Array.from(article.matchAll(/\bid="/g)).length,'unique HTML IDs');
 const elements=new Map();
 for(const id of ids)elements.set(id,new Element(id));
 const events={};
 let scheduled;
 const document={
  getElementById(id){assert.ok(ids.has(id),'missing element #'+id);return elements.get(id);},
  createElementNS(_namespace,tag){return new Element(tag);},
  addEventListener(name,cb){events[name]=cb;},
  documentElement:{requestFullscreen:async()=>{}},
  exitFullscreen:async()=>{}
 };
 const context=vm.createContext({document,requestAnimationFrame:cb=>{scheduled=cb;}});
 vm.runInContext(script[1],context,{filename:'linear-inequality-region-sweep.html'});
 return {
  element:id=>elements.get(id),
  click:id=>elements.get(id).emit('click'),
  change:(id,property,value)=>elements.get(id).emit('change',{target:{[property]:value}}),
  input:k=>elements.get('k').emit('input',{target:{value:String(k)}}),
  state:()=>vm.runInContext('state',context),
  frame:t=>scheduled(t),
  key:(key,code)=>events.keydown({key,code,target:{tagName:'DIV'},preventDefault(){}})
 };
}
test('index is linked under math II at textbook page 108, retaining Pick Up',()=>{
 assert.match(org,/:PATH: \.\/math-ii\/linear-inequality-region-sweep\.html/);
 assert.match(org,/:PAGE: 108/);
 assert.match(html,/href="\.\/math-ii\/linear-inequality-region-sweep\.html"/);
 assert.match(html,/class="featured-section"/);
 const section=html.split('<h2>数II</h2>')[1].split('<h2>数B</h2>')[0];
 const pages=Array.from(section.matchAll(/深進数学II p\.(\d+)/g),m=>Number(m[1]));
 assert.deepEqual(pages,[9,10,88,89,106,108]);
});
test('single vertical line begins at the correct open endpoint',()=>{
 const app=load();
 assert.equal(app.element('globalEquation').textContent,'y > 2x − 1');
 assert.equal(app.element('numericEquation').textContent,'k = 0 だから y > −1');
 assert.equal(app.element('swept').attributes.visibility,'hidden');
 assert.equal(app.element('boundary').attributes['stroke-dasharray'],'10 7');
 assert.equal(app.element('endpoint').attributes.fill,'#fff');
 app.input(1);
 assert.equal(app.element('numericEquation').textContent,'k = 1 だから y > 1');
 assert.equal(app.element('endpoint').attributes.cy,String(40+(4-1)*70));
 app.input(3);
 assert.equal(app.element('accepted').attributes.visibility,'hidden');
 assert.match(app.element('viewportNote').textContent,/表示しているグラフの外側/);
});
test('collect mode only shades the swept x-range and finishes across the plot',()=>{
 const app=load();
 app.click('collect');
 assert.equal(app.state().k,-4);
 assert.equal(app.element('swept').attributes.visibility,'visible');
 app.input(0);
 assert.match(app.element('swept').attributes.d,/M55,40 L335,40/);
 app.click('finish');
 assert.equal(app.state().k,4);
 assert.match(app.element('stepText').textContent,/左から右まで/);
 app.click('single');
 assert.equal(app.element('swept').attributes.visibility,'hidden');
 assert.equal(app.state().k,0);
});
test('lower side and equality update inequality, segment and boundary',()=>{
 const app=load();
 app.change('direction','value','lower');
 assert.equal(app.element('globalEquation').textContent,'y < 2x − 1');
 assert.equal(app.element('numericEquation').textContent,'k = 0 だから y < −1');
 assert.equal(app.element('accepted').attributes.visibility,'visible');
 app.change('inclusive','checked',true);
 assert.equal(app.element('globalEquation').textContent,'y ≤ 2x − 1');
 assert.equal(app.element('boundary').attributes['stroke-dasharray'],'none');
 assert.equal(app.element('endpoint').attributes.fill,'#087aab');
 app.click('finish');
 assert.equal(app.element('swept').attributes.visibility,'visible');
});
test('play and keyboard controls move k and pause without autoplay',()=>{
 const app=load();
 assert.equal(app.state().running,false);
 app.key('ArrowRight','ArrowRight');
 assert.equal(app.state().k,0.1);
 app.click('play');
 assert.equal(app.state().mode,'collect');
 assert.equal(app.state().k,-4);
 app.frame(1000);app.frame(1100);
 assert.ok(app.state().k>-4);
 app.click('play');
 assert.equal(app.state().running,false);
});

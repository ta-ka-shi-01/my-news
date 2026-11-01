// Dependency-free checks for the actual inline UI script, using a small DOM fixture.
const {readFileSync}=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
class Element {
  constructor(tag){this.tagName=tag;this.children=[];this.attributes={};this.textContent='';}
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(...nodes){this.children=nodes;}
  setAttribute(key,value){this.attributes[key]=value;}
  focus(){this.focused=true;}
}
const nodes={tabs:new Element('nav'),items:new Element('main'),status:new Element('span')};
const descendants=(element,tag)=>element.children.flatMap(child=>[...(child.tagName===tag?[child]:[]),...descendants(child,tag)]);
const script=readFileSync('index.html','utf8').match(/<script>([\s\S]*?)<\/script>/)[1];
const context=vm.createContext({document:{createElement:tag=>new Element(tag),getElementById:id=>nodes[id],querySelector:()=>descendants(nodes.items,'h2')[0]},fetch:()=>new Promise(()=>{})});
vm.runInContext(script,context);
const run=code=>vm.runInContext(code,context);
run("collection=Object.fromEntries(cats.slice(1).map(c=>[c,{status:'ok'}]))");
run(`data=cats.slice(1).flatMap(category=>Array.from({length:7},(_,i)=>({category,title:category+i,url:'https://example.org/'+i,source:'Test',published:new Date(Date.UTC(2026,10,i+1)).toISOString(),priority:'通常'})));draw()`);
assert.deepEqual(descendants(nodes.items,'h2').map(n=>n.textContent),['ゲーム業界','成人向け同人ゲーム','野球']);
assert.equal(descendants(nodes.items,'article').length,15);
assert.ok(nodes.items.children.every(s=>descendants(s,'article').length===5));
assert.equal(descendants(nodes.items,'a')[0].textContent,'ゲーム業界6');
assert.equal(descendants(nodes.items,'span').filter(n=>n.className?.startsWith('category')).length,15);
for(let i=0;i<3;i++){
  run(`selectCategory('すべて')`);
  descendants(nodes.items,'button')[i].onclick();
  assert.equal(descendants(nodes.items,'article').length,7);
  assert.equal(descendants(nodes.items,'h2').length,1);
  assert.equal(descendants(nodes.items,'h2')[0].focused,true);
  assert.equal(nodes.tabs.children[i+1].attributes['aria-pressed'],'true');
  assert.ok(descendants(nodes.items,'a').every(n=>n.textContent.startsWith(['ゲーム業界','成人向け同人ゲーム','野球'][i])));
}
run(`data=data.filter(a=>a.category!=='成人向け同人ゲーム');selectCategory('すべて')`);
assert.equal(descendants(nodes.items,'p')[0].textContent,'成人向け同人ゲームの新着記事はありません。');
nodes.tabs.children[2].onclick();
assert.equal(descendants(nodes.items,'article').length,0);
assert.equal(descendants(nodes.items,'p').length,1);
run(`data=[];selectCategory('すべて')`);
assert.equal(descendants(nodes.items,'p').length,3);
assert.equal(descendants(nodes.items,'button').length,3);
run(`data=JSON.parse(${JSON.stringify(readFileSync('news.json','utf8'))}).articles;draw()`);
assert.ok(descendants(nodes.items,'article').length<=15);
console.log('UI checks passed: section order, latest five, labels, all category links/tabs, empty states, real news.json.');

// Exercise the actual asynchronous fetch chain, including a newer failure log.
async function fetchScenario(news,diagnostics,options={}){
  const elements={tabs:new Element('nav'),items:new Element('main'),status:new Element('span')};
  const ctx=vm.createContext({document:{createElement:tag=>new Element(tag),getElementById:id=>elements[id],querySelector:()=>descendants(elements.items,'h2')[0]},
    fetch:async url=>{
      if(url.includes('diagnostics')){if(options.noDiagnostics)throw Error('missing');return {ok:true,json:async()=>diagnostics};}
      return {ok:!options.failNews,json:async()=>news};
    }});
  await vm.runInContext(script,ctx);
  return {elements,ctx};
}
(async()=>{
  const date='2026-11-01T00:00:00Z';
  const news={updated_at:date,articles:[],diagnostics:{attempted_at:date,categories:Object.fromEntries(['ゲーム業界','成人向け同人ゲーム','野球'].map(c=>[c,{status:'ok'}]))}};
  const failed={attempted_at:'2026-11-01T06:00:00Z',categories:Object.fromEntries(['ゲーム業界','成人向け同人ゲーム','野球'].map(c=>[c,{status:'failed'}]))};
  let result=await fetchScenario(news,failed);
  assert.ok(descendants(result.elements.items,'p').every(p=>!p.textContent.includes('新着記事はありません')));
  assert.ok(descendants(result.elements.items,'p').some(p=>p.textContent.includes('収集に失敗')));
  failed.categories['成人向け同人ゲーム'].status='partial';
  result=await fetchScenario(news,failed);
  assert.ok(descendants(result.elements.items,'p').some(p=>p.textContent.includes('一部の検索')));
  result=await fetchScenario(news,{...failed,attempted_at:'2026-10-31T00:00:00Z'});
  assert.ok(descendants(result.elements.items,'p').some(p=>p.textContent==='成人向け同人ゲームの新着記事はありません。'));
  result=await fetchScenario({updated_at:date,articles:[]},null,{noDiagnostics:true});
  assert.ok(descendants(result.elements.items,'p').every(p=>p.textContent.includes('未確認')));
  result=await fetchScenario(news,null,{failNews:true});
  assert.equal(result.elements.status.textContent,'取得エラー');
  console.log('Fetch/UI checks passed: fresh diagnostics, failed/partial states, legacy fallback, stale log ignored, fetch error.');
})().catch(error=>{console.error(error);process.exitCode=1;});

const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
async function page(){
  class Node {
    constructor(){this.value='';this.hidden=false;this.children=[];this.listeners={};}
    addEventListener(t,f){(this.listeners[t]??=[]).push(f);}
    async fire(t){for(const f of this.listeners[t]||[])await f({preventDefault(){},currentTarget:this});}
    append(...nodes){this.children.push(...nodes);}
    replaceChildren(){this.children=[];}
  }
  const nodes=new Map();const html=fs.readFileSync(path.join(__dirname,'../static/index.html'),'utf8');
  for(const match of html.matchAll(/id="([^"]+)"/g))nodes.set(match[1],new Node());
  const document=new Node();Object.assign(document,{getElementById:id=>{assert.ok(nodes.has(id),id);return nodes.get(id);},createElement:()=>new Node()});
  const window=new Node(),calls=[];
  const state={turns:[],total:0,notes:{draft:{text:'Recovered draft',revision:2},context:{text:'Synthetic background',revision:1}},remaining:20,next_omitted:0,connected:true};
  let failed=false;const flush=()=>new Promise(resolve=>setImmediate(resolve));
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../static/chat.js'),'utf8'),{
    window,document,Date,confirm:()=>true,crypto:{randomUUID:()=> 'synthetic-id'},setTimeout:()=>1,clearTimeout(){},
    fetch:async(url,options)=>{
      calls.push({url,options});let data;
      if(url.endsWith('/send')){
        if(failed)return{ok:false,status:503,json:async()=>({error:'Unavailable'})};
        const payload=JSON.parse(options.body);state.turns=[{id:'1',created:1,prompt:payload.prompt,answer:'safe <script>text</script>',status:'completed',omitted:0}];state.total=1;state.notes.draft={text:'',revision:3};data={id:'1'};
      }else if(url.endsWith('/chat/state'))data=state;
      else if(url.endsWith('/draft'))data={revision:3};
      else data={csrf:'fixture'};
      return{ok:true,status:200,json:async()=>data};
    }
  });
  await document.fire('daily:unlocked');await flush();return{get:id=>nodes.get(id),calls,state,window,document,flush,setFailed:v=>{failed=v;}};
}
test('restores explicit draft without a model call and sends long input unchanged',async()=>{
  const p=await page();assert.equal(p.get('chat-input').value,'Recovered draft');
  assert.ok(p.calls.every(c=>c.options.method===undefined));
  const text='🙂abc'.repeat(1000)+'END';p.get('chat-input').value=text;await p.get('chat-input').fire('input');
  await p.get('chat-form').fire('submit');
  const call=p.calls.find(c=>c.url.endsWith('/send'));assert.equal(JSON.parse(call.options.body).prompt,text);
  assert.equal(call.options.headers['X-CSRF-Token'],'fixture');assert.equal(p.get('chat-input').value,'');
  assert.equal(p.get('chat-turns').children[0].children[3].textContent,'safe <script>text</script>');
});
test('over-limit and failed requests preserve edits and retry identity',async()=>{
  const p=await page();p.get('chat-input').value='x'.repeat(12001);await p.get('chat-input').fire('input');
  await p.get('chat-form').fire('submit');assert.ok(!p.calls.some(c=>c.url.endsWith('/send')));
  assert.equal(p.get('chat-input').value.length,12001);
  p.get('chat-input').value='keep me';await p.get('chat-input').fire('input');p.setFailed(true);
  await p.get('chat-form').fire('submit');await p.get('chat-form').fire('submit');
  const sent=p.calls.filter(c=>c.url.endsWith('/send'));assert.equal(sent[0].options.body,sent[1].options.body);
  assert.equal(p.get('chat-input').value,'keep me');
});
test('saved draft uses observed revision and locking clears private DOM',async()=>{
  const p=await page();await p.get('draft-save').fire('click');
  const sent=p.calls.find(c=>c.url.endsWith('/draft'));assert.equal(JSON.parse(sent.options.body).revision,2);
  assert.match(p.get('draft-status').textContent,/Saved/);
  await p.document.fire('daily:locked');assert.equal(p.get('chat-workspace').hidden,true);
  assert.equal(p.get('chat-input').value,'');
  assert.equal(p.get('chat-turns').children.length,0);
});

test('daily page has no user-editable background prompt and keeps saved draft',async()=>{
  const p=await page();
  assert.equal(p.get('chat-input').value,'Recovered draft');
  assert.ok(!p.calls.some(c=>c.url.endsWith('/context')));
  assert.ok(!p.calls.some(c=>c.url.endsWith('/send')));
  assert.match(fs.readFileSync(path.join(__dirname,'../static/index.html'),'utf8'),/id="conversation"/);
  assert.doesNotMatch(fs.readFileSync(path.join(__dirname,'../static/index.html'),'utf8'),/id="chat-context"/);
});

test('follow-up choice sends once with its source and preserves unsent edits',async()=>{
  const p=await page();p.state.turns=[{id:'source',created:1,kind:'checkin',prompt:'Synthetic check-in',answer:'One small step',status:'completed',result:{agents:[]}}];
  await p.document.fire('daily:unlocked');await p.flush();
  p.get('chat-input').value='Unsent edits';await p.get('chat-input').fire('input');
  const card=p.get('chat-turns').children[0];
  const actions=card.children.find(n=>n.className==='followup-actions');
  assert.equal(actions.children.length,3);
  await actions.children[0].fire('click');
  const sends=p.calls.filter(c=>c.url.endsWith('/send'));
  assert.equal(sends.length,1);
  assert.equal(JSON.parse(sends[0].options.body).reply_to,'source');
  assert.equal(p.get('chat-input').value,'Unsent edits');
});

test('urgent and running responses offer no routine follow-up choices',async()=>{
  for(const status of ['needs_attention','running','failed']){
    const p=await page();p.state.turns=[{id:'source',created:1,prompt:'Synthetic',answer:'Warning',status}];
    await p.document.fire('daily:unlocked');await p.flush();
    assert.ok(!p.get('chat-turns').children[0].children.some(n=>n.className==='followup-actions'));
    assert.ok(!p.calls.some(c=>c.url.endsWith('/send')));
  }
});

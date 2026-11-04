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
  const nodes=new Map();const html=fs.readFileSync(path.join(__dirname,'../static/chat.html'),'utf8');
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
        const payload=JSON.parse(options.body);state.turns=[{created:1,prompt:payload.prompt,answer:'safe <script>text</script>',status:'completed',omitted:0}];state.total=1;state.notes.draft={text:'',revision:3};data={id:'1'};
      }else if(url.endsWith('/chat/state'))data=state;
      else if(url.endsWith('/draft'))data={revision:3};
      else data={csrf:'fixture'};
      return{ok:true,status:200,json:async()=>data};
    }
  });
  await flush();return{get:id=>nodes.get(id),calls,state,window,flush,setFailed:v=>{failed=v;}};
}
test('restores explicit draft without a model call and sends long input unchanged',async()=>{
  const p=await page();assert.equal(p.get('chat-input').value,'Recovered draft');
  assert.ok(p.calls.every(c=>c.options.method===undefined));
  const text='🙂abc'.repeat(1000)+'END';p.get('chat-input').value=text;await p.get('chat-input').fire('input');
  await p.get('chat-form').fire('submit');
  const call=p.calls.find(c=>c.url.endsWith('/send'));assert.equal(JSON.parse(call.options.body).prompt,text);
  assert.equal(call.options.headers['X-CSRF-Token'],'fixture');assert.equal(p.get('chat-input').value,'');
  assert.equal(p.get('chat-turns').children[0].children[4].textContent,'safe <script>text</script>');
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
  await p.get('chat-lock').fire('click');assert.equal(p.get('chat-workspace').hidden,true);
  assert.equal(p.get('chat-input').value,'');assert.equal(p.get('chat-context').value,'');
  assert.equal(p.get('chat-turns').children.length,0);
});

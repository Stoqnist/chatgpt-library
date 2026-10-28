'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');

// Run the actual scripts together against a small DOM/event boundary. No model,
// Calendar, microphone, browser storage or speech provider is contacted.
async function page({runs=[],recognition=false,speech=true}={}){
  const html=fs.readFileSync(path.join(__dirname,'../static/index.html'),'utf8');
  const nodes=new Map();let focused=null;
  class Node {
    constructor(){this.hidden=false;this.disabled=false;this.open=false;this.value='';this.textContent='';this.children=[];this.listeners={};this.attrs={};this.classList={toggle(){}};}
    addEventListener(type,fn){(this.listeners[type]??=[]).push(fn);}
    dispatchEvent(event){for(const fn of this.listeners[event.type]||[])fn(event);}
    async fire(type,extra={}){for(const fn of this.listeners[type]||[])await fn({type,preventDefault(){},currentTarget:this,submitter:new Node(),...extra});}
    append(node){this.children.push(node);}
    replaceChildren(){this.children=[];}
    setAttribute(k,v){this.attrs[k]=v;}
    focus(){focused=this;}
    scrollIntoView(){}
    querySelectorAll(){return [];}
  }
  for(const m of html.matchAll(/<[^>]*\bid="([^"]+)"[^>]*>/g)){
    const n=new Node();n.hidden=/\bhidden\b/.test(m[0]);n.disabled=/\bdisabled\b/.test(m[0]);nodes.set(m[1],n);
  }
  const document=new Node();Object.assign(document,{readyState:'complete',hidden:false,getElementById:id=>{assert.ok(nodes.has(id),id);return nodes.get(id);},createElement:()=>new Node(),querySelectorAll:()=>[]});
  const calls=[],spoken=[],recognizers=[],timers=new Map();let clock=Date.now(),timerId=0,runId='submitted';
  class ClockDate extends Date{constructor(...args){super(...(args.length?args:[clock]));}static now(){return clock;}}
  class Recognition {
    constructor(){recognizers.push(this);}
    start(){this.started=true;}
    abort(){this.aborted=true;this.onend?.();}
    stop(){this.stopped=true;}
  }
  const window=new Node();window.confirm=()=>true;
  if(recognition)window.SpeechRecognition=Recognition;
  if(speech){window.SpeechSynthesisUtterance=class{constructor(text){this.text=text;}};window.speechSynthesis={speak:u=>spoken.push(u),cancel(){}};}
  const state={csrf:'synthetic',connected:true,remaining:20,runs};
  const context=vm.createContext({document,window,Date:ClockDate,Event:class{constructor(type){this.type=type;}},CustomEvent:class{constructor(type,data){this.type=type;Object.assign(this,data);}},URLSearchParams,location:{search:''},history:{},confirm:()=>true,crypto:{randomUUID:()=> 'synthetic-id'},
    setTimeout(fn,ms){const id=++timerId;timers.set(id,{fn,ms});return id;},clearTimeout(id){timers.delete(id);},setInterval(){},
    fetch:async(url,options)=>{calls.push({url,options});if(url.endsWith('/run'))return{ok:true,status:200,json:async()=>({id:runId})};return{ok:true,status:200,json:async()=>state};}});
  for(const file of ['app.js','morning.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/'+file),'utf8'),context);
  const flush=()=>new Promise(resolve=>setImmediate(resolve));await flush();
  return {get:id=>nodes.get(id),document,window,calls,spoken,recognizers,state,timers,flush,context,focused:()=>focused,refresh:()=>vm.runInContext('refresh()',context),advance:ms=>{clock+=ms;},tick:()=>vm.runInContext('refreshDate()',context)};
}
const completed=(id='old',created=Date.now()/1000)=>({id,created,prompt:'Fictional kitchen check-in',status:'completed',result:{message:'A small plan for today',next_steps:[{text:'A fictional step',owner:'Home'}]}});

test('login/reload never selects historical or same-day completed plans; history is collapsed and dated',async()=>{
  for(const age of [0,86400*2]){
    const p=await page({runs:[completed('fixture',Date.now()/1000-age)]});
    assert.equal(p.get('result').hidden,true);assert.equal(p.get('checkin-state').textContent,'Not started');
    assert.equal(p.get('history-section').open,false);assert.equal(p.get('history-section').hidden,false);
    assert.equal(p.get('checkin-form').hidden,true);
    assert.equal(p.calls.length,1);assert.ok(p.calls.every(c=>c.options.method===undefined));
    assert.equal(p.spoken.length,0);assert.equal(p.recognizers.length,0);
    await p.get('history').children[0].fire('click');
    assert.match(p.get('result-context').textContent,/Previous check-in/);
    assert.doesNotMatch(p.get('result-title').textContent,/today/);
    assert.equal(p.get('checkin-state').textContent,'Not started');
    await p.refresh();assert.match(p.get('result-context').textContent,/Previous check-in/);
  }
});

test('recover a working run without replacing unsent work or making another run request',async()=>{
  const run={...completed('working'),status:'running',result:{message:'Working'}};
  const p=await page({runs:[run,completed()]});
  assert.equal(p.get('checkin-state').textContent,'Working');assert.equal(p.get('morning-open').disabled,true);
  p.get('prompt').value='My still unsent edit';await p.get('prompt').fire('input');
  run.status='completed';await p.refresh();
  assert.equal(p.get('prompt').value,'My still unsent edit');assert.equal(p.get('checkin-state').textContent,'Draft in progress');
  assert.ok(p.calls.every(c=>c.options.method===undefined));
});

test('one user tap opens guided draft and greeting, never microphone or model; review is separate from submit',async()=>{
  const p=await page({recognition:true});await p.get('morning-open').fire('click');
  assert.equal(p.spoken.length,1);assert.match(p.spoken[0].text,/Welcome.*sleep/);
  assert.equal(p.recognizers.length,0);assert.equal(p.calls.length,1);
  assert.equal(p.get('checkin-state').textContent,'Draft in progress');
  assert.equal(p.get('morning-companion').hidden,false);
  assert.equal(p.focused(),p.get('morning-greeting'));
  p.get('morning-answer').value='A fictional report.';
  for(let i=0;i<3;i++)await p.get('morning-next').fire('click');
  assert.equal(p.get('checkin-form').hidden,false);assert.equal(p.get('morning-companion').hidden,true);
  assert.match(p.get('prompt').value,/A fictional report/);assert.equal(p.calls.length,1);
  const submitted=completed('submitted');p.state.runs=[submitted];
  await p.get('checkin-form').fire('submit');
  assert.equal(p.calls.filter(c=>c.url.endsWith('/run')).length,1);
  assert.equal(p.get('checkin-state').textContent,"Today's completed plan");
  p.advance(86400*1000);p.tick();
  assert.match(p.get('result-context').textContent,/Previous check-in/);
  assert.doesNotMatch(p.get('result-title').textContent,/today/);
  assert.equal(p.get('checkin-state').textContent,'Not started');
});

test('unsupported TTS still shows keyboard microphone guidance and never opens recording',async()=>{
  const p=await page({speech:false,recognition:true});
  await p.get('morning-open').fire('click');
  assert.equal(p.get('morning-voice-toggle').disabled,true);
  assert.match(p.get('morning-speech-status').textContent,/unavailable.*keyboard dictation/);
  assert.equal(p.get('morning-answer').value,'');
  assert.equal(p.recognizers.length,0);
  assert.equal(p.calls.length,1);
});

test('each next-question tap speaks the newly visible question, without starting a microphone',async()=>{
  const p=await page({recognition:true});
  await p.get('morning-open').fire('click');
  assert.equal(p.spoken.length,1);
  p.get('morning-answer').value='First fictional answer';
  await p.get('morning-next').fire('click');
  assert.equal(p.spoken.length,2);
  assert.equal(p.spoken[1].text,p.get('morning-question').textContent);
  p.get('morning-answer').value='Second fictional answer';
  await p.get('morning-next').fire('click');
  assert.equal(p.spoken.length,3);
  assert.equal(p.spoken[2].text,p.get('morning-question').textContent);
  assert.equal(p.recognizers.length,0);
  assert.equal(p.calls.length,1);
});

test('voice off prevents subsequent speech, Hear again is explicit, voice on resumes',async()=>{
  const p=await page();await p.get('morning-open').fire('click');
  await p.get('morning-voice-toggle').fire('click');
  assert.equal(p.get('morning-voice-toggle').attrs['aria-pressed'],'false');
  await p.get('morning-next').fire('click');
  assert.equal(p.spoken.length,1);
  await p.get('morning-hear').fire('click');
  assert.equal(p.spoken.length,2);
  await p.get('morning-voice-toggle').fire('click');
  assert.equal(p.spoken.length,3);
  assert.equal(p.get('morning-voice-toggle').attrs['aria-pressed'],'true');
  assert.equal(p.spoken[2].text,p.get('morning-question').textContent);
});

test('TTS error and silent non-start show an honest fallback; voice off stops playback',async()=>{
  const p=await page();await p.get('morning-open').fire('click');
  p.spoken[0].onerror();assert.match(p.get('morning-speech-status').textContent,/could not play/);
  await p.get('morning-hear').fire('click');
  [...p.timers.values()].find(t=>t.ms===5000).fn();
  assert.match(p.get('morning-speech-status').textContent,/did not start/);
  await p.get('morning-hear').fire('click');
  await p.get('morning-voice-toggle').fire('click');
  assert.equal(p.get('morning-voice-toggle').attrs['aria-pressed'],'false');
  assert.equal(p.timers.size,0);
});

test('backgrounding and locking stop playback and discard private guided draft',async()=>{
  const p=await page({recognition:true});
  await p.get('morning-open').fire('click');
  assert.equal(p.spoken.length,1);
  p.document.hidden=true;await p.document.fire('visibilitychange');
  assert.match(p.get('morning-speech-status').textContent,/background/);
  assert.equal(p.recognizers.length,0);
  p.get('morning-answer').value='Unsent synthetic draft';
  vm.runInContext('lockUI()',p.context);
  assert.equal(p.get('morning-answer').value,'');
  assert.equal(p.get('morning-companion').hidden,true);
  assert.equal(p.get('history-section').open,false);
  assert.equal(p.get('checkin-state').textContent,'Not started');
});

test('local dates label a UTC-tomorrow run as today where appropriate',async()=>{
  const previous=process.env.TZ;process.env.TZ='America/Los_Angeles';
  try{
    const p=await page();
    vm.runInContext("testRun={created:Date.parse('2026-10-29T01:00:00Z')/1000};",p.context);
    // Set clock to 18:30 PDT on Oct 28. The run's UTC day is Oct 29, local day is Oct 28.
    p.advance(Date.parse('2026-10-29T01:30:00Z')-vm.runInContext('Date.now()',p.context));
    assert.equal(vm.runInContext('isToday(testRun)',p.context),true);
    p.advance(7*3600*1000);assert.equal(vm.runInContext('isToday(testRun)',p.context),false);
  }finally{if(previous===undefined)delete process.env.TZ;else process.env.TZ=previous;}
});

test('historical failed and safety-interrupted check-ins retain their actionable message',async()=>{
  for(const status of ['failed','interrupted','needs_attention','partial']){
    const p=await page({runs:[{...completed(),status,result:{message:'Important original warning'}}]});
    await p.get('history').children[0].fire('click');
    assert.equal(p.get('result-title').textContent,'Important original warning');
    assert.match(p.get('result-context').textContent,/Previous check-in/);
    assert.doesNotMatch(p.get('result-source').textContent,/can take about a minute/);
  }
});

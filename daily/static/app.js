'use strict';
const $=id=>document.getElementById(id);
let csrf='', state=null, activeId=null, poll=null, request=null, busy=false;
const notice=(message,error=false)=>{$('notice').textContent=message;$('notice').classList.toggle('error',error);};
async function api(path,data){
  const options={credentials:'same-origin',cache:'no-store',headers:{}};
  if(data!==undefined){options.method='POST';options.headers={'Content-Type':'application/json','X-CSRF-Token':csrf};options.body=JSON.stringify(data);}
  const response=await fetch('/daily/api/'+path,options);
  const result=await response.json();
  if(response.status===401&&path!=='login'){lockUI();}
  if(!response.ok)throw new Error(result.error||'Something went wrong. Please try again.');
  return result;
}
function lockUI(){
  clearTimeout(poll);state=null;csrf='';activeId=null;request=null;busy=false;
  $('locked').hidden=false;$('workspace').hidden=true;$('prompt').value='';$('api-key').value='';
  $('plan').replaceChildren();$('history').replaceChildren();$('result').hidden=true;
}
function el(tag,text,className){const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(className)node.className=className;return node;}
function renderRun(run){
  $('result').hidden=false;$('result').setAttribute('aria-busy',String(run.status==='running'));
  $('run-status').textContent=({running:'Working',completed:'Ready',partial:'Partial',failed:'Needs attention',interrupted:'Interrupted',needs_attention:'Pause & seek help'})[run.status]||run.status;
  $('result-title').textContent=run.result.message||'Preparing your plan.';
  $('result-source').textContent=run.result.source||'This can take about a minute. You can return to this page.';
  $('progress').replaceChildren();$('plan').replaceChildren();$('questions').replaceChildren();
  if(run.result.next_steps?.length){const steps=el('ol',undefined,'next-steps');for(const step of run.result.next_steps){const item=el('li');item.append(el('span',step.text));item.append(el('small',step.owner));steps.append(item);}$('plan').append(steps);}
  for(const agent of run.result.agents||[]){
    $('progress').append(el('span',agent.name+' · '+({completed:'ready',waiting:'working',failed:'unavailable'}[agent.status]||agent.status),agent.status));
    if(agent.status==='waiting')continue;
    const card=el('details',undefined,'agent-card');card.append(el('summary',agent.name+' perspective'));card.append(el('p',agent.summary));
    if(agent.suggestions?.length){const list=el('ul');for(const text of agent.suggestions)list.append(el('li',text));card.append(list);}
    for(const text of agent.missing_context||[])card.append(el('p','Still unknown: '+text,'quiet'));
    $('plan').append(card);
  }
  if(run.result.questions?.length){$('questions').append(el('h3','Only if you can add a little more'));for(const q of run.result.questions)$('questions').append(el('p',q));}
}
async function refresh(){
  try{state=await api('state');}catch(error){if(!$('workspace').hidden)notice(error.message,true);return;}
  csrf=state.csrf;$('locked').hidden=true;$('workspace').hidden=false;
  const running=state.runs.find(r=>r.status==='running');busy=Boolean(running);
  $('run-button').disabled=busy||!state.connected;
  $('run-button').textContent=busy?'Your specialists are working…':'Find my next steps ↗';
  $('connection').textContent=state.connected?`${state.remaining} check-ins available today`:'Add your API key in Settings to begin';
  if(!state.connected){$('settings').hidden=false;$('settings-toggle').setAttribute('aria-expanded','true');}
  const calendar=state.calendar||{configured:false,connected:false};
  $('calendar-setup').hidden=!calendar.configured;
  $('calendar-status').textContent=calendar.connected
    ? 'Google Calendar permission is connected. Availability is not used in plans yet.'
    : 'Connect Google Calendar for free/busy-only access.';
  $('calendar-connect').hidden=calendar.connected;
  $('calendar-disconnect').hidden=!calendar.connected;
  if(running)activeId=running.id;
  if(!activeId&&state.runs.length)activeId=state.runs[0].id;
  const active=state.runs.find(r=>r.id===activeId);if(active)renderRun(active);else $('result').hidden=true;
  $('history').replaceChildren();$('history-section').hidden=state.runs.length<1;
  for(const run of state.runs){const b=el('button',run.prompt.slice(0,95)+(run.prompt.length>95?'…':''));b.type='button';b.append(el('small',new Date(run.created*1000).toLocaleString([], {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'})+' · '+run.status));b.addEventListener('click',()=>{activeId=run.id;renderRun(run);$('result').scrollIntoView({block:'start'});});$('history').append(b);}
  clearTimeout(poll);if(running)poll=setTimeout(refresh,1800);
}
$('date').textContent=new Date().toLocaleDateString([], {weekday:'long',month:'long',day:'numeric'});
$('login-form').addEventListener('submit',async e=>{e.preventDefault();const button=e.submitter;button.disabled=true;try{await api('login',{password:$('password').value});$('password').value='';notice('');await refresh();}catch(error){notice(error.message,true);}finally{button.disabled=false;}});
$('settings-toggle').addEventListener('click',()=>{$('settings').hidden=!$('settings').hidden;$('settings-toggle').setAttribute('aria-expanded',String(!$('settings').hidden));});
$('key-form').addEventListener('submit',async e=>{e.preventDefault();e.submitter.disabled=true;try{await api('settings',{api_key:$('api-key').value.trim()});$('api-key').value='';$('settings').hidden=true;$('settings-toggle').setAttribute('aria-expanded','false');notice('Key saved. Your first check-in will test the connection.');await refresh();}catch(error){notice(error.message,true);}finally{e.submitter.disabled=false;}});
$('checkin-form').addEventListener('submit',async e=>{e.preventDefault();if(busy)return;const prompt=$('prompt').value.trim();if(!request||request.prompt!==prompt)request={prompt,request_id:crypto.randomUUID()};busy=true;$('run-button').disabled=true;notice('');try{const r=await api('run',request);activeId=r.id;request=null;await refresh();$('result').scrollIntoView({block:'start'});}catch(error){notice(error.message,true);busy=false;await refresh();}});
for(const button of document.querySelectorAll('[data-starter]'))button.addEventListener('click',()=>{if($('prompt').value.trim()&&!confirm('Replace your current check-in text?'))return;$('prompt').value=button.dataset.starter;$('prompt').focus();request=null;});
$('logout').addEventListener('click',async()=>{try{await api('logout',{});lockUI();notice('Your space is locked.');}catch(error){notice(error.message,true);}});
$('calendar-connect').addEventListener('click',async e=>{
  const button=e.currentTarget;button.disabled=true;
  try{
    const {authorization_url}=await api('calendar/connect',{});
    if(!authorization_url?.startsWith('https://accounts.google.com/o/oauth2/v2/auth?'))
      throw new Error('The Calendar sign-in address was invalid.');
    location.assign(authorization_url);
  }catch(error){notice(error.message,true);button.disabled=false;}
});
$('calendar-disconnect').addEventListener('click',async e=>{
  if(!confirm('Disconnect Google Calendar from Stoq? This removes its saved authorization on this server.'))return;
  const button=e.currentTarget;button.disabled=true;
  try{
    await api('calendar/disconnect',{});
    await refresh();
    notice('Calendar disconnected from Stoq. Revoke the app in Google Account settings if needed.');
  }catch(error){notice(error.message,true);}finally{button.disabled=false;}
});
$('clear').addEventListener('click',async()=>{if(!confirm('Delete your saved check-ins and plans? This cannot be undone.'))return;try{await api('clear',{});activeId=null;await refresh();notice('Check-in history cleared.');}catch(error){notice(error.message,true);}});
if(new URLSearchParams(location.search).get('calendar')==='connected'){
  history.replaceState(null,'','/daily/');
  notice('Calendar authorization saved. Availability is not used in plans yet.');
}
refresh();

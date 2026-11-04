'use strict';
(() => {
  const get=id=>document.getElementById(id);
  let csrf='', timer=null, epoch=0, loaded=false, busy=false, request=null;
  let revision=0, edited=false;
  function stopSpeech(){if(window.speechSynthesis)window.speechSynthesis.cancel();}
  document.addEventListener('visibilitychange',()=>{if(document.hidden)stopSpeech();});
  window.addEventListener('pagehide',stopSpeech);
  const notice=text=>{get('chat-notice').textContent=text;};
  function lock(){
    stopSpeech();epoch++;clearTimeout(timer);csrf='';loaded=false;busy=false;request=null;
    edited=false;
    get('chat-workspace').hidden=true;get('chat-locked').hidden=false;
    get('chat-input').value='';get('chat-turns').replaceChildren();
  }
  async function api(path,data){
    const options={credentials:'same-origin',cache:'no-store',headers:{}};
    if(data!==undefined){options.method='POST';options.headers={'Content-Type':'application/json','X-CSRF-Token':csrf};options.body=JSON.stringify(data);}
    const response=await fetch('/daily/api/'+path,options);
    const value=await response.json();
    if(response.status===401){lock();document.dispatchEvent(new Event('daily:session-expired'));}
    if(!response.ok)throw Error(value.error||'The request failed. Your unsent edits are still here unless the session expired.');
    return value;
  }
  const node=(tag,text)=>{const n=document.createElement(tag);n.textContent=text;return n;};
  function count(){get('chat-count').textContent=Array.from(get('chat-input').value).length.toLocaleString()+' / 12,000 characters. Text is never cut to fit.';}
  function render(data){
    get('chat-workspace').hidden=false;get('chat-locked').hidden=true;
    if(!loaded||!edited){
      get('chat-input').value=data.notes.draft.text;
      revision=data.notes.draft.revision;
    }
    if(!loaded)get('draft-status').textContent=data.notes.draft.text?'Saved draft restored.':'Unsent text is recoverable only after Save draft succeeds.';
    loaded=true;busy=data.turns.some(t=>t.status==='running');
    get('chat-send').disabled=busy||!data.connected;
    get('chat-send').textContent=busy?'Coordinator working…':'Send to coordinator';
    get('chat-usage').textContent=data.connected?`${data.remaining} shared requests remain.`:'API key missing. Open Daily Settings above for a setup guide; API billing is separate from ChatGPT.';
    get('chat-coverage').textContent=`Showing the latest ${data.turns.length} of ${data.total} saved exchanges. Replies use a bounded recent history; ${data.next_omitted} older exchanges would currently be omitted. Export includes all saved exchanges.`;
    get('chat-turns').replaceChildren();
    for(const turn of data.turns){
      const article=node('article','');article.className='panel';
      article.append(node('p',new Date(turn.created*1000).toLocaleString()+' · '+turn.status));
      article.append(node('h2','You'));const prompt=node('p',turn.prompt);prompt.className='conversation-text';article.append(prompt);
      article.append(node('h2','Stoq'));const reply=node('p',turn.answer||turn.error||'Your message is saved. Preparing a reply…');reply.className='conversation-text';article.append(reply);
      if(turn.answer&&window.speechSynthesis&&window.SpeechSynthesisUtterance){
        const listen=node('button','Listen');listen.type='button';listen.className='text-button';
        listen.addEventListener('click',()=>{stopSpeech();notice('If audio does not play, read the reply below.');window.speechSynthesis.speak(new window.SpeechSynthesisUtterance(turn.answer));});
        const stop=node('button','Stop audio');stop.type='button';stop.className='text-button';stop.addEventListener('click',stopSpeech);article.append(listen,stop);
      }
      if(turn.omitted)article.append(node('small',`${turn.omitted} older exchanges were not included in this reply.`));
      get('chat-turns').append(article);
    }
    count();
  }
  async function refresh(){
    const version=epoch;
    try{
      const state=await api('state');if(version!==epoch)return;csrf=state.csrf;
      const data=await api('chat/state');if(version!==epoch)return;render(data);
      clearTimeout(timer);if(busy)timer=setTimeout(refresh,1800);
    }catch(error){notice(error.message);}
  }
  const input=get('chat-input');
  input.addEventListener('input',()=>{
    edited=true;request=null;count();
    get('draft-status').textContent='Unsaved edits — use Save draft before leaving.';
  });
  get('draft-save').addEventListener('click',async e=>{
    const button=e.currentTarget,text=input.value,version=epoch;
    button.disabled=true;
    try{
      const result=await api('chat/draft',{text,revision});
      if(version!==epoch)return;
      revision=result.revision;
      edited=input.value!==text;
      get('draft-status').textContent=edited
        ?'Earlier text saved; your newest edits are still unsaved.':'Saved on your server.';
    }catch(error){notice(error.message);}
    finally{button.disabled=false;}
  });
  get('chat-form').addEventListener('submit',async e=>{
    e.preventDefault();if(busy)return;
    const prompt=get('chat-input').value,version=epoch;
    if(!prompt.trim()||Array.from(prompt).length>12000){notice('Send 1–12,000 characters. Your text is intact.');return;}
    if(!request||request.prompt!==prompt)request={prompt,request_id:crypto.randomUUID()};
    busy=true;get('chat-send').disabled=true;notice('');
    try{
      await api('chat/send',request);if(version!==epoch)return;
      request=null;
      if(get('chat-input').value===prompt){get('chat-input').value='';edited=false;}
      get('draft-status').textContent='Message saved. New unsent edits need Save draft.';
      await refresh();
    }catch(error){notice(error.message);busy=false;get('chat-send').disabled=false;}
  });
  get('chat-clear').addEventListener('click',async()=>{
    if(!confirm('Delete all conversation messages, saved drafts and background? Existing backups are not erased.'))return;
    try{await api('chat/clear',{});edited=false;loaded=false;request=null;await refresh();notice('Conversation deleted from the application.');}
    catch(error){notice(error.message);}
  });
  window.addEventListener('beforeunload',e=>{if(edited){e.preventDefault();e.returnValue='';}});
  document.addEventListener('daily:unlocked',refresh);
  document.addEventListener('daily:locked',lock);
})();

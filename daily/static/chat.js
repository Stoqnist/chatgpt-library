'use strict';
(() => {
  const get=id=>document.getElementById(id);
  let csrf='', timer=null, epoch=0, loaded=false, busy=false, request=null;
  let revision=0, edited=false, actionButtons=[];
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
  function render(data, dailyState){
    get('chat-workspace').hidden=false;get('chat-locked').hidden=true;
    if(!loaded||!edited){
      get('chat-input').value=data.notes.draft.text;
      revision=data.notes.draft.revision;
    }
    if(!loaded)get('draft-status').textContent=data.notes.draft.text?'Saved draft restored.':'Unsent text is recoverable only after Save draft succeeds.';
    loaded=true;busy=data.turns.some(t=>t.status==='running')||Boolean(dailyState.runs?.some(t=>t.status==='running'));
    get('chat-send').disabled=busy||!data.connected;
    get('chat-send').textContent=busy?'Preparing reply…':'Send';
    get('chat-usage').textContent=data.connected?`${data.remaining} shared requests remain.`:'API key missing. Open Daily Settings above for a setup guide; API billing is separate from ChatGPT.';
    get('chat-coverage').textContent=`Showing the latest ${data.turns.length} of ${data.total} retained exchanges (including seven-day check-ins). Replies use a bounded recent history; ${data.next_omitted} older exchanges would currently be omitted. Export includes all saved exchanges.`;
    get('chat-turns').replaceChildren();actionButtons=[];
    const older=node('details','');older.append(node('summary','Earlier messages and check-ins'));
    if(data.turns.length>1)get('chat-turns').append(older);
    for(const turn of data.turns){
      const article=node('article','');article.className='panel';
      article.append(node('p',new Date(turn.created*1000).toLocaleString()+' · '+turn.status));
      const source=node('details','');source.append(node('summary',turn.kind==='checkin'?'Your check-in':'Your message'));
      const prompt=node('p',turn.prompt);prompt.className='conversation-text';source.append(prompt);article.append(source);
      article.append(node('h3',turn.kind==='checkin'?'Your next steps':'Stoq'));const reply=node('p',turn.answer||turn.error||'Your message is saved. Preparing a reply…');reply.className='conversation-text';article.append(reply);
      if(turn===data.turns[data.turns.length-1]&&['completed','partial'].includes(turn.status)&&turn.answer){
        const actions=node('div','');actions.className='followup-actions';
        const choices=[
          ['Choose my next step','Help me choose one concrete next step from your last response.','Picks one priority and explains why. Nothing is scheduled.'],
          ['Make it manageable','Make your last response more manageable: suggest a smaller first step.','Breaks the advice into one easier action you can start.'],
          ['Explain this','Explain the reasoning and uncertainties in your last response.','Explains the suggestions, assumptions and what is still unknown.']
        ];
        for(const [index,[label,prompt,description]] of choices.entries()){
          const choice=node('div','');choice.className='followup-choice';
          const button=node('button',label);button.type='button';button.disabled=busy||!data.connected;
          const help=node('p',description);help.className='followup-description';
          help.id='followup-help-'+index;button.setAttribute('aria-describedby',help.id);
          button.addEventListener('click',()=>send(prompt,turn.id));
          actionButtons.push(button);choice.append(button,help);actions.append(choice);
        }
        article.append(actions,node('p','One tap sends one new AI request. These choices do not change external accounts.'));
      }
      if(turn===data.turns[data.turns.length-1]&&turn.kind==='conversation'&&turn.status==='failed'){
        const retry=node('button','Try replying again');retry.type='button';
        retry.disabled=busy||!data.connected;
        retry.addEventListener('click',()=>send(turn.prompt,turn.id));
        const info=node('p','Manually retries your saved message as a new AI request; the failed turn remains in history.');
        info.className='followup-description';article.append(retry,info);
        actionButtons.push(retry);
      }
      if(turn.kind==='checkin'&&turn.result){
        const details=node('details','');details.append(node('summary','Supporting perspectives'));
        for(const agent of turn.result.agents||[]){
          details.append(node('h3',agent.name+' · '+agent.status));
          details.append(node('p',agent.summary||''));
          for(const text of agent.suggestions||[])details.append(node('p',text));
          for(const text of agent.missing_context||[])details.append(node('p','Unknown: '+text));
        }
        article.append(details);
      }
      if(turn.answer&&window.speechSynthesis&&window.SpeechSynthesisUtterance){
        const listen=node('button','Listen');listen.type='button';listen.className='text-button';
        listen.addEventListener('click',()=>{stopSpeech();notice('If audio does not play, read the reply below.');window.speechSynthesis.speak(new window.SpeechSynthesisUtterance(turn.answer));});
        const stop=node('button','Stop audio');stop.type='button';stop.className='text-button';stop.addEventListener('click',stopSpeech);const audio=node('div','');audio.className='morning-actions';audio.append(listen,stop);article.append(audio);
      }
      if(turn.omitted)article.append(node('small',`${turn.omitted} older exchanges were not included in this reply.`));
      (turn===data.turns[data.turns.length-1]?get('chat-turns'):older).append(article);
    }
    count();
  }
  async function refresh(){
    const version=epoch;
    try{
      const state=await api('state');if(version!==epoch)return;csrf=state.csrf;
      const data=await api('chat/state');if(version!==epoch)return;render(data,state);
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
  async function send(prompt,replyTo=null){
    if(busy)return;
    const version=epoch;
    if(!prompt.trim()||Array.from(prompt).length>12000){notice('Send 1–12,000 characters. Your text is intact.');return;}
    if(!request||request.prompt!==prompt||request.reply_to!==replyTo)
      request={prompt,reply_to:replyTo,request_id:crypto.randomUUID()};
    busy=true;get('chat-send').disabled=true;actionButtons.forEach(b=>b.disabled=true);notice('');
    try{
      await api('chat/send',request);if(version!==epoch)return;
      request=null;
      if(!replyTo&&get('chat-input').value===prompt){get('chat-input').value='';edited=false;}
      if(!replyTo)get('draft-status').textContent='Message saved. New unsent edits need Save draft.';
      await refresh();
    }catch(error){
      if(version!==epoch)return;
      notice(error.message);busy=false;get('chat-send').disabled=false;
      actionButtons.forEach(b=>b.disabled=false);
    }
  }
  get('chat-form').addEventListener('submit',async e=>{
    e.preventDefault();await send(get('chat-input').value);
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

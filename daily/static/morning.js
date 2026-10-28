'use strict';
/* Three optional answers, spoken prompts and native keyboard dictation.
   No microphone APIs, audio uploads, browser storage or automatic model calls. */
const MorningCompanion = (() => {
  const questions = Object.freeze([
    Object.freeze({label:'Sleep and physical comfort',question:'How was your sleep, and how is your physical comfort today?'}),
    Object.freeze({label:'Energy and mood',question:'How are your energy, mood and mental clarity? Is anything on your mind?'}),
    Object.freeze({label:'Priorities and commitments',question:'What matters today: appointments, messages to reply to, health, hygiene, meals, chores or focused work?'})
  ]);
  function buildPrompt(answers) {
    if(!Array.isArray(answers)||answers.length!==questions.length)throw new Error('Expected three morning answers');
    const lines=answers.map((answer,i)=>{
      const clean=typeof answer==='string'?answer.trim().slice(0,900):'';
      return clean?questions[i].label+': '+clean:'';
    }).filter(Boolean);
    if(!lines.length)return '';
    return [
      'Help me make an actionable plan based only on what I report below.',
      ...lines,
      'Prioritize my explicitly reported commitments and tasks. Keep suggestions practical, specific and directly addressed to me.',
      'Do not invent a focus block, nap, meal, appointment, deadline, health fact, message or household task that I did not mention.',
      'Distinguish today from tomorrow when giving times. Calendar-unblocked intervals do not prove I am available.',
      'Do not claim an action was executed. Ask a short follow-up only if a critical detail is missing.'
    ].join('\n');
  }
  function mount(){
    if(typeof document==='undefined')return;
    const get=id=>document.getElementById(id);
    const panel=get('morning-companion');
    if(!panel)return;
    const open=get('morning-open'),answer=get('morning-answer'),question=get('morning-question');
    const progress=get('morning-progress'),next=get('morning-next'),cancel=get('morning-cancel');
    const read=get('morning-hear'),toggle=get('morning-voice-toggle');
    const speechStatus=get('morning-speech-status'),readPlan=get('read-plan');
    const speechSupported=typeof window!=='undefined'&&'speechSynthesis' in window&&'SpeechSynthesisUtterance' in window;
    let running=false,position=0,answers=['','',''],utterance=null,speechTimer=null,voiceEnabled=speechSupported;
    read.disabled=!speechSupported;
    toggle.disabled=!speechSupported;
    readPlan.hidden=!speechSupported;
    function syncVoice(){
      toggle.textContent=voiceEnabled?'Voice on':'Voice off';
      toggle.setAttribute('aria-pressed',String(voiceEnabled));
      read.textContent='Hear again';
      readPlan.textContent='Listen to plan';
    }
    function stopAudio(){
      clearTimeout(speechTimer);speechTimer=null;
      utterance=null;
      if(speechSupported)window.speechSynthesis.cancel();
      syncVoice();
    }
    function speak(text,button){
      if(!speechSupported){
        speechStatus.textContent='Spoken prompts are unavailable. Read the question and use keyboard dictation or type.';
        return;
      }
      stopAudio();
      const u=new window.SpeechSynthesisUtterance(text.slice(0,1600));
      utterance=u;u.lang='en-GB';u.rate=0.96;
      speechStatus.textContent='Starting spoken prompt… If you hear nothing, read the question below.';
      u.onstart=()=>{if(utterance!==u)return;clearTimeout(speechTimer);speechStatus.textContent='Speaking. Tap Voice off to stop playback.';};
      u.onend=()=>{if(utterance!==u)return;clearTimeout(speechTimer);utterance=null;syncVoice();speechStatus.textContent='';};
      u.onerror=()=>{if(utterance!==u)return;stopAudio();speechStatus.textContent='Audio could not play. Read the question or tap Hear again.';};
      speechTimer=setTimeout(()=>{if(utterance!==u)return;stopAudio();speechStatus.textContent='Audio did not start. Read the question or tap Hear again.';},5000);
      try{window.speechSynthesis.speak(u);}catch(_){u.onerror();}
    }
    function show(){
      question.textContent=questions[position].question;
      progress.textContent='Question '+(position+1)+' of '+questions.length+' · You may leave any answer blank';
      answer.value=answers[position];
      next.textContent=position===questions.length-1?'Review my check-in':'Next question / skip';
      get('morning-greeting').focus();
      panel.scrollIntoView({block:'start'});
    }
    const draft=active=>document.dispatchEvent(new CustomEvent('daily:draft',{detail:{active}}));
    function close(){
      stopAudio();running=false;panel.hidden=true;open.setAttribute('aria-expanded','false');
      answer.value='';answers=['','',''];position=0;speechStatus.textContent='';draft(false);
    }
    open.addEventListener('click',()=>{
      const prompt=get('prompt');
      if((running||prompt.value.trim())&&!window.confirm('Start a new guided morning check-in? Guided answers will be reset. Your unsent text stays until you review the new draft.'))return;
      stopAudio();running=true;answers=['','',''];position=0;panel.hidden=false;
      open.setAttribute('aria-expanded','true');get('checkin-form').hidden=true;draft(true);show();
      if(voiceEnabled)speak('Hello. Welcome to your check-in. Share only what you want to share. '+question.textContent,read);
      else speechStatus.textContent='Voice is off. Read the question and use the keyboard microphone or type.';
    });
    next.addEventListener('click',()=>{
      if(!running)return;
      stopAudio();speechStatus.textContent='';answers[position]=answer.value.slice(0,900);
      if(position<questions.length-1){
        position+=1;show();
        if(voiceEnabled)speak(question.textContent,read);
        return;
      }
      const text=buildPrompt(answers);
      if(!text){speechStatus.textContent='Add at least one answer before reviewing, or cancel to write a check-in.';return;}
      const prompt=get('prompt');
      if(prompt.value.trim()&&!window.confirm('Replace your unsent check-in with these morning answers?'))return;
      prompt.value=text;get('checkin-form').hidden=false;
      prompt.dispatchEvent(new Event('input',{bubbles:true}));
      close();prompt.focus();
      get('notice').textContent='Check-in drafted. Review and edit it before choosing Find my next steps.';
    });
    cancel.addEventListener('click',()=>{close();get('checkin-form').hidden=!get('prompt').value.trim();open.focus();});
    read.addEventListener('click',()=>speak(question.textContent,read));
    toggle.addEventListener('click',()=>{
      if(!speechSupported)return;
      voiceEnabled=!voiceEnabled;
      stopAudio();
      if(voiceEnabled&&running)speak(question.textContent,read);
      else speechStatus.textContent=voiceEnabled?'Voice is on.':'Voice is off. Use the keyboard microphone or type.';
    });
    readPlan.addEventListener('click',()=>{
      if(get('result').hidden)return;
      const items=Array.from(get('plan').querySelectorAll('.next-steps li span')).map(x=>x.textContent);
      if(!items.length)return;
      speak([get('result-context').textContent,get('result-title').textContent,...items].join('. '),readPlan);
    });
    document.addEventListener('daily:locked',close);
    document.addEventListener('daily:text-entry',close);
    document.addEventListener('daily:result-changed',stopAudio);
    document.addEventListener('visibilitychange',()=>{if(document.hidden){stopAudio();if(running)speechStatus.textContent='Voice stopped while this page was in the background.';}});
    window.addEventListener('pagehide',stopAudio);
    get('checkin-form').addEventListener('submit',stopAudio,{capture:true});
    syncVoice();
  }
  if(typeof document!=='undefined'){
    if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount,{once:true});
    else mount();
  }
  return {questions,buildPrompt};
})();
if(typeof module!=='undefined'&&module.exports)module.exports=MorningCompanion;

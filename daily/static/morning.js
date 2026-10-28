'use strict';
/* Guided, client-side check-in: no audio files, storage or automatic posts. */
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
      'Help me make a manageable plan for today based only on what I report.',
      ...lines,
      'Protect fixed commitments and deadlines first; include essential health, meals and hygiene if suitable, and one uninterrupted focus block where possible.',
      'Keep optional chores flexible. Do not invent appointments, email contents, clinical facts, or claim an action was executed.',
      'Ask a short follow-up if a critical detail is missing.'
    ].join('\n');
  }
  function mount(){
    if(typeof document==='undefined')return;
    const get=id=>document.getElementById(id);
    const panel=get('morning-companion');
    if(!panel)return;
    const open=get('morning-open'),answer=get('morning-answer'),question=get('morning-question');
    const progress=get('morning-progress'),next=get('morning-next'),cancel=get('morning-cancel');
    const read=get('morning-hear'),dictate=get('morning-dictate'),stop=get('morning-stop');
    const voiceStatus=get('morning-voice-status'),speechStatus=get('morning-speech-status'),readPlan=get('read-plan');
    const speechSupported=typeof window!=='undefined'&&'speechSynthesis' in window&&'SpeechSynthesisUtterance' in window;
    const Recognition=typeof window!=='undefined'&&(window.SpeechRecognition||window.webkitSpeechRecognition);
    const fallback='Tap the answer box, then the microphone on your device keyboard if available, or type your answer.';
    let running=false,position=0,answers=['','',''],recognizer=null,utterance=null,speechTimer=null;
    read.disabled=!speechSupported;
    readPlan.hidden=!speechSupported;
    // Keep an actionable, honest fallback visible even on iPhone browsers without recognition.
    dictate.textContent=Recognition?'Speak answer':'Use keyboard dictation';
    const status=message=>{voiceStatus.textContent=message;};
    const draft=active=>document.dispatchEvent(new CustomEvent('daily:draft',{detail:{active}}));
    function syncControls(){
      stop.disabled=!recognizer&&!utterance;
      dictate.disabled=Boolean(recognizer);
      read.textContent='Hear question';readPlan.textContent='Listen to plan';
    }
    function stopAudio(){
      clearTimeout(speechTimer);speechTimer=null;
      if(recognizer){const current=recognizer;recognizer=null;try{current.abort();}catch(_){}}
      utterance=null;
      if(speechSupported)window.speechSynthesis.cancel();
      syncControls();
    }
    function speak(text,button){
      if(!speechSupported){speechStatus.textContent='Spoken prompts are unavailable in this browser. Read the question below and dictate or type.';return;}
      if(utterance){stopAudio();speechStatus.textContent='Playback stopped.';return;}
      stopAudio();
      const u=new window.SpeechSynthesisUtterance(text.slice(0,1600));
      utterance=u;u.lang='en-GB';u.rate=0.96;syncControls();button.textContent='Stop speaking';
      speechStatus.textContent='Starting spoken prompt… If you cannot hear it, check volume or read the question.';
      u.onstart=()=>{if(utterance!==u)return;clearTimeout(speechTimer);speechStatus.textContent='Speaking. You can stop playback at any time.';};
      u.onend=()=>{if(utterance!==u)return;clearTimeout(speechTimer);utterance=null;syncControls();speechStatus.textContent='Playback finished. If you heard nothing, check device volume or read the question.';};
      u.onerror=()=>{if(utterance!==u)return;stopAudio();speechStatus.textContent='Audio could not play. Read the question, or tap Hear question to retry.';};
      // Some mobile browsers expose TTS but never start playback. Do not imply it was heard.
      speechTimer=setTimeout(()=>{if(utterance!==u)return;stopAudio();speechStatus.textContent='Audio did not start. Read the question, or tap Hear question to retry.';},5000);
      try{window.speechSynthesis.speak(u);}catch(_){u.onerror();}
    }
    function show(){
      question.textContent=questions[position].question;
      progress.textContent='Question '+(position+1)+' of '+questions.length+' · You may leave any answer blank';
      answer.value=answers[position];
      next.textContent=position===questions.length-1?'Review my check-in':'Next question / skip';
      // Avoid opening the software keyboard over the voice controls on the first tap.
      get('morning-greeting').focus();
      panel.scrollIntoView({block:'start'});
    }
    function close(){
      stopAudio();running=false;panel.hidden=true;open.setAttribute('aria-expanded','false');
      answer.value='';answers=['','',''];position=0;status('');speechStatus.textContent='';draft(false);
    }
    open.addEventListener('click',()=>{
      const prompt=get('prompt');
      if((running||prompt.value.trim())&&!window.confirm('Start a new guided morning check-in? Guided answers will be reset. Your unsent text stays until you review the new draft.'))return;
      stopAudio();running=true;answers=['','',''];position=0;panel.hidden=false;
      open.setAttribute('aria-expanded','true');get('checkin-form').hidden=true;draft(true);show();
      status(Recognition?'Tap Speak answer to start the microphone. Your browser may use an external speech service.':'Browser speech recognition is unavailable here. '+fallback);
      speak('Hello. Welcome to your morning check-in. Share only what you want to share. '+question.textContent,read);
    });
    next.addEventListener('click',()=>{
      if(!running)return;
      stopAudio();speechStatus.textContent='';answers[position]=answer.value.slice(0,900);
      if(position<questions.length-1){position+=1;show();status(Recognition?'Tap Speak answer, dictate or type.':fallback);return;}
      const text=buildPrompt(answers);
      if(!text){status('Add at least one answer before reviewing, or cancel to write a check-in.');return;}
      const prompt=get('prompt');
      if(prompt.value.trim()&&!window.confirm('Replace your unsent check-in with these morning answers?'))return;
      prompt.value=text;get('checkin-form').hidden=false;
      prompt.dispatchEvent(new Event('input',{bubbles:true}));
      close();prompt.focus();
      get('notice').textContent='Morning check-in drafted. Review and edit it before choosing Find my next steps.';
      // No automatic submission: the owner explicitly reviews the text.
    });
    cancel.addEventListener('click',()=>{close();get('checkin-form').hidden=!get('prompt').value.trim();open.focus();});
    stop.addEventListener('click',()=>{
      if(recognizer){
        // Stop capture but accept the final transcript. Cancel/navigation instead aborts it.
        status('Finishing speech input…');stop.disabled=true;
        try{recognizer.stop();}catch(_){stopAudio();status('Microphone off. '+fallback);}
        return;
      }
      stopAudio();speechStatus.textContent='Audio stopped.';status('Microphone off. '+fallback);
    });
    read.addEventListener('click',()=>speak(question.textContent,read));
    readPlan.addEventListener('click',()=>{
      if(get('result').hidden)return;
      const title=get('result-title').textContent;
      const items=Array.from(get('plan').querySelectorAll('.next-steps li span')).map(x=>x.textContent);
      if(!items.length)return;
      speak([get('result-context').textContent,title,...items].join('. '),readPlan);
    });
    dictate.addEventListener('click',()=>{
      if(!running)return;
      stopAudio();speechStatus.textContent='';
      if(!Recognition){status('Browser speech recognition is unavailable here. '+fallback);answer.focus();return;}
      let r;
      try{r=new Recognition();}catch(_){status('Speech input could not start. '+fallback);return;}
      recognizer=r;syncControls();
      r.lang='en-GB';r.continuous=false;r.interimResults=false;r.maxAlternatives=1;
      status('Requesting microphone access… Allow it in your browser to speak, or use keyboard dictation.');
      r.onstart=()=>{if(recognizer===r)status('Listening… Tap Stop when finished. Your browser may use an external speech service.');};
      r.onresult=event=>{
        if(recognizer!==r||!running)return;
        const words=Array.from(event.results).map(x=>x[0]?.transcript||'').join(' ').trim();
        if(words){answer.value=[answer.value.trim(),words].filter(Boolean).join(' ').slice(0,900);status('Answer added. Review or edit it before continuing.');}
        else status('No words were recognized. '+fallback);
      };
      r.onerror=event=>{if(recognizer!==r)return;stopAudio();status(event.error==='not-allowed'?'Microphone permission was denied. '+fallback:'Speech recognition was unavailable. '+fallback);};
      r.onend=()=>{if(recognizer!==r)return;recognizer=null;syncControls();if(/^(Listening|Requesting|Finishing)/.test(voiceStatus.textContent))status('Microphone off. Tap Speak answer to retry, or use device dictation or typing.');};
      try{r.start();}catch(_){if(recognizer===r){stopAudio();status('Speech input could not start. '+fallback);}}
    });
    document.addEventListener('daily:locked',close);
    document.addEventListener('daily:text-entry',close);
    document.addEventListener('daily:result-changed',stopAudio);
    document.addEventListener('visibilitychange',()=>{if(document.hidden){stopAudio();if(running)status('Microphone off while this page is in the background.');}});
    window.addEventListener('pagehide',stopAudio);
    get('checkin-form').addEventListener('submit',stopAudio,{capture:true});
    syncControls();
  }
  if(typeof document!=='undefined'){
    if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount,{once:true});
    else mount();
  }
  return {questions,buildPrompt};
})();
if(typeof module!=='undefined'&&module.exports)module.exports=MorningCompanion;

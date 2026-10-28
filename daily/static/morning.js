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
    const read=get('morning-hear'),dictate=get('morning-dictate');
    const voiceStatus=get('morning-voice-status'),readPlan=get('read-plan');
    const speechSupported=typeof window!=='undefined'&&'speechSynthesis' in window&&'SpeechSynthesisUtterance' in window;
    const Recognition=typeof window!=='undefined'&&(window.SpeechRecognition||window.webkitSpeechRecognition);
    let running=false,position=0,answers=['','',''],recognizer=null,spoken=false;
    read.hidden=!speechSupported;
    readPlan.hidden=!speechSupported;
    dictate.hidden=!Recognition;
    const status=message=>{voiceStatus.textContent=message;};
    function stopAudio(){
      if(recognizer){const current=recognizer;recognizer=null;try{current.abort();}catch(_){}}
      if(speechSupported)window.speechSynthesis.cancel();
      spoken=false;dictate.textContent='Speak answer';read.textContent='Hear question';
    }
    function speak(text,button){
      if(!speechSupported)return;
      if(spoken){window.speechSynthesis.cancel();spoken=false;button.textContent=button===read?'Hear question':'Listen to plan';return;}
      stopAudio();
      const utterance=new window.SpeechSynthesisUtterance(text.slice(0,1600));
      utterance.lang='en-GB';utterance.rate=0.96;
      spoken=true;button.textContent='Stop speaking';
      const reset=()=>{spoken=false;button.textContent=button===read?'Hear question':'Listen to plan';};
      utterance.onend=reset;utterance.onerror=reset;
      window.speechSynthesis.speak(utterance);
    }
    function show(){
      question.textContent=questions[position].question;
      progress.textContent='Question '+(position+1)+' of '+questions.length;
      answer.value=answers[position];
      next.textContent=position===questions.length-1?'Review my check-in':'Next question';
      answer.focus();
    }
    function close(){stopAudio();running=false;panel.hidden=true;answer.value='';answers=['','',''];position=0;status('');}
    open.addEventListener('click',()=>{
      const prompt=get('prompt');
      if(prompt.value.trim()&&!window.confirm('Start a guided morning check-in? Your current unsent text will remain until you choose to review the new draft.'))return;
      stopAudio();running=true;answers=['','',''];position=0;panel.hidden=false;show();
      status('You may type or use your device keyboard microphone. Browser speech recognition, if available, may use an external speech service.');
    });
    next.addEventListener('click',()=>{
      if(!running)return;
      stopAudio();answers[position]=answer.value.slice(0,900);
      if(position<questions.length-1){position+=1;show();return;}
      const draft=buildPrompt(answers);
      if(!draft){status('Add at least one answer before reviewing.');return;}
      const prompt=get('prompt');
      if(prompt.value.trim()&&!window.confirm('Replace your unsent check-in with these morning answers?'))return;
      prompt.value=draft;
      prompt.dispatchEvent(new Event('input',{bubbles:true}));
      close();prompt.focus();
      get('notice').textContent='Morning check-in drafted. Review and edit it before choosing Find my next steps.';
      // No automatic submission: the owner explicitly reviews the text.
    });
    cancel.addEventListener('click',close);
    read.addEventListener('click',()=>speak(question.textContent,read));
    readPlan.addEventListener('click',()=>{
      if(get('result').hidden)return;
      const title=get('result-title').textContent;
      const items=Array.from(get('plan').querySelectorAll('.next-steps li span')).map(x=>x.textContent);
      if(!items.length){status('No completed plan to read yet.');return;}
      speak([title,...items].join('. '),readPlan);
    });
    if(Recognition){
      dictate.addEventListener('click',()=>{
        if(recognizer){stopAudio();return;}
        stopAudio();
        const r=new Recognition();
        recognizer=r;
        r.lang='en-GB';r.continuous=false;r.interimResults=false;r.maxAlternatives=1;
        dictate.textContent='Stop microphone';
        status('Listening only after your click. Your browser may use an external service to transcribe audio.');
        r.onresult=event=>{
          const words=Array.from(event.results).map(x=>x[0]?.transcript||'').join(' ').trim();
          if(words)answer.value=[answer.value.trim(),words].filter(Boolean).join(' ').slice(0,900);
        };
        r.onerror=()=>{status('Speech recognition was unavailable. Use your keyboard microphone or type instead.');};
        r.onend=()=>{if(recognizer===r)recognizer=null;dictate.textContent='Speak answer';};
        try{r.start();}catch(_){recognizer=null;dictate.textContent='Speak answer';status('Speech recognition is not available in this browser. Use device dictation or type.');}
      });
    }else status('Browser speech recognition is unavailable. Use keyboard dictation or typing.');
    document.addEventListener('daily:locked',close);
    get('checkin-form').addEventListener('submit',stopAudio,{capture:true});
  }
  if(typeof document!=='undefined'){
    if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount,{once:true});
    else mount();
  }
  return {questions,buildPrompt};
})();
if(typeof module!=='undefined'&&module.exports)module.exports=MorningCompanion;

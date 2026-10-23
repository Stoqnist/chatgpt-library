'use strict';
const $ = id => document.getElementById(id);
const labels = {purchase:'Purchase & Resale', finance:'Finance', home:'Home & Possessions'};
let active = 0;
function node(tag, text, className) { const el=document.createElement(tag); el.textContent=text; if(className) el.className=className; return el; }
function select(index) {
  active=index; const item=window.DEMO_CASES[index];
  document.querySelectorAll('.scenario').forEach((b,i)=>b.setAttribute('aria-pressed', String(i===index)));
  $('case-title').textContent=item.title; $('case-detail').textContent=item.detail;
  $('count').textContent=item.evidence.length+' fictional records'; $('evidence').replaceChildren();
  item.evidence.forEach(e=>{
    const row=node('div','','evidence-row'), info=node('div','');
    const isReceipt=e.source_type==='receipt', transfer=e.data.kind==='own_account_transfer';
    const title=isReceipt?'Desk lamp receipt':transfer?'Transfer between own accounts':e.evidence_id==='bank-a-repeat'?'Overlapping bank export':'Card payment';
    info.append(node('strong',title),node('small',isReceipt?'Receipt R-123 · purchase complete':'Transaction '+e.data.transaction_id));
    row.append(node('span',isReceipt?'R':'B','icon'),info,node('span','€'+e.data.amount_eur,'amount')); $('evidence').append(row);
  });
  $('result').hidden=true; $('review').hidden=false;
}
window.DEMO_CASES.forEach((item,index)=>{
  const b=node('button','','scenario'); b.type='button'; b.append(node('small','CASE 0'+(index+1)),node('strong',item.title));
  b.addEventListener('click',()=>select(index)); $('scenarios').append(b);
});
$('review').addEventListener('click',()=>{
  const item=window.DEMO_CASES[active], r=item.result;
  const summary=item.key==='conflict'?'Conflicting evidence. Spending stays unresolved.':item.key==='missing'?'€49.90 in card spending. The purchase is still unconfirmed.':'€49.90 in card spending. Counted once.';
  $('summary').replaceChildren(node('div',summary),node('small','Delivery remains unverified. No records changed.'));
  $('owners').replaceChildren();
  Object.entries(r.specialist_results).forEach(([key,result])=>{
    const card=node('article','','owner'), heading=node('div','','owner-head');
    heading.append(node('strong',labels[key]),node('span',result.status==='completed'?'Analysis available':result.status,'status')); card.append(heading);
    result.findings.forEach(f=>card.append(node('p',f.claim)));
    if(!result.findings.length) card.append(node('p',result.unresolved_questions.join(' ')));
    $('owners').append(card);
  });
  $('questions').replaceChildren(...r.unresolved_questions.map(q=>node('li',q)));
  $('raw').textContent=JSON.stringify({evidence:item.evidence, result:r},null,2);
  $('review').hidden=true; $('result').hidden=false; $('result-heading').focus({preventScroll:true}); $('result').scrollIntoView({behavior:'auto',block:'start'});
});
$('reset').addEventListener('click',()=>{select((active+1)%window.DEMO_CASES.length);document.querySelectorAll('.scenario')[active].focus();});
select(0);

// Recovery is a fictional UI story, not clinical logic or the V2 coordinator.
let soundOn = false;
let audioContext;
function tick() {
  if (!soundOn || !audioContext) return;
  const oscillator = audioContext.createOscillator();
  const gain = audioContext.createGain();
  oscillator.type = 'sine'; oscillator.frequency.value = 520;
  gain.gain.setValueAtTime(0, audioContext.currentTime);
  gain.gain.linearRampToValueAtTime(0.035, audioContext.currentTime + 0.01);
  gain.gain.exponentialRampToValueAtTime(0.0001, audioContext.currentTime + 0.13);
  oscillator.connect(gain); gain.connect(audioContext.destination);
  oscillator.start(); oscillator.stop(audioContext.currentTime + 0.14);
  oscillator.onended = () => { oscillator.disconnect(); gain.disconnect(); };
}
$('sound').addEventListener('click', async () => {
  try {
    if (!soundOn) {
      const Audio = window.AudioContext || window.webkitAudioContext;
      if (!Audio) throw new Error('Audio unavailable');
      audioContext ||= new Audio();
      await audioContext.resume();
    }
    soundOn = !soundOn;
    if (!soundOn && audioContext) await audioContext.suspend();
    $('sound').setAttribute('aria-pressed', String(soundOn));
    $('sound').textContent = soundOn ? 'Sound on' : 'Sound off';
    tick();
  } catch (_) {
    soundOn = false; $('sound').textContent = 'Sound unavailable';
    $('sound').setAttribute('aria-pressed', 'false');
  }
});
function moodReset(message = 'One tap is enough. You can skip this.') {
  document.querySelectorAll('[data-mood]').forEach(b => b.setAttribute('aria-pressed','false'));
  $('mood-status').textContent = message; $('undo-mood').hidden = true;
}
document.querySelectorAll('[data-mood]').forEach(button => button.addEventListener('click', () => {
  document.querySelectorAll('[data-mood]').forEach(b => b.setAttribute('aria-pressed',String(b === button)));
  $('mood-status').textContent = 'Demo mood: ' + button.dataset.mood + '. That’s the check-in. No health assessment made.';
  $('undo-mood').hidden = false; tick();
}));
$('skip-mood').addEventListener('click', () => moodReset('Skipped. Nothing to catch up on.'));
$('undo-mood').addEventListener('click', () => moodReset());
function energySelect(value) {
  document.querySelectorAll('[data-energy]').forEach(b => b.setAttribute('aria-pressed',String(b.dataset.energy === value)));
  const low = value === 'low';
  $('optional-tasks').open = !low;
  $('optional-label').textContent = low ? 'Can wait · 2 optional tasks' : 'Optional tasks · 2';
  $('plan-title').textContent = low ? 'Keep today small.' : 'A few things to hold.';
  $('plan-status').textContent = low ? 'Optional chores can wait. Your care instructions stay unchanged.' : value ? 'One practical step at a time. The care plan stays unchanged.' : 'Try a lower-energy day to see what can wait.';
  $('next-task').classList.remove('settle');
  void $('next-task').offsetWidth;
  if (value) $('next-task').classList.add('settle');
}
document.querySelectorAll('[data-energy]').forEach(b => b.addEventListener('click', () => { energySelect(b.dataset.energy); tick(); }));
$('prepare-help').addEventListener('click', () => {
  $('help-draft').hidden = !$('help-draft').hidden;
  $('prepare-help').setAttribute('aria-expanded', String(!$('help-draft').hidden));
  $('prepare-help').textContent = $('help-draft').hidden ? 'Preview a help request →' : 'Close draft ↑'; tick();
});
$('prepare-help').setAttribute('aria-expanded','false');
$('prepare-help').setAttribute('aria-controls','help-draft');
$('recovery-reset').addEventListener('click', () => {
  moodReset(); energySelect(null); $('help-draft').hidden = true;
  $('prepare-help').textContent = 'Preview a help request →';
  $('prepare-help').setAttribute('aria-expanded','false');
});
function openAnchor() {
  const target = document.getElementById(location.hash.slice(1));
  if (target?.tagName === 'DETAILS') target.open = true;
  if (target?.closest('.purchase-more')) target.closest('.purchase-more').open = true;
}
window.addEventListener('hashchange', openAnchor); openAnchor();

'use strict';
const $ = id => document.getElementById(id);
const {t, source, money} = window.StoqI18n;
if ($('scenarios')) {
let active = 0;
function node(tag, text, className) { const el=document.createElement(tag); el.textContent=text; if(className) el.className=className; return el; }
function select(index) {
  active=index; const item=window.DEMO_CASES[index];
  document.querySelectorAll('.scenario').forEach((b,i)=>b.setAttribute('aria-pressed', String(i===index)));
  $('case-title').textContent=t(`case.${item.key}.title`); $('case-detail').textContent=t(`case.${item.key}.detail`);
  $('count').textContent=t('case.count', {count:item.evidence.length}); $('evidence').replaceChildren();
  item.evidence.forEach(e=>{
    const row=node('div','','evidence-row'), info=node('div','');
    const isReceipt=e.source_type==='receipt', transfer=e.data.kind==='own_account_transfer';
    const title=t(isReceipt?'evidence.receipt':transfer?'evidence.transfer':e.evidence_id==='bank-a-repeat'?'evidence.overlap':'evidence.card');
    info.append(node('strong',title),node('small',isReceipt?t('evidence.receiptDetail'):t('evidence.transaction',{id:e.data.transaction_id})));
    row.append(node('span',isReceipt?'▤':'↔','icon'),info,node('span',money(e.data.amount_eur),'amount')); $('evidence').append(row);
  });
  $('result').hidden=true; $('review').disabled=false; $('review').setAttribute('aria-expanded','false');
}
window.DEMO_CASES.forEach((item,index)=>{
  const b=node('button','','scenario'); b.type='button'; b.append(node('small',t('case.number',{number:String(index+1).padStart(2,'0')})),node('strong',t(`case.${item.key}.title`)));
  b.addEventListener('click',()=>select(index)); $('scenarios').append(b);
});
$('review').addEventListener('click',()=>{
  const item=window.DEMO_CASES[active], r=item.result;
  const summary=t(`summary.${item.key}`,{amount:money('49.90')});
  $('summary').replaceChildren(node('div',summary),node('small',t('summary.note')));
  $('owners').replaceChildren();
  Object.entries(r.specialist_results).forEach(([key,result])=>{
    const card=node('article','','owner'), heading=node('div','','owner-head');
    heading.append(node('strong',t('owner.'+key)),node('span',t('status.'+result.status),'status')); card.append(heading);
    result.findings.forEach(f=>card.append(node('p',source(f.claim))));
    if(!result.findings.length) card.append(node('p',result.unresolved_questions.map(source).join(' ')));
    $('owners').append(card);
  });
  $('questions').replaceChildren(...r.unresolved_questions.map(q=>node('li',source(q))));
  $('raw').textContent=JSON.stringify({evidence:item.evidence, result:r},null,2);
  $('review').disabled=true; $('review').setAttribute('aria-expanded','true'); $('result').hidden=false; $('result-heading').focus({preventScroll:true});
});
$('reset').addEventListener('click',()=>{select((active+1)%window.DEMO_CASES.length);document.querySelectorAll('.scenario')[active].focus();});
select(0);
}

if ($('recovery')) {
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
    $('sound').textContent = t(soundOn ? 'sound.on' : 'sound.off');
    tick();
  } catch (_) {
    soundOn = false; $('sound').textContent = t('sound.unavailable');
    $('sound').setAttribute('aria-pressed', 'false');
  }
});
function moodReset(message = t('mood.initial')) {
  document.querySelectorAll('[data-mood]').forEach(b => b.setAttribute('aria-pressed','false'));
  $('mood-status').textContent = message; $('undo-mood').hidden = true;
}
document.querySelectorAll('[data-mood]').forEach(button => button.addEventListener('click', () => {
  document.querySelectorAll('[data-mood]').forEach(b => b.setAttribute('aria-pressed',String(b === button)));
  $('mood-status').textContent = t('mood.selected',{mood:t('mood.'+button.dataset.mood)});
  $('undo-mood').hidden = false; tick();
}));
$('skip-mood').addEventListener('click', () => moodReset(t('mood.skipped')));
$('undo-mood').addEventListener('click', () => moodReset());
function energySelect(value) {
  document.querySelectorAll('[data-energy]').forEach(b => b.setAttribute('aria-pressed',String(b.dataset.energy === value)));
  const low = value === 'low';
  $('energy-feedback').textContent = t(low ? 'energy.feedbackLow' : value ? 'energy.feedbackOther' : 'energy.initial');
  $('optional-tasks').open = !low;
  $('optional-label').textContent = t(low ? 'plan.wait' : 'plan.optional');
  $('plan-title').textContent = t(low ? 'plan.small' : 'plan.title');
  $('plan-status').textContent = t(low ? 'plan.low' : value ? 'plan.other' : 'plan.initial');
  $('next-task').classList.remove('settle');
  void $('next-task').offsetWidth;
  if (value) $('next-task').classList.add('settle');
}
document.querySelectorAll('[data-energy]').forEach(b => b.addEventListener('click', () => { energySelect(b.dataset.energy); tick(); }));
$('prepare-help').addEventListener('click', () => {
  $('help-draft').hidden = !$('help-draft').hidden;
  $('prepare-help').setAttribute('aria-expanded', String(!$('help-draft').hidden));
  $('prepare-help').textContent = t($('help-draft').hidden ? 'help.open' : 'help.close'); tick();
});
$('prepare-help').setAttribute('aria-expanded','false');
$('prepare-help').setAttribute('aria-controls','help-draft');
$('recovery-reset').addEventListener('click', () => {
  moodReset(); energySelect(null); $('help-draft').hidden = true;
  $('prepare-help').textContent = t('help.open');
  $('prepare-help').setAttribute('aria-expanded','false');
});
function openAnchor() {
  const target = document.getElementById(location.hash.slice(1));
  if (target?.tagName === 'DETAILS') target.open = true;
  if (target?.closest('.purchase-more')) target.closest('.purchase-more').open = true;
}
window.addEventListener('hashchange', openAnchor); openAnchor();


// Reveal the film invitation only when its action can start playback.
// Native controls remain available without JavaScript and after playback begins.
const filmVideo = $('story-video'), filmPlay = $('film-play');
if (filmVideo && filmPlay) {
  const runtime = $('film-runtime');
  filmVideo.setAttribute('tabindex', '-1');
  filmPlay.hidden = false;
  const revealPlayer = () => {
    filmPlay.hidden = true;
    filmVideo.removeAttribute('tabindex');
    if (runtime) runtime.hidden = true;
  };
  filmPlay.addEventListener('click', () => {
    revealPlayer();
    const playback = filmVideo.play();
    if (playback && typeof playback.catch === 'function') playback.catch(() => filmVideo.focus());
  });
  filmVideo.addEventListener('play', revealPlayer);
  filmVideo.addEventListener('error', () => {
    revealPlayer();
    $('video-status').textContent = t('video.unavailable');
  });
}

}

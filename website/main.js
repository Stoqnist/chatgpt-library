'use strict';
document.documentElement.classList.add('js');
const hero=document.querySelector('.hero');
const heroImage=hero?.querySelector('img');
if(heroImage){
  const onImage=()=>hero.classList.toggle('has-art',heroImage.naturalWidth>0);
  heroImage.addEventListener('load',onImage);
  heroImage.addEventListener('error',onImage);
  if(heroImage.complete)onImage();
}
const examples={
  plan:{question:'“I’ve got too much to sort out this week. Where do I start?”',title:'Start with what matters most.',description:'Break a busy week into priorities, decisions and manageable next actions.',steps:['Find priorities','Choose a first step','Review the plan']},
  choose:{question:'“There are several options. How do I make a sensible choice?”',title:'See the trade-offs plainly.',description:'Put the practical differences, missing information and risks side by side.',steps:['Clarify the goal','Compare options','Decide with confidence']},
  organise:{question:'“I keep losing track of the small things. Can I simplify them?”',title:'Make more room for everyday life.',description:'Create a clear view of what needs attention, without making another complicated system.',steps:['Collect what matters','Organise it simply','Keep it useful']}
};
const tabs=[...document.querySelectorAll('.journey-tab')];
const panel=document.getElementById('journey-panel');
function selectJourney(key,focus=false){
 const item=examples[key];if(!item||!panel)return;
 for(const tab of tabs){const selected=tab.dataset.journey===key;tab.setAttribute('aria-selected',String(selected));tab.tabIndex=selected?0:-1;if(selected){panel.setAttribute('aria-labelledby',tab.id);if(focus)tab.focus();}}
 document.getElementById('journey-question').textContent=item.question;
 document.getElementById('journey-title').textContent=item.title;
 document.getElementById('journey-description').textContent=item.description;
 document.getElementById('journey-steps').replaceChildren(...item.steps.map(s=>{const el=document.createElement('span');el.textContent=s;return el;}));
}
tabs.forEach((tab,index)=>{
 tab.addEventListener('click',()=>selectJourney(tab.dataset.journey));
 tab.addEventListener('keydown',event=>{
  if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
  event.preventDefault();
  const i=event.key==='Home'?0:event.key==='End'?tabs.length-1:(index+(event.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;
  selectJourney(tabs[i].dataset.journey,true);
 });
});
const reveals=[...document.querySelectorAll('.scroll-reveal')];
if('IntersectionObserver' in window&&!window.matchMedia('(prefers-reduced-motion: reduce)').matches){
 const ob=new IntersectionObserver((entries,observer)=>{for(const e of entries){if(e.isIntersecting){e.target.classList.add('is-visible');observer.unobserve(e.target);}}},{threshold:.08,rootMargin:'0px 0px -35px 0px'});
 reveals.forEach(el=>ob.observe(el));
}else reveals.forEach(el=>el.classList.add('is-visible'));

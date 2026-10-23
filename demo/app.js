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

import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const root=new URL('../',import.meta.url);
const registry=JSON.parse(fs.readFileSync(new URL('locales/registry.json',root),'utf8'));
for(const {code:locale} of registry.locales.filter(entry=>entry.enabled)){
  // Run the real app with a small DOM to check every interaction and fixture branch.
  class Element{
    constructor(){this.textContent='';this.children=[];this.dataset={};this.attrs={};this.listeners={};this.hidden=false;this.classList={remove(){},add(){}};}
    setAttribute(k,v){this.attrs[k]=v;} append(...items){this.children.push(...items);}
    replaceChildren(...items){this.children=items;} addEventListener(k,f){this.listeners[k]=f;}
    focus(){} closest(){return null;} click(){return this.listeners.click?.();}
  }
  const ids=new Map();const byId=id=>{if(!ids.has(id))ids.set(id,new Element());return ids.get(id);};
  const moods=['veryLow','low','neutral','good','veryGood'].map(value=>Object.assign(new Element(),{dataset:{mood:value}}));
  const energies=['low','some','plenty'].map(value=>Object.assign(new Element(),{dataset:{energy:value}}));
  const document={getElementById:byId,createElement:()=>new Element(),querySelectorAll:selector=>selector==='[data-mood]'?moods:selector==='[data-energy]'?energies:selector==='.scenario'?byId('scenarios').children:[]};
  const context=vm.createContext({document,window:{addEventListener(){}},location:{hash:''},Intl,URL});
  for(const file of [`locales/${locale}.js`,'i18n.js','cases.js','app.js'])vm.runInContext(fs.readFileSync(new URL(file,root),'utf8'),context);
  const {t,source,money}=context.window.StoqI18n;
  assert.equal(context.window.StoqI18n.locale,locale);
  assert.throws(()=>t('missing.translation'),/Missing translation/);
  assert.throws(()=>t('mood.selected'),/Missing translation value/);
  assert.throws(()=>source('Changed coordinator text'),/Uncatalogued/);
  for(const b of moods){b.click();assert.equal(byId('mood-status').textContent,t('mood.selected',{mood:t('mood.'+b.dataset.mood)}));}
  byId('skip-mood').click();assert.equal(byId('mood-status').textContent,t('mood.skipped'));
  byId('undo-mood').click();assert.equal(byId('mood-status').textContent,t('mood.initial'));
  for(const b of energies){b.click();assert.equal(byId('optional-tasks').open,b.dataset.energy!=='low');}
  energies[0].click();assert.equal(byId('energy-feedback').textContent,t('energy.feedbackLow'));
  byId('help-draft').hidden=true;byId('prepare-help').click();assert.equal(byId('prepare-help').textContent,t('help.close'));
  byId('recovery-reset').click();assert.equal(byId('help-draft').hidden,true);assert.equal(byId('plan-title').textContent,t('plan.title'));
  await byId('sound').click();assert.equal(byId('sound').textContent,t('sound.unavailable'));
  for(const [i,c] of context.window.DEMO_CASES.entries()){
    byId('scenarios').children[i].click();assert.equal(byId('case-title').textContent,t(`case.${c.key}.title`));
    byId('review').click();assert.equal(byId('result').hidden,false);assert.equal(byId('review').attrs['aria-expanded'],'true');
    assert.equal(byId('summary').children[0].textContent,t(`summary.${c.key}`,{amount:money('49.90')}));
    assert.ok(byId('owners').children.length===3);
    assert.equal(byId('questions').children.length,c.result.unresolved_questions.length);
    assert.deepEqual(JSON.parse(byId('raw').textContent).result.executed_writes,[]);
  }
  byId('reset').click();assert.equal(byId('result').hidden,true);
  console.log(`PASS: ${locale} recovery controls, audio failure, three evidence scenarios, results and currency`);
}

// Synthetic browser acceptance only; no account, model, or private data.
import {chromium} from 'playwright';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const browser=await chromium.launch({executablePath:process.env.CHROME_PATH||undefined,headless:true});
try {
 for(const width of [390,1024]){
  const page=await browser.newPage({viewport:{width,height:844}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const turns=[];const runs=[];const sent=[];
  await page.route('https://daily.example/**',async route=>{
   const url=new URL(route.request().url()),path=url.pathname;
   if(!path.includes('/api/')){
    const name=path==='/daily/'?'index.html':path.split('/').pop();
    const contentType=name.endsWith('.js')?'text/javascript':name.endsWith('.css')?'text/css':'text/html';
    return route.fulfill({body:await fs.readFile(new URL('../static/'+name,import.meta.url)),contentType});
   }
   let data={};
   if(path.endsWith('/run')){
    const body=route.request().postDataJSON();sent.push({path,...body});
    const result={message:'Your next steps',source:'Your check-in only.',next_steps:[{text:'Read one page of your book.',owner:'Planning'}],agents:[]};
    const run={id:'run-1',created:Date.now()/1000,prompt:body.prompt,status:'completed',result};
    runs.push(run);turns.push({...run,kind:'checkin',answer:'Read one page of your book.',omitted:0});data={id:run.id};
   }else if(path.endsWith('/chat/send')){
    const body=route.request().postDataJSON();sent.push({path,...body});
    turns.push({id:'reply-1',created:Date.now()/1000,prompt:body.prompt,kind:'conversation',answer:'Open the book at your bookmark.',status:'completed',omitted:0});data={id:'reply-1'};
   }else if(path.endsWith('/chat/state')){
    data={turns,total:turns.length,notes:{draft:{text:'',revision:0}},connected:true,remaining:18,next_omitted:0};
   }else if(path.endsWith('/state'))data={csrf:'synthetic',connected:true,remaining:20,runs};
   return route.fulfill({json:data});
  });
  await page.goto('https://daily.example/daily/');
  await page.locator('#morning-open').click();
  await page.locator('#morning-answer').fill('I slept well.');
  await page.locator('#morning-next').click();
  await page.locator('#morning-answer').fill('I have some energy.');
  await page.locator('#morning-next').click();
  await page.locator('#morning-answer').fill('I want to read my book.');
  assert.match(await page.locator('#morning-review').inputValue(),/I want to read my book/);
  await page.locator('#morning-next').click();
  await page.getByRole('button',{name:'Choose my next step'}).waitFor();
  assert.equal(sent.length,1);
  assert.equal(await page.locator('#result').isVisible(),false);
  await page.locator('#chat-input').fill('Keep this unsent draft.');
  await page.getByRole('button',{name:'Choose my next step'}).click();
  await page.getByText('Open the book at your bookmark.',{exact:true}).waitFor();
  assert.equal(sent.length,2);assert.equal(sent[1].reply_to,'run-1');
  assert.equal(await page.locator('#chat-input').inputValue(),'Keep this unsent draft.');
  assert.equal(await page.getByText('Export conversation',{exact:true}).isVisible(),false);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  assert.deepEqual(errors,[]);
  await page.close();
 }
 console.log('PASS: mobile/desktop one-tap check-in, findings, direct follow-up, preserved draft and layout');
}finally{await browser.close();}

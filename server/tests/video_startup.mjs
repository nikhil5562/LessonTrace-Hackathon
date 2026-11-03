import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';

const [root,jsdomPath]=process.argv.slice(2);
const {JSDOM,VirtualConsole}=await import(pathToFileURL(jsdomPath).href);
let input='';for await(const chunk of process.stdin)input+=chunk;
const fixture=JSON.parse(input),scenario=fixture.scenario,issues=[];
const virtualConsole=new VirtualConsole();virtualConsole.on('jsdomError',error=>issues.push(error.message));
const dom=new JSDOM(await fs.readFile(path.join(root,'app/index.html'),'utf8'),{
  url:'http://127.0.0.1:8897/'+(['workspace_failure','quoted_quiz'].includes(scenario)?'#video':'#learn'),
  runScripts:'outside-only',pretendToBeVisual:true,virtualConsole,
});
const w=dom.window;
w.HTMLElement.prototype.scrollIntoView=function(){};
w.Range.prototype.getClientRects=()=>[];
w.Range.prototype.getBoundingClientRect=()=>({left:0,top:0,right:0,bottom:0,width:0,height:0});
w.matchMedia=()=>({matches:false,addListener(){},removeListener(){},addEventListener(){},removeEventListener(){}});
w.ResizeObserver=class{observe(){} unobserve(){} disconnect(){}};
w.addEventListener('error',event=>issues.push(event.error?.stack||event.message));
let online=scenario!=='offline_reconnect',created=false,posts=0;
const reply=(value,status=200)=>({ok:status===200,status,json:async()=>JSON.parse(JSON.stringify(value))});
w.fetch=async(url,options={})=>{
  const target=new URL(url,w.location.href);
  assert.equal(target.origin,'http://127.0.0.1:8897','Unexpected external URL in an offline UI test');
  if(target.pathname==='/api/session'&&!online)return reply({detail:'Synthetic connection unavailable'},503);
  if(options.method==='POST'){
    assert.equal(target.pathname,'/api/video-session/learning');
    const body=JSON.parse(options.body);assert.equal(body.consent,true);assert.ok(body.url.startsWith('https://'));
    posts++;
    await new Promise(resolve=>setTimeout(resolve,30));
    if(scenario==='creation_failure'&&posts===1)return reply({detail:'Synthetic generation unavailable; old work kept'},503);
    created=true;return reply(fixture.created);
  }
  if(target.pathname==='/api/video-session'){
    if(!created&&scenario==='edited_url')await new Promise(resolve=>setTimeout(resolve,180));
    if(!created&&scenario==='saved_lesson_failure')return reply({detail:'Synthetic saved-lesson unavailable'},503);
    return reply({session:created?fixture.created.session:fixture.initial_session});
  }
  if(target.pathname==='/api/video-learning'){
    if(!created&&scenario==='workspace_failure')return reply({detail:'Synthetic saved-workspace unavailable'},503);
    return reply({learning:created?fixture.created.learning:fixture.initial_learning,allowance:fixture.created.allowance});
  }
  assert.ok(target.pathname in fixture.responses,'Unmocked request '+target.pathname);
  return reply(fixture.responses[target.pathname]);
};
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(predicate,label){const limit=Date.now()+5500;while(!predicate()){assert.ok(Date.now()<limit,'Timed out: '+label);await delay(10);}}

try{
  for(const tag of w.document.querySelectorAll('script[src]')){
    const name=path.basename(new URL(tag.src).pathname);
    if(scenario==='studio_missing'&&name==='video-studio.js')continue;
    w.eval(await fs.readFile(path.join(root,'app/assets',name),'utf8')+'\n//# sourceURL='+name);
  }
  const button=w.document.getElementById('session-create'),consent=w.document.getElementById('session-consent');
  await until(()=>!button.disabled,'creation becomes available independently of the saved preview');
  assert.equal(button.closest('[inert]'),null);
  if(scenario==='quoted_quiz'){
    await until(()=>w.document.querySelector('.vs-quiz-code code'),'quoted premise is displayed');
    assert.equal(w.document.querySelector('.vs-quiz-code code').textContent,'friends = ["Paul", \'Dana\', "Nathan"]');
  }
  if(scenario==='edited_url'){
    const input=w.document.getElementById('session-url'),chosen='https://youtu.be/fz_BCnhEQYQ?section=student-choice';
    input.value=chosen;input.dispatchEvent(new w.Event('input'));await delay(220);
    assert.equal(input.value,chosen,'Loading saved work must not replace the learner’s new URL');
  }
  if(scenario==='offline_reconnect'){
    assert.match(button.textContent,/Reconnect/);online=true;
  }
  // Consent is still necessary, even when reconnecting or recovering a preview.
  button.click();await delay(80);assert.equal(posts,0);
  assert.match(w.document.getElementById('session-create-status').textContent,/Allow Meta/);
  consent.checked=true;consent.dispatchEvent(new w.Event('change'));
  button.click();button.click();
  await until(()=>posts===1&&!button.disabled,'creation finishes and unlocks the control');
  if(scenario==='creation_failure'){
    assert.match(w.document.getElementById('session-create-status').textContent,/Synthetic generation unavailable/);
    assert.ok(w.document.querySelector('#session-saved a'),'The old saved lesson remains available');
    assert.equal(created,false);button.click();await until(()=>posts===2&&!button.disabled,'retry succeeds');
  }
  assert.equal(created,true);assert.equal(posts,scenario==='creation_failure'?2:1);
  assert.ok(w.document.querySelector('#session-saved a'),'The created lesson remains reopenable');
  assert.match(w.document.getElementById('session-create-status').textContent,/ready|created and saved/);
  if(scenario==='studio_missing')assert.equal(w.location.hash,'#learn','A preview error must not hide the saved lesson behind a blank workspace');
  assert.deepEqual(issues,[]);
  console.log(JSON.stringify({scenario,creation:'clickable',consent:'required',duplicate_click:'blocked',model_calls:0}));
}finally{w.close();}

import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [root,jsdomPath]=process.argv.slice(2),{JSDOM,VirtualConsole}=await import(pathToFileURL(jsdomPath).href);
let input='';for await(const part of process.stdin)input+=part;const f=JSON.parse(input),issues=[],posts=[];
const console=new VirtualConsole();console.on('jsdomError',error=>issues.push(error.message));
const dom=new JSDOM(await fs.readFile(path.join(root,'app/index.html'),'utf8'),{url:'http://127.0.0.1:8897/#video',runScripts:'outside-only',pretendToBeVisual:true,virtualConsole:console}),w=dom.window;
w.HTMLElement.prototype.scrollIntoView=function(){};w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};w.HTMLDialogElement.prototype.close=function(){this.open=false;};
w.matchMedia=()=>({matches:false,addListener(){},removeListener(){},addEventListener(){},removeEventListener(){}});w.ResizeObserver=class{observe(){} disconnect(){}};
w.addEventListener('error',event=>issues.push(event.error?.stack||event.message));
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms)),reply=(data,status=200)=>({ok:status===200,status,json:async()=>structuredClone(data)});
const old=structuredClone(f.video);old.session.lesson_id=old.learning.lesson_id='2'.repeat(32);old.session.title='Earlier dictionary lesson';
let active=f.video,preferences=f.preferences,grant={},researchPosts=0,revisionConflict=f.scenario==='conflict',networkFailed=f.scenario==='network';
const quoteText='A <img src=x onerror=alert(1)> stays literal source wording.';
if(f.scenario==='evidence')f.video.learning.messages.push({role:'assistant',text:'Earlier saved reply, without a separate support review.',sources:[]},{role:'assistant',text:'Review the source wording.',claim_review:{status:'supported'},sources:[f.video.session.source_segments[0].id],evidence_quotes:[{source_id:f.video.session.source_segments[0].id,claim:'A controlled display-only source claim.',quote:quoteText,quote_verified:true}]});
const allowance={remaining_requests:({unavailable:3,exhausted:0,'last-reservation':1}[f.scenario]??30)},summary=item=>({lesson_id:item.session.lesson_id,context:item.session.context||'video',title:item.session.title,unit_id:item.learning.unit.id,unit_title:item.learning.unit.title,stage:'practice',quiet:f.scenario==='fresh'});
function dashboard(){const current=summary(active),card=f.scenario==='fresh'?{kind:'quiet',title:'Your fresh check is yours to try',text:'Ask Meta explicitly for supported help.',action:null,basis:'saved_progress'}:grant.job?.status==='ready'?{kind:'research_ready',title:'A focused follow-up is ready',text:'Your current work stays saved.',action:'open_research',lesson_id:f.hub.session.lesson_id,basis:'meta_research'}:null;
  return {preferences,lessons:[summary(f.video),summary(old),summary(f.hub)],current,next_step:card,research:grant,research_supported:true,updates:[],allowance,meta_enabled:true,usage:{recorded_calls:2,reserved_cents:20,calls_with_usage:1,reported_total_tokens:123}};}
w.fetch=async(url,options={})=>{const u=new URL(url,w.location.href);assert.equal(u.origin,'http://127.0.0.1:8897');
  if(options.method==='POST'){const body=JSON.parse(options.body);posts.push({path:u.pathname,body});assert.equal(options.headers['X-LessonTrace-CSRF'],f.responses['/api/session'].csrf);
    if(u.pathname==='/api/coach/preferences'){await delay(30);if(networkFailed)return reply({detail:'Synthetic workspace connection unavailable.'},503);if(revisionConflict){preferences={...preferences,revision:2,goal:'Saved in another tab'};return reply({detail:'Preferences changed in another tab. Reload them before saving.'},409);}preferences={...body,revision:body.revision+1};return reply({preferences});}
    if(u.pathname==='/api/coach/preferences/reset'){preferences={...f.preferences,revision:preferences.revision+1};return reply({preferences});}
    if(u.pathname==='/api/coach/resume'){active=[f.video,old,f.hub].find(item=>item.session.lesson_id===body.lesson_id);assert.ok(active);return reply({session:active.session});}
    if(u.pathname==='/api/coach/research'){researchPosts++;await delay(30);grant={used:true,unit_title:active.learning.unit.title,lesson_id:f.hub.session.lesson_id,job:{id:'research-fixture',status:'ready',message:'Checked synthetic follow-up ready.'}};return reply(dashboard());}
    assert.fail('Unexpected mutation '+u.pathname);
  }
  if(u.pathname==='/api/coach'){if(networkFailed&&posts.length)throw new Error('Synthetic connection lost.');return reply(dashboard());}
  if(u.pathname==='/api/video-session')return reply({session:active.session.context==='hub'?f.video.session:active.session});
  if(u.pathname==='/api/hub')return reply({session:f.hub.session,job:null,catalog:[],allowance});
  if(u.pathname==='/api/video-learning')return reply({learning:u.searchParams.get('context')==='hub'?f.hub.learning:active.learning,allowance});
  assert.ok(u.pathname in f.responses,'Unmocked '+u.pathname);return reply(f.responses[u.pathname]);
};
const $=id=>w.document.getElementById(id),editor=()=>w.document.querySelector('#vs-editor textarea');
async function until(check,label){const end=Date.now()+8000;while(!check()){assert.ok(Date.now()<end,'Timed out: '+label);await delay(10);}}
function inputValue(id,value){$(id).value=value;$(id).dispatchEvent(new w.Event('input',{bubbles:true}));}
try{
  for(const script of w.document.querySelectorAll('script[src]')){const name=path.basename(new URL(script.src).pathname);if(name==='lesson-editor.bundle.js')continue;w.eval(await fs.readFile(path.join(root,'app/assets',name),'utf8')+'\n//# sourceURL='+name);}
  await until(()=>editor()&&!$('lc-home').hidden,'Coach and editor ready');$('vs-meta-tab').click();
  if(f.scenario==='evidence'){
    const detail=w.document.querySelector('.vs-evidence');assert.ok(detail);assert.equal(detail.open,false);
    assert.equal(detail.querySelector('blockquote').textContent,quoteText);assert.equal(detail.querySelectorAll('img,script').length,0);
    assert.ok(detail.querySelector('button'));assert.match(detail.textContent,/supports the explanation/);
    const checked=[...w.document.querySelectorAll('.vs-action-note')].filter(node=>node.textContent==='Checked against the supplied evidence');assert.equal(checked.length,1,'Only the separately reviewed reply gets the label');assert.match(checked[0].title,/automated.*mistakes/);
    assert.match($('lc-usage').textContent,/2.*0\.20 reserved.*123 tokens.*Actual billed cost is unavailable/);
    assert.ok($('lc-usage').closest('details'),'Usage belongs in optional settings');assert.equal(posts.length,0);
  }else if(['exhausted','last-reservation','resumed'].includes(f.scenario)){
    const source=editor().value;inputValue('vs-reply','My unsent question');$('vs-consent').checked=true;$('vs-consent').dispatchEvent(new w.Event('change',{bubbles:true}));
    if(f.scenario==='resumed')assert.equal($('vs-send').disabled,false,'Resumed allowance enables the reply after consent');
    else{assert.equal($('vs-send').disabled,true);assert.equal($('vs-hint').disabled,true);assert.equal($('vs-explain').disabled,true);assert.match($('vs-chat-status').textContent,/Meta assistance is paused.*allowance/);$('vs-send').click();}
    assert.equal(editor().value,source);assert.equal($('vs-reply').value,'My unsent question');assert.equal($('vs-run').disabled,false,'Local Python stays available');assert.equal(posts.length,0);
  }else if(f.scenario==='preferences'){
    inputValue('lc-goal','Practise loops independently');$('lc-explanation').value='short_steps';$('lc-representation').value='boxes';
    await w.LessonTraceCoach.refresh();assert.equal($('lc-goal').value,'Practise loops independently','Poll preserves unsaved settings');
    $('lc-save').click();await until(()=>preferences.revision===1&&!$('lc-save').disabled,'Save completes and controls recover');
    assert.equal(posts.filter(item=>item.path==='/api/coach/preferences').length,1);assert.equal($('vs-representation').value,'boxes');
    $('lc-reset').click();await until(()=>preferences.revision===2&&!$('lc-reset').disabled,'Reset completes');assert.equal($('lc-goal').value,'');
  }else if(f.scenario==='library'){
    inputValue('vs-reply','Unsent tutor question');editor().value='def score_for(scores, name):\n    return 123';editor().dispatchEvent(new w.Event('input'));
    await w.LessonTraceCoach.resume(old.session.lesson_id);await until(()=>active===old&&!$('vs-notes').disabled,'Older lesson opens');
    assert.notEqual(editor().value,'def score_for(scores, name):\n    return 123');
    assert.equal($('vs-reply').value,'','Unsent replies do not cross lesson boundaries');
    await w.LessonTraceCoach.resume(f.video.session.lesson_id);await until(()=>editor().value==='def score_for(scores, name):\n    return 123','Original draft restored');
    assert.equal($('vs-consent').checked,false,'Resume does not grant tutor processing');
    assert.equal($('vs-reply').value,'Unsent tutor question','Unsent reply stays with its original activity');
  }else if(f.scenario==='research'){
    $('lc-research').open=true;const find=text=>[...$('lc-research-content').querySelectorAll('button')].find(button=>button.textContent===text);
    find('Prepare one follow-up').click();await delay(30);assert.equal(researchPosts,0);assert.match($('lc-status').textContent,/Allow/);
    $('lc-research-consent').checked=true;find('Prepare one follow-up').click();find('Prepare one follow-up').click();
    await until(()=>$('lc-next').textContent.includes('A focused follow-up is ready'),'Ready follow-up appears');assert.equal(researchPosts,1);assert.equal(active,f.video,'Ready result does not replace the active lesson');
    assert.match($('vs-meta-tab').textContent,/ready/);$('lc-next').querySelector('button').click();
    await until(()=>w.location.hash==='#hub-learn'&&$('vs-title').textContent==='Follow an inner break','Explicitly opens follow-up');
    assert.equal($('vs-consent').checked,false,'Research consent does not grant code-sharing consent');
  }else if(f.scenario==='fresh'){
    assert.match($('lc-next').textContent,/fresh check/);assert.equal($('lc-research-consent'),null);assert.equal($('vs-meta-tab').textContent,'Ask Meta');assert.equal(posts.length,0);
  }else if(f.scenario==='conflict'){
    inputValue('lc-goal','Keep my typed goal');$('lc-save').click();await until(()=>!$('lc-reload').hidden,'Conflict recovery offered');assert.equal($('lc-goal').value,'Keep my typed goal');
    await w.LessonTraceCoach.refresh();$('lc-reload').click();await until(()=>$('lc-goal').value==='Saved in another tab','Conflict reload fetches the saved version');assert.equal(researchPosts,0);
  }else if(f.scenario==='network'){
    inputValue('lc-goal','Keep my goal through a connection failure');$('lc-save').click();await until(()=>!$('lc-reload').hidden&&!$('lc-save').disabled,'Failed save releases the controls');
    await delay(300);assert.equal($('lc-save').disabled,false,'A failed refresh must not leave Save stuck');assert.equal($('lc-goal').value,'Keep my goal through a connection failure');
    networkFailed=false;$('lc-save').click();await until(()=>preferences.revision===1&&!$('lc-save').disabled,'Retry succeeds after recovery');assert.equal(researchPosts,0);
  }else{
    const research=[...$('lc-research-content').querySelectorAll('button')];assert.equal(research.length,2);assert.ok(research.every(button=>button.disabled));assert.equal(posts.length,0);
  }
  assert.deepEqual(issues,[]);process.stdout.write(JSON.stringify({scenario:f.scenario,controls:'passed',model_calls:0})+'\n');
}finally{w.close();}

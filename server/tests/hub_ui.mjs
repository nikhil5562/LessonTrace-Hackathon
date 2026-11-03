import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';

const [root,jsdomPath]=process.argv.slice(2),{JSDOM,VirtualConsole}=await import(pathToFileURL(jsdomPath).href);
let input='';for await(const part of process.stdin)input+=part;const f=JSON.parse(input),scenario=f.scenario,issues=[];
const console=new VirtualConsole();console.on('jsdomError',e=>issues.push(e.message));
const dom=new JSDOM(await fs.readFile(path.join(root,'app/index.html'),'utf8'),{url:'http://127.0.0.1:8897/'+(scenario==='reopen'?'#hub-learn':scenario==='direct_hub'?'#hub':'#video'),runScripts:'outside-only',pretendToBeVisual:true,virtualConsole:console}),w=dom.window;
w.HTMLElement.prototype.scrollIntoView=function(){};w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};w.HTMLDialogElement.prototype.close=function(){this.open=false;};
w.matchMedia=()=>({matches:false,addListener(){},removeListener(){},addEventListener(){},removeEventListener(){}});w.ResizeObserver=class{observe(){} unobserve(){} disconnect(){}};
w.addEventListener('error',event=>issues.push(event.error?.stack||event.message));w.URL.createObjectURL=()=> 'blob:synthetic-notes';w.URL.revokeObjectURL=()=>{};
const delay=ms=>new Promise(r=>setTimeout(r,ms)),reply=(body,status=200)=>({ok:status===200,status,json:async()=>structuredClone(body)});
let job=null,polls=0,posts=[],savedHub=['reopen','cancel','failed_research','direct_hub'].includes(scenario)?f.hub.session:null,download=null,failedTransport=false,retried=false;
const readyJob=()=>({id:job.id,status:'ready',phase:'ready',message:'Checked synthetic lesson ready',steps:[{action:'read_sources',detail:'Read a primary reference.'}]});
w.fetch=async(url,options={})=>{
  const u=new URL(url,w.location.href);assert.equal(u.origin,'http://127.0.0.1:8897','No external requests in offline UI checks');
  if(u.pathname.startsWith('/api/video-session/download/')){download=u;return {ok:true,headers:{get:()=> 'attachment; filename="synthetic-notes.md"'},blob:async()=>new w.Blob(['synthetic notes'])};}
  if(options.method==='POST'){
    const body=JSON.parse(options.body);assert.equal(options.headers['X-LessonTrace-CSRF'],f.responses['/api/session'].csrf);
    if(u.pathname==='/api/hub/research'){
      assert.equal(body.consent,true);assert.equal(body.base_lesson_id,f.video.session.lesson_id);posts.push(body);
      if(scenario==='retry_transport'&&!failedTransport){failedTransport=true;return reply({detail:'Synthetic connection lost after queuing research.'},503);}
      await delay(30);job={id:body.request_id,status:'queued',phase:'queued',message:'Starting synthetic research',steps:[]};return reply({job,session:null,allowance:f.allowance});
    }
    if(u.pathname.endsWith('/cancel')){job={...job,status:'cancelled',phase:'cancelled',message:'Research stopped'};return reply({job,session:null,allowance:f.allowance});}
    if(u.pathname.endsWith('/retry')){assert.equal(body.consent,true);retried=true;job={...job,status:'queued',phase:'queued',can_retry:false};return reply({job,session:null,allowance:f.allowance});}
    if(u.pathname==='/api/coach/resume'){assert.equal(body.lesson_id,f.hub.session.lesson_id);savedHub=f.hub.session;return reply({session:savedHub});}
    assert.fail('Unexpected mutation '+u.pathname);
  }
  if(u.pathname==='/api/video-session')return reply({session:f.video.session});
  if(u.pathname==='/api/video-learning')return reply({learning:u.searchParams.get('context')==='hub'?f.hub.learning:f.video.learning,allowance:f.allowance});
  if(u.pathname==='/api/hub')return reply({catalog:f.catalog,session:savedHub,job,allowance:f.allowance});
  if(u.pathname.startsWith('/api/hub/research/')){
    polls++;
    if(scenario==='cancel')return reply({job:{...job,status:'running',phase:'reading'},session:null,allowance:f.allowance});
    if(scenario==='failed_research'){job={...job,status:'failed',phase:'failed',message:'Synthetic source unavailable; saved lesson kept.'};return reply({job,session:null,allowance:f.allowance});}
    if(scenario==='retry_preparation'&&!retried){job={...job,status:'failed',phase:'failed',can_retry:true,message:'Synthetic preparation rejected; passages saved.'};return reply({job,session:null,allowance:f.allowance});}
    if(polls<2)return reply({job:{...job,status:'running',phase:'reading'},session:null,allowance:f.allowance});
    job=readyJob();savedHub=f.hub.session;return reply({job,session:savedHub,allowance:f.allowance});
  }
  assert.ok(u.pathname in f.responses,'Unmocked '+u.pathname);return reply(f.responses[u.pathname]);
};
async function until(check,label){const limit=Date.now()+8000;while(!check()){assert.ok(Date.now()<limit,'Timed out: '+label);await delay(10);}}
const $=id=>w.document.getElementById(id);
async function openHubLesson(){if(w.location.hash!=='#hub-learn')$('hub-begin').click();await until(()=>!$('video-studio-panel').hidden&&$('vs-title').textContent==='Follow an inner break'&&!$('vs-notes').disabled,'Hub workspace opens');}
function hubLayout(){assert.equal(w.document.body.dataset.view,'hub');assert.equal(w.getComputedStyle(w.document.querySelector('.app-layout')).display,'block','Hub must use the full workspace instead of the old sidebar grid');assert.equal(w.getComputedStyle(w.document.querySelector('.course-sidebar')).display,'none');assert.equal($('hub-panel').parentElement,$('workspace'));assert.equal($('workspace').lastElementChild.tagName,'FOOTER','Footer must follow Hub content');assert.equal($('hub-panel').nextElementSibling.tagName,'FOOTER');}
try{
  for(const link of w.document.querySelectorAll('link[rel="stylesheet"]')){const style=w.document.createElement('style');style.textContent=await fs.readFile(path.join(root,'app/assets',path.basename(new URL(link.href).pathname)),'utf8');w.document.head.append(style);}
  for(const tag of w.document.querySelectorAll('script[src]')){const name=path.basename(new URL(tag.src).pathname);if(name==='lesson-editor.bundle.js')continue;w.eval(await fs.readFile(path.join(root,'app/assets',name),'utf8')+'\n//# sourceURL='+name);}
  if(scenario==='reopen')await openHubLesson();
  else if(scenario==='direct_hub'){await until(()=>!$('hub-ready').hidden,'Saved Hub opens directly');hubLayout();await openHubLesson();}
  else{
    await until(()=>$('vs-title').textContent==='Look up a value'&&!$('vs-deeper').disabled,'Original video workspace opens');
    const videoEditor=w.document.querySelector('#vs-editor textarea');videoEditor.value='def score_for(scores, name):\n    return 123';videoEditor.dispatchEvent(new w.Event('input'));
    $('vs-deeper').click();await until(()=>!$('hub-panel').hidden&&$('hub-base').textContent.includes('Look up a value'),'Linked Hub opens');
    hubLayout();
    $('hub-start').click();await delay(40);assert.equal(posts.length,0);assert.match($('hub-message').textContent,/Allow Meta/);
    $('hub-consent').checked=true;$('hub-start').click();$('hub-start').click();
    await until(()=>posts.length===1,'Research starts once');
    if(scenario==='retry_transport'){
      await until(()=>!$('hub-start').disabled,'Transport failure is recoverable');assert.match($('hub-message').textContent,/Synthetic connection/);
      $('hub-start').click();await until(()=>posts.length===2,'Retry submitted');assert.equal(posts[0].request_id,posts[1].request_id,'Retry uses the same job ID');
    }
    if(scenario==='cancel'){
      await until(()=>!$('hub-job').hidden&&!$('hub-stop').hidden,'Stop available');$('hub-stop').click();await until(()=>$('hub-job-message').textContent==='Research stopped','Cancellation displayed');
      assert.equal($('hub-ready').hidden,false,'A cancelled job preserves the previous Hub');assert.equal(posts.length,1);
    }else if(scenario==='failed_research'){
      await until(()=>$('hub-job-message').textContent.includes('Synthetic source unavailable'),'Research failure shown');assert.equal($('hub-ready').hidden,false,'Failure preserves previous Hub');
    }else{
      if(scenario==='retry_preparation'){await until(()=>!$('hub-retry').hidden,'Preparation retry offered');$('hub-retry').click();await until(()=>retried,'Retry uses saved source preparation');}
      await until(()=>$('hub-job-message').textContent==='Checked synthetic lesson ready','Research completes');
    }
    await openHubLesson();assert.equal($('vs-back').getAttribute('href'),'#hub');assert.equal($('vs-deeper').hidden,true);
    assert.equal($('vs-consent').checked,false,'Research consent must not authorize sending learner code to the tutor');
    $('vs-consent').checked=true;$('vs-consent').dispatchEvent(new w.Event('change'));
    const hubEditor=w.document.querySelector('#vs-editor textarea');assert.match(hubEditor.value,/first_matches/);assert.ok(!hubEditor.value.includes('return 123'),'Video draft must not become Hub code');hubEditor.value='def first_matches(rows, limit):\n    return []';hubEditor.dispatchEvent(new w.Event('input'));
    w.location.hash='video';await until(()=>$('vs-title').textContent==='Look up a value'&&!$('vs-notes').disabled,'Video reopens');assert.equal(w.document.querySelector('#vs-editor textarea').value,'def score_for(scores, name):\n    return 123','Original draft retained');
    assert.equal($('vs-consent').checked,false,'Hub tutor consent must not change the original video consent');
    w.location.hash='hub-learn';await until(()=>$('vs-title').textContent==='Follow an inner break'&&!$('vs-notes').disabled,'Hub reopens');assert.equal(w.document.querySelector('#vs-editor textarea').value,'def first_matches(rows, limit):\n    return []','Hub draft retained separately');
    assert.equal($('vs-consent').checked,true,'The same Hub keeps its explicit tutor choice');
  }
  assert.equal(w.document.body.dataset.view,'hub-learn');assert.equal($('learn-panel').hidden,true);
  w.document.querySelector('#vs-lesson .inline-source').click();assert.ok(w.document.querySelector('.vs-source a').href.startsWith('https://docs.python.org/'));assert.equal(w.document.querySelector('#vs-lesson iframe'),null,'Web citations must not open a made-up video timestamp');
  $('vs-notes').click();assert.equal($('notes-reader').open,true);assert.equal($('notes-reader-title').textContent,f.hub.session.title);
  const choice=$('notes-format-reader');choice.value='md';choice.closest('.notes-download').querySelector('button').click();await until(()=>download,'Download request sent');assert.equal(download.searchParams.get('context'),'hub');assert.equal(download.searchParams.get('expected_revision'),f.hub.session.revision);
  assert.equal(w.LessonTraceHub.safeURL('javascript:alert(1)'),null);assert.equal(w.LessonTraceHub.safeURL('https://example.org/unreviewed'),null);
  await delay(20);assert.deepEqual(issues.filter(message=>!message.includes('navigation (except hash changes)')),[]);
  process.stdout.write(JSON.stringify({scenario,private_contexts:true,source_links:true,downloads:'hub',model_calls:0})+'\n');
}finally{w.close();}

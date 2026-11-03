import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [root,jsdomPath]=process.argv.slice(2),{JSDOM,VirtualConsole}=await import(pathToFileURL(jsdomPath).href);
let input='';for await(const part of process.stdin)input+=part;const f=JSON.parse(input),issues=[],posts=[];
const console=new VirtualConsole();console.on('jsdomError',error=>issues.push(error.message));
const dom=new JSDOM(await fs.readFile(path.join(root,'app/index.html'),'utf8'),{url:'http://127.0.0.1:8897/#courses',runScripts:'outside-only',pretendToBeVisual:true,virtualConsole:console}),w=dom.window;
w.HTMLElement.prototype.scrollIntoView=function(){};w.HTMLDialogElement.prototype.showModal=function(){this.open=true;};w.HTMLDialogElement.prototype.close=function(){this.open=false;};
w.matchMedia=()=>({matches:false,addEventListener(){},removeEventListener(){}});w.ResizeObserver=class{observe(){} disconnect(){}};
w.addEventListener('error',e=>issues.push(e.error?.stack||e.message));
let learning=f.learning;const reply=value=>({ok:true,status:200,json:async()=>structuredClone(value)});
w.fetch=async(url,options={})=>{const target=new URL(url,w.location.href);assert.equal(target.origin,'http://127.0.0.1:8897');
  if(options.method==='POST'){const body=JSON.parse(options.body);posts.push({path:target.pathname,body});assert.equal(options.headers['X-LessonTrace-CSRF'],f.responses['/api/session'].csrf);
    if(target.pathname==='/api/course/open'){assert.equal(body.concept_id,'for_loop');return reply({session:f.session});}
    if(target.pathname==='/api/video-learning/move'){if(f.scenario==='lesson-first'){assert.equal(body.action,'quiz');learning=structuredClone(f.learning);learning.progress.phase='prediction';learning.progress.lesson_opened=true;learning.progress.next_action=null;return reply({learning,allowance:f.board.allowance});}assert.equal(body.action,'fresh_check');assert.equal(body.consent,false);learning=f.fresh;return reply({learning,allowance:f.board.allowance});}
    assert.fail('Unexpected mutation '+target.pathname);
  }
  if(target.pathname==='/api/course')return reply(f.board);
  if(target.pathname==='/api/runs/display-fixture')return reply(f.run);
  if(target.pathname==='/api/course/session')return reply({session:f.session});
  if(target.pathname==='/api/video-session')return reply({session:null});
  if(target.pathname==='/api/video-learning')return reply({learning:target.searchParams.get('context')==='course'?learning:null,allowance:f.board.allowance});
  if(target.pathname==='/api/coach')return reply(f.coach);
  if(target.pathname==='/api/hub')return reply({session:null,job:null,catalog:[],allowance:f.board.allowance});
  assert.ok(target.pathname in f.responses,'Unmocked path '+target.pathname);return reply(f.responses[target.pathname]);
};
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));async function until(check,label){const end=Date.now()+8000;while(!check()){assert.ok(Date.now()<end,'Timed out '+label);await delay(10);}}
try{
  for(const link of w.document.querySelectorAll('link[rel="stylesheet"]')){const style=w.document.createElement('style');style.textContent=await fs.readFile(path.join(root,'app/assets',path.basename(new URL(link.href).pathname)),'utf8');link.replaceWith(style);}
  for(const script of w.document.querySelectorAll('script[src]')){const name=path.basename(new URL(script.src).pathname);if(name==='lesson-editor.bundle.js')continue;w.eval(await fs.readFile(path.join(root,'app/assets',name),'utf8')+'\n//# sourceURL='+name);}
  await until(()=>w.document.querySelectorAll('.cp-unit').length===5,'Five course units');
  assert.equal(w.document.getElementById('course-panel').hidden,false);assert.equal(w.getComputedStyle(w.document.querySelector('.app-layout')).display,'block');
  const row=id=>w.document.querySelector(`[data-concept="${id}"]`);assert.equal(row('for_loop').querySelector('button').disabled,false);assert.equal(row('loop_if_else').querySelector('button').disabled,true);assert.match(row('loop_if_else').textContent,/Choosing with if and else/);
  assert.ok(w.document.getElementById('course-panel').compareDocumentPosition(w.document.querySelector('footer'))&w.Node.DOCUMENT_POSITION_FOLLOWING);
  if(f.scenario==='overview'){assert.equal(posts.length,0);assert.match(w.document.querySelector('[data-unit="functions"] summary').textContent,/Outline · lessons planned/);assert.match(w.document.getElementById('cp-privacy').textContent,/no Meta request/);const unit=w.document.querySelector('.cp-unit');unit.open=true;const choice=w.document.getElementById('cp-auto');choice.checked=true;choice.dispatchEvent(new w.Event('change'));await w.LessonTraceCourse.refresh();assert.equal(unit.open,true);assert.equal(choice.checked,true,'Refreshing preserves an unsaved support choice');assert.equal(posts.length,0);}
  else{
    row('for_loop').querySelector('button').click();await until(()=>w.location.hash==='#course-learn'&&w.document.querySelector('#vs-editor textarea'),'Course studio opens');
    assert.equal(posts.filter(p=>p.path==='/api/course/open').length,1);assert.match(w.document.getElementById('vs-back').textContent,/Python Fundamentals/);
    if(f.scenario==='lesson-first'){
      assert.equal(w.document.getElementById('vs-workbench').hidden,true);assert.match(w.document.getElementById('vs-stage').textContent,/READ THE LESSON FIRST/);assert.ok(w.document.querySelector('.vs-course-reading').textContent.length>100);assert.match(w.document.getElementById('vs-continue').textContent,/Start the topic check/);
      w.document.getElementById('vs-continue').click();await until(()=>w.document.querySelector('input[name="vs-answer"]'),'Quiz opens after the teaching lesson');assert.equal(w.document.querySelector('.vs-course-reading'),null);assert.equal(w.document.getElementById('vs-workbench').hidden,true);assert.ok(!posts.some(p=>p.body.action==='fresh_check'));
    }else{
    assert.match(w.document.querySelector('.vs-input-example').textContent,f.scenario==='trace'?/left = 0, right = 4/:/values =/);assert.equal(w.document.querySelector('#vs-editor textarea').value,f.learning.unit.exercise.starter);assert.equal(w.document.getElementById('vs-consent').checked,false);
    if(f.scenario==='trace'){
      assert.match(w.document.getElementById('vs-replay-inputs').textContent,/check 2 of 2.*left = 0, right = 4/);
      assert.equal(w.document.getElementById('vs-executed-code').textContent,'Line 1: result = 1');assert.deepEqual([...w.document.querySelectorAll('.studio-scalars dd')].map(n=>n.textContent),['0','4','1']);
      w.document.getElementById('vs-next-step').click();assert.equal(w.document.getElementById('vs-executed-code').textContent,'Line 2: result = 2');assert.deepEqual([...w.document.querySelectorAll('.studio-scalars dd')].map(n=>n.textContent),['0','4','2']);
      const editor=w.document.querySelector('#vs-editor textarea');editor.value+='\nresult = 3';editor.dispatchEvent(new w.Event('input'));assert.equal(w.document.getElementById('vs-prev').disabled,true);assert.equal(w.document.querySelector('.studio-scalars'),null);assert.equal(w.document.getElementById('vs-executed-code').hidden,true);assert.match(w.document.getElementById('vs-state').textContent,/edited after this run/);
    }
    if(f.scenario==='progress'){
      assert.match(w.document.getElementById('cp-support').textContent,/1\/3 checks passed/);assert.match(row('for_loop').textContent,/1 of 3/);
      f.board.demonstrated.push('for_loop');const item=f.board.units.flatMap(u=>u.topics).find(c=>c.id==='for_loop');item.demonstrated=true;item.completion={...item.completion,stage:'complete',quiz_correct:2,quiz_total:2,practice_passed:true,independent_passed:true,message:'Topic check, main practice and independent task passed.'};
      w.dispatchEvent(new w.Event('lessontrace-learning-state'));await until(()=>row('for_loop').classList.contains('is-done'),'Progress refreshes after the learning event, without waiting for the 15-second poll');assert.match(w.document.getElementById('cp-support').textContent,/Independent task passed/);
    }
    }
    if(f.scenario==='fresh'){w.document.getElementById('vs-continue').click();await until(()=>posts.some(p=>p.path==='/api/video-learning/move'),'Frozen fresh transition');await until(()=>w.document.querySelector('#vs-editor textarea').value===f.fresh.unit.exercise.starter,'Fresh draft opens');assert.equal(w.document.getElementById('vs-consent').checked,false);}
  }
  assert.deepEqual(issues,[]);process.stdout.write(JSON.stringify({scenario:f.scenario,course_controls:'passed',cloud_calls:0})+'\n');
}finally{w.close();}

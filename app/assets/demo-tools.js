(() => {
  'use strict';
  const el=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
  const course=document.querySelector('#course-panel .cp-heading');
  if(course){
    const entry=el('div',undefined,'demo-entry');
    const copy=el('div');copy.append(el('strong','Try the original sample'),el('p','Two loops, one deliberate bug. Prepared notes and real Python work without a key; live Meta tutoring is optional.'));
    const start=el('button','Open sample →');start.type='button';
    const status=el('p','', 'subtle');status.setAttribute('role','status');
    start.onclick=async()=>{
      if(window.LessonTraceVideoStudio?.isBusy()){status.textContent='Finish the current request before opening the sample.';return;}
      start.disabled=true;status.textContent='Checking the original sample with Python…';
      try{
        window.LessonTraceVideoStudio?.saveDraft();
        const session=await fetch('/api/session',{cache:'no-store'}).then(r=>r.json());
        const response=await fetch('/api/demo/start',{method:'POST',headers:{'X-LessonTrace-CSRF':session.csrf}});
        const data=await response.json();if(!response.ok)throw new Error(data.detail||'The sample could not open.');
        await window.LessonTraceVideoStudio.setRecord(data.session,{lazy:true});
        location.hash='#hub-learn';status.textContent='';
      }catch(error){status.textContent=error.message||'The sample could not open. Your work was kept.';}
      finally{start.disabled=false;}
    };
    entry.append(copy,start,status);course.append(entry);
  }
  const panel=el('details',undefined,'meta-activity');panel.id='meta-activity';
  panel.append(el('summary','Live Meta calls'));
  panel.append(el('p','This browser’s requests since this server started. A received response shows an API result, not that the teaching is correct. Prepared lessons and recorded examples are not live calls.','subtle'));
  const rows=el('div'),notice=el('p','Open this panel before sending a Meta question or starting research.','subtle');notice.setAttribute('role','status');panel.append(notice,rows);
  function placePanel(){
    const host=document.getElementById(location.hash==='#hub'?'hub-form':'vs-meta');
    if(host&&panel.parentElement!==host)host.append(panel);
  }
  window.addEventListener('hashchange',placePanel);
  window.addEventListener('lessontrace-hub-ready',placePanel);
  placePanel();
  let timer=null,loading=false;
  async function refresh(){
    if(!panel.open||loading||document.hidden)return;loading=true;
    try{
      const response=await fetch('/api/meta/activity',{cache:'no-store'});if(!response.ok)throw new Error();const data=await response.json();
      rows.replaceChildren();notice.textContent=data.events.length?'Most recent requests first. No prompts or keys are shown.':'No Meta requests from this browser in this server session.';
      for(const event of [...data.events].reverse()){
        const row=el('article',undefined,'meta-call');row.dataset.mode=event.mode;
        const state=event.status==='preparing'?'Preparing…':event.status==='sending'?'Sending…':event.status==='response_received'?'Response received':'Failed';
        const mode=event.mode==='live'?'LIVE META':event.mode==='controlled-test'?'CONTROLLED TEST':'NO HTTP REQUEST SENT';
        row.append(el('strong',mode+' · '+state),el('p',event.model+' · '+event.purpose));
        row.append(el('code',event.endpoint));
        const time=new Date(event.started_at*1000).toLocaleTimeString();
        row.append(el('p',time+(event.latency_ms!==undefined?' · '+(event.latency_ms/1000).toFixed(1)+' s':'')+(event.failure?' · '+event.failure:''),'subtle'));
        if(event.request_id)row.append(el('code','Response ID: '+event.request_id));
        if(event.reported_tokens?.total_tokens!==undefined)row.append(el('p','Provider-reported tokens: '+event.reported_tokens.total_tokens,'subtle'));
        rows.append(row);
      }
    }catch{notice.textContent='Call status is unavailable. The lesson and your saved work are unchanged.';}
    finally{loading=false;}
  }
  panel.addEventListener('toggle',()=>{clearInterval(timer);timer=null;if(panel.open){refresh();timer=setInterval(refresh,1500);}});
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
})();

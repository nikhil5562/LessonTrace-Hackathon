(() => {
  'use strict';
  const $=id=>document.getElementById(id),el=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
  const state={csrf:'',meta:false,record:null,busy:false,remaining:null,ready:false,connecting:false,connectionError:'',previewVersion:0,urlEdited:false};
  const readiness=el('p','Connecting to your workspace…','session-readiness');readiness.id='session-readiness';readiness.setAttribute('role','status');
  $('session-create').closest('.session-url-row').after(readiness);$('session-create').setAttribute('aria-describedby','session-readiness');$('session-url').setAttribute('aria-describedby','session-readiness session-create-status');
  document.querySelector('#learn-panel .page-heading h1').textContent='What are you learning today?';document.querySelector('#learn-panel .lesson-tag').textContent='Video → notes → practice';
  const menu=el('details',undefined,'header-tools');menu.append(el('summary','More'));const menuLinks=el('div');const bank=el('a','Original practice bank');bank.href='#guided';menuLinks.append(bank,document.querySelector('.header-right a[href="/plan/"]'));menuLinks.addEventListener('click',event=>{if(event.target.closest('a'))menu.open=false;});menu.append(menuLinks);document.querySelector('.header-right').append(menu);
  const aside=document.querySelector('.studio-coach');
  const tutor=el('div');tutor.id='session-tutor';while(aside.firstChild)tutor.append(aside.firstChild);
  const lesson=el('div');lesson.id='session-lesson';lesson.hidden=false;
  const tabs=el('div',undefined,'session-tabs');tabs.setAttribute('role','tablist');tabs.setAttribute('aria-label','Lesson workspace');
  const lessonTab=el('button','Lesson'),tutorTab=el('button','Ask Meta');
  for(const [button,id] of [[lessonTab,'session-lesson'],[tutorTab,'session-tutor']]){button.type='button';button.setAttribute('role','tab');button.setAttribute('aria-controls',id);tabs.append(button);}
  lesson.setAttribute('role','tabpanel');tutor.setAttribute('role','tabpanel');aside.append(tabs,lesson,tutor);tutor.hidden=true;
  const video=el('div');video.id='session-player';
  const notes=el('div');notes.id='session-notes';const source=el('div');source.id='session-source';
  const reader=el('dialog',undefined,'notes-reader');reader.id='notes-reader';reader.setAttribute('aria-labelledby','notes-reader-title');const readerHeader=el('div',undefined,'notes-reader-header'),readerTitle=el('h2');readerTitle.id='notes-reader-title';const readerClose=el('button','Back to my lesson');readerClose.type='button';readerClose.addEventListener('click',()=>reader.close());readerHeader.append(readerTitle,readerClose);const readerBody=el('div',undefined,'notes-reader-body'),readerDownloads=el('div',undefined,'reader-downloads');reader.append(readerHeader,readerDownloads,readerBody);document.body.append(reader);
  const originalNotes=document.querySelector('#guided-panel .unit-notes');
  lesson.append(video,notes,source,originalNotes);
  document.querySelector('#guided-panel .tutorial-source').hidden=true;
  const settings=el('details',undefined,'session-advanced');settings.append(el('summary','Processing settings'));
  const provider=$('learning-provider'),providerLabel=tutor.querySelector('label[for="learning-provider"]');settings.append(providerLabel,provider,$('learning-cloud-status'));
  tutor.append(settings);
  const formConsent=$('learning-consent').closest('label');formConsent.classList.add('session-cloud-consent');
  const questionInput=$('learning-question-input');questionInput.rows=2;
  const composer=el('div',undefined,'coach-composer');questionInput.before(composer);composer.append(questionInput,$('learning-ask'));$('learning-ask').textContent='Send →';
  const coachReadiness=el('p',undefined,'coach-readiness');coachReadiness.id='learning-ask-reason';coachReadiness.setAttribute('role','status');coachReadiness.hidden=true;composer.before(coachReadiness);$('learning-ask').setAttribute('aria-describedby','learning-ask-reason');
  const privacyPlace=el('span');formConsent.before(privacyPlace);
  function consentPlacement(){if($('learning-consent').checked)settings.append(formConsent);else privacyPlace.after(formConsent);}
  $('learning-consent').addEventListener('change',consentPlacement);consentPlacement();
  settings.append(tutor.querySelector('.coach-footnote'));
  const thirdSuggestion=tutor.querySelector('[data-coach-question*="return"]');if(thirdSuggestion)settings.append(thirdSuggestion);
  const checkDetails=el('details',undefined,'session-check-details');checkDetails.append(el('summary','Check details'),$('learning-checks'));$('learning-task-card').append(checkDetails);
  const shortResult=el('p',undefined,'session-result');shortResult.setAttribute('aria-live','polite');$('learning-run').closest('.studio-run-actions').after(shortResult);
  new MutationObserver(()=>{const text=$('learning-checks').querySelector('strong')?.textContent||$('learning-checks').textContent;shortResult.textContent=text||'';}).observe($('learning-checks'),{childList:true,subtree:true,characterData:true});
  const more=el('details',undefined,'session-advanced');more.append(el('summary','More practice tools'));
  for(const detail of [...document.querySelectorAll('.studio-main > details')])if(detail!==originalNotes)more.append(detail);
  document.querySelector('.studio-main').append(more);
  function pane(name){const show=name==='lesson';lesson.hidden=!show;tutor.hidden=show;lessonTab.setAttribute('aria-selected',String(show));tutorTab.setAttribute('aria-selected',String(!show));}
  lessonTab.addEventListener('click',()=>pane('lesson'));tutorTab.addEventListener('click',()=>pane('tutor'));pane('lesson');
  const time=seconds=>Math.floor(seconds/60)+':'+String(Math.floor(seconds%60)).padStart(2,'0');
  async function fetchSite(path,options={}){
    if(options.method&&options.method!=='GET')return fetch(path,options);
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),8000);
    try{return await fetch(path,{...options,cache:'no-store',signal:controller.signal});}
    catch(error){if(controller.signal.aborted)throw new Error('LessonTrace took too long to respond. Use Reconnect to try again.');throw error;}
    finally{clearTimeout(timer);}
  }
  async function sessionInfo(){
    const response=await fetchSite('/api/session');
    if(!response.ok)throw new Error('Cannot connect to LessonTrace. Check that the local website is running, then use Reconnect.');
    const info=await response.json();
    if(!info.csrf||!info.meta)throw new Error('LessonTrace returned an incomplete connection status. Use Reconnect to try again.');
    return info;
  }
  async function connect(){
    state.connecting=true;state.connectionError='';buttons();
    try{const info=await sessionInfo();state.csrf=info.csrf;state.meta=info.meta.enabled;state.remaining=info.meta.allowance?.remaining_requests??null;state.ready=true;return info;}
    catch(error){state.ready=false;state.connectionError=error.message;throw error;}
    finally{state.connecting=false;buttons();}
  }
  async function api(path,body,retry=true){let response;try{response=await fetchSite(path,{method:body===undefined?'GET':'POST',headers:body===undefined?{}:{'Content-Type':'application/json','X-LessonTrace-CSRF':state.csrf},...(body===undefined?{}:{body:JSON.stringify(body)})});}catch(error){throw new Error(error.message||'Cannot reach LessonTrace. Check that the local website is running, then use Reconnect.');}let data;try{data=await response.json();}catch{throw new Error('The website returned an unreadable response. Refresh and try again.');}if((response.status===401||(response.status===403&&data.detail==='Refresh the lesson page and try again.'))&&retry){const info=await sessionInfo();state.csrf=info.csrf;return api(path,body,false);}if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'The lesson could not be created.');return data;}
  function blockedReason(){return !state.ready?state.connectionError||'Connecting to your workspace…':!state.meta?'New notes are paused because Meta is switched off in this server. Local practice still works.':state.remaining===0?'New notes are paused: the app’s approved testing allowance is used. This is separate from your Meta account credits.':!$('session-consent').checked?'Before creating notes, tick “Allow Meta” below.':null;}
  function buttons(){const button=$('session-create');button.disabled=state.busy||state.connecting;button.textContent=state.busy?'Creating lesson…':state.connecting?'Connecting…':state.ready?'Create my lesson →':'Reconnect to LessonTrace →';readiness.textContent=state.busy?'Meta is creating notes and exercises, then Python checks the generated examples. This can take two minutes.':blockedReason()||'Ready to create your lesson.';readiness.classList.toggle('needs-attention',Boolean(!state.connecting&&blockedReason()));}
  function practiceTopic(){const topic=state.record?.practice_topic;if(topic&&$('learning-topic').value!==topic){$('learning-topic').value=topic;$('learning-topic').dispatchEvent(new Event('change'));}}
  function player(start=0){if(!state.record)return;const frame=el('iframe');frame.title=state.record.title;frame.src='https://www.youtube-nocookie.com/embed/'+state.record.video_id+'?start='+Math.floor(start);frame.allow='fullscreen; picture-in-picture';frame.allowFullscreen=true;frame.referrerPolicy='strict-origin-when-cross-origin';video.replaceChildren(frame);}
  function showSource(id){const chunk=state.record?.source_segments.find(c=>c.id===id);if(!chunk)return false;window.LessonTraceVideo.selectedSourceId=id;source.replaceChildren(el('h3','Caption source'+(chunk.start===null?'':' · '+time(chunk.start))),el('p',chunk.excerpt,'caption-excerpt'));if(chunk.start!==null){const jump=el('button','Watch this part of the lesson');jump.type='button';jump.addEventListener('click',()=>{player(chunk.start);video.scrollIntoView({block:'nearest'});});source.append(jump);}pane('lesson');source.scrollIntoView({block:'nearest'});return true;}
  function noteSource(id,record=state.record){const chunk=record?.source_segments.find(c=>c.id===id);return chunk?{label:['hub','course'].includes(record.context)?chunk.source_title+(chunk.start===null?'':' · '+time(chunk.start)):chunk.start===null?'Caption source':time(chunk.start),open:()=>{if(reader.open)reader.close();if(record.interactive)window.LessonTraceVideoStudio.showSource(id,record);else showSource(id);}}:null;}
  function downloadControls(record,context){
    const root=el('div',undefined,'notes-download');root.setAttribute('role','group');root.setAttribute('aria-label','Download lesson notes');
    const label=el('label','Save notes as'),choice=el('select');choice.id='notes-format-'+context;label.htmlFor=choice.id;
    for(const [value,text]of [['pdf','PDF · read or print'],['docx','Word · edit your notes'],['md','Markdown · plain text']]){const option=el('option',text);option.value=value;choice.append(option);}
    const button=el('button','Download notes'),status=el('p',undefined,'download-status');button.type='button';status.setAttribute('role','status');
    button.addEventListener('click',async()=>{button.disabled=true;status.textContent='Preparing your download…';
      try{if(!record.revision)throw new Error('Refresh these notes to enable the new download formats.');const response=await fetch('/api/video-session/download/'+choice.value+'?expected_revision='+encodeURIComponent(record.revision)+'&context='+(['hub','course'].includes(record.context)?record.context:'video'));if(!response.ok){const error=await response.json();throw new Error(typeof error.detail==='string'?error.detail:'The notes could not be downloaded. Refresh and try again.');}const blob=await response.blob(),url=URL.createObjectURL(blob),anchor=el('a');anchor.href=url;anchor.download=response.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)?.[1]||'lessontrace-notes.'+choice.value;document.body.append(anchor);anchor.click();anchor.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);status.textContent=(choice.value==='docx'?'Word':choice.value.toUpperCase())+' download started. No Meta request was needed.';}
      catch(error){status.textContent=error.message;}finally{button.disabled=false;}
    });root.append(label,choice,button,status);return root;
  }
  function render(){
    const record=state.record;notes.replaceChildren();video.replaceChildren();source.replaceChildren();$('session-saved').replaceChildren();
    if(!record){notes.append(el('h2','Start with a small idea.'),el('p','Create a session from your YouTube link, or use the original practice notes below.'));return;}
    notes.append(el('span','META-GENERATED STUDY NOTES','prepared-label'),el('h2',record.title),el('p',(record.auto_generated?'Auto-generated captions · ':'')+record.language+' · '+record.caption_source,'subtle'));
    notes.append(el('p',record.caption_source.startsWith('Learner-supplied')?'Sources used: your reviewed caption text. Audio and video frames were not analysed separately.':'Sources used: YouTube captions only. Audio and video frames were not analysed separately.','notes-source-coverage'));
    notes.append(el('p',record.practice_basis||'Choose a related practice unit on the right. These exercises come from the original practice bank; they were not generated from this video.','session-practice-basis'));
    const reading=el('div');window.LessonTraceNotes.render(reading,record.answer,noteSource);notes.append(reading);
    const sources=el('div',undefined,'session-citations');for(const id of record.sources){const chunk=record.source_segments.find(c=>c.id===id);if(!chunk)continue;const b=el('button',chunk.start===null?'Caption source':time(chunk.start));b.type='button';b.addEventListener('click',()=>showSource(id));sources.append(b);}notes.append(sources,el('p',record.coverage+' Review the generated notes before relying on them.','subtle'));
    const play=el('button','Load the YouTube lesson');play.type='button';play.addEventListener('click',()=>player());video.append(play);
    const expand=el('button','Read full notes');expand.type='button';expand.className='primary notes-expand';expand.addEventListener('click',openNotes);notes.prepend(expand);
    notes.append(downloadControls(record,'lesson'));
    const open=el('a',record.interactive?'Open my lesson session →':'Prepare interactive practice →','primary');open.href=record.interactive?'#video':'#learn';if(!record.interactive)open.addEventListener('click',()=>{$('session-url').value=record.url;$('session-create-status').textContent='Allow Meta below, then create this video’s interactive lesson. Your saved notes stay available until the new lesson passes its checks.';$('session-consent').focus();});$('session-saved').append(el('p',record.title+' · notes saved for this browser.'),open);
    const heading=document.querySelector('.studio-heading h1');heading.textContent=record.title;document.querySelector('.studio-intro').textContent='Keep the lesson and tutor on the left. Predict, write and inspect your code on the right.';
  }
  async function create(){
    if(state.busy||state.connecting)return;if(!state.ready){try{await connect();}catch(error){$('session-create-status').textContent=error.message;return;}}const reason=blockedReason();if(reason){$('session-create-status').textContent=reason;if(state.meta&&state.remaining!==0&&!$('session-consent').checked)$('session-consent').focus();return;}if(!$('session-url').reportValidity())return;if(!$('session-start').reportValidity()||!$('session-end').reportValidity())return;state.previewVersion++;state.busy=true;buttons();$('session-create-status').textContent='Reading captions, creating your lesson with Meta, and checking its code with Python…';
    try{const end=$('session-end').value;const result=await api('/api/video-session/learning',{url:$('session-url').value,consent:$('session-consent').checked,caption_text:$('session-caption-text').value,caption_reviewed:$('session-caption-reviewed').checked,start_seconds:Number($('session-start').value||0)*60,end_seconds:end?Number(end)*60:null});state.record=result.session;state.remaining=result.allowance.remaining_requests;let workspaceError=null;try{render();await window.LessonTraceVideoStudio.setRecord(state.record,{consent:true});}catch(error){workspaceError=error;}$('session-create-status').textContent=workspaceError?'Your lesson was created and saved, but the workspace could not open. Use Open my lesson session to try again.':'Your Meta lesson is ready. Its prediction outputs and practice reference code passed the Python checks.';
      practiceTopic();
      provider.value='meta';provider.dispatchEvent(new Event('change'));$('learning-consent').checked=true;$('learning-consent').dispatchEvent(new Event('change'));pane('lesson');if(!workspaceError)location.hash='video';
    }catch(error){$('session-create-status').textContent=error.message;try{const info=await sessionInfo();state.csrf=info.csrf;state.remaining=info.meta.allowance?.remaining_requests??null;}catch(connectionError){state.ready=false;state.connectionError=connectionError.message;}}finally{state.busy=false;buttons();}
  }
  $('session-create').addEventListener('click',create);$('session-consent').addEventListener('change',buttons);state.urlEdited=$('session-url').value!==$('session-url').defaultValue;$('session-url').addEventListener('input',()=>{state.urlEdited=true;});
  function openNotes(provided){const record=provided?.answer?provided:state.record;if(!record)return;readerTitle.textContent=record.title;window.LessonTraceNotes.render(readerBody,record.answer,id=>noteSource(id,record));readerDownloads.replaceChildren(downloadControls(record,'reader'));if(!reader.open)reader.showModal();}
  window.LessonTraceVideo={openNotes,showSource,acceptSession(record){state.record=record;render();},selectedSourceId:null,showPane:pane,sourceLabel:id=>{const chunk=state.record?.source_segments.find(c=>c.id===id);return chunk?(chunk.start===null?'Caption source':time(chunk.start)):null;}};
  async function init(){
    state.connecting=true;buttons();
    try{
      if(!$('connection').classList.contains('connected'))await new Promise(resolve=>{const obs=new MutationObserver(()=>{if($('connection').classList.contains('connected')){obs.disconnect();resolve();}});obs.observe($('connection'),{attributes:true});setTimeout(()=>{obs.disconnect();resolve();},2500);});
      await connect();
    }catch(error){state.connecting=false;buttons();$('session-create-status').textContent=error.message;return;}
    const previewVersion=state.previewVersion;
    try{
      const saved=await api('/api/video-session');
      if(previewVersion!==state.previewVersion)return;
      state.record=saved.session;if(state.record&&!state.urlEdited)$('session-url').value=state.record.url;
      render();
      if(window.LessonTraceVideoStudio)await window.LessonTraceVideoStudio.setRecord(state.record,{lazy:true});
      practiceTopic();
    }catch(error){if(previewVersion===state.previewVersion)$('session-create-status').textContent='Your saved lesson could not be reopened. You can still create a new lesson. '+error.message;}
    finally{buttons();}
    if(state.meta){provider.value='meta';provider.dispatchEvent(new Event('change'));}
  }

  init();
})();

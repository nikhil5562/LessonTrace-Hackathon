/* A small, text-only Markdown renderer. Model text never becomes executable HTML. */
(() => {
  'use strict';
  const make=(tag,text,cls)=>{const item=document.createElement(tag);if(text!==undefined)item.textContent=text;if(cls)item.className=cls;return item;};
  function inline(parent,text,source){
    const parts=text.split(/(`[^`\n]+`|\*\*[^*\n]+\*\*|\[[A-Za-z][A-Za-z0-9_-]*\])/g);
    for(const part of parts){
      if(part.startsWith('`')&&part.endsWith('`'))parent.append(make('code',part.slice(1,-1)));
      else if(part.startsWith('**')&&part.endsWith('**'))parent.append(make('strong',part.slice(2,-2)));
      else if(part.startsWith('[')&&part.endsWith(']')&&source){const reference=source(part.slice(1,-1));if(reference){const button=make('button',reference.label,'inline-source');button.type='button';button.addEventListener('click',reference.open);parent.append(button);}else parent.append(document.createTextNode(part));}
      else parent.append(document.createTextNode(part));
    }
  }
  function cells(line){let row=line.trim();if(row.startsWith('|'))row=row.slice(1);if(row.endsWith('|')&&!row.endsWith('\\|'))row=row.slice(0,-1);return row.split(/(?<!\\)\|/).map(cell=>cell.trim().replace(/\\\|/g,'|'));}
  function render(parent,text,source){
    parent.replaceChildren();parent.classList.add('study-notes');
    let paragraph=[],list=null,code=null,language='';
    const flush=()=>{if(paragraph.length){const p=make('p');inline(p,paragraph.join(' '),source);parent.append(p);paragraph=[];}list=null;};
    const lines=text.replace(/\r\n?/g,'\n').split('\n');
    for(let index=0;index<lines.length;index++){const line=lines[index];
      const fence=line.match(/^\s*```([\w-]*)\s*$/);
      if(fence){if(code!==null){const pre=make('pre'),body=make('code',code.join('\n'));if(language)pre.setAttribute('aria-label',language+' example');pre.append(body);parent.append(pre);code=null;}else{flush();code=[];language=fence[1];}continue;}
      if(code!==null){code.push(line);continue;}
      if(!line.trim()){flush();continue;}
      const headers=cells(line),divider=cells(lines[index+1]||'');
      if(line.includes('|')&&headers.length>=2&&divider.length===headers.length&&divider.every(cell=>/^:?-{3,}:?$/.test(cell))){
        flush();const wrap=make('div',undefined,'notes-table'),table=make('table'),head=make('thead'),row=make('tr'),body=make('tbody');
        wrap.tabIndex=0;wrap.setAttribute('role','region');wrap.setAttribute('aria-label','Lesson table');
        for(const text of headers){const cell=make('th');cell.scope='col';inline(cell,text,source);row.append(cell);}head.append(row);index++;
        while(index+1<lines.length&&lines[index+1].includes('|')){const values=cells(lines[index+1]);if(values.length!==headers.length)break;index++;const row=make('tr');for(const text of values){const cell=make('td');inline(cell,text,source);row.append(cell);}body.append(row);}
        table.append(head,body);wrap.append(table);parent.append(wrap);continue;
      }
      const heading=line.match(/^#{1,4}\s+(.+)$/);
      if(heading){flush();const title=make('h3');inline(title,heading[1],source);parent.append(title);continue;}
      const item=line.match(/^\s*(?:([-*])|\d+[.)])\s+(.+)$/);
      if(item){if(paragraph.length)flush();const tag=item[1]?'ul':'ol';if(!list||list.tagName.toLowerCase()!==tag){list=make(tag);parent.append(list);}const row=make('li');inline(row,item[2],source);list.append(row);continue;}
      if(list)list=null;paragraph.push(line.trim());
    }
    if(code!==null){const pre=make('pre');pre.append(make('code',code.join('\n')));parent.append(pre);}
    flush();
  }
  window.LessonTraceNotes={render};
})();

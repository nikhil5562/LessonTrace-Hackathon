import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const [root,jsdomPath]=process.argv.slice(2),{JSDOM}=await import(pathToFileURL(jsdomPath).href);
const dom=new JSDOM('<div id="notes"></div>',{runScripts:'outside-only'}),w=dom.window;let sourceOpened=false;
try{
  const app=new w.DOMParser().parseFromString(await fs.readFile(path.join(root,'app/index.html'),'utf8'),'text/html');
  for(const link of app.querySelectorAll('link[rel="stylesheet"]')){const style=w.document.createElement('style');style.textContent=await fs.readFile(path.join(root,'app/assets',path.basename(new URL(link.getAttribute('href'),'http://127.0.0.1:8897').pathname)),'utf8');w.document.head.append(style);}
  w.eval(await fs.readFile(path.join(root,'app/assets/study-notes.js'),'utf8'));
  const target=w.document.getElementById('notes'),markdown='## Walk the same values\n\n| Outer | Inner | What happens next |\n|---|---|---|\n| `A` | 1 | Print [hub-example] |\n| `A` | 2 | <img src=x onerror=alert(1)> \\| literal |\n\nAfter the loop.\n\n```python\nprint("| not a table")\n```';
  w.LessonTraceNotes.render(target,markdown,id=>id==='hub-example'?{label:'Official source',open:()=>sourceOpened=true}:null);
  assert.equal(target.querySelectorAll('thead th').length,3);assert.equal(target.querySelectorAll('tbody tr').length,2);
  assert.ok([...target.querySelectorAll('th')].every(cell=>cell.scope==='col'));
  assert.equal(target.querySelector('tbody code').textContent,'A');assert.equal(target.querySelector('tbody tr:last-child td:last-child').textContent,'<img src=x onerror=alert(1)> | literal');
  assert.equal(target.querySelectorAll('img,script').length,0);assert.equal(target.querySelector('pre code').textContent,'print("| not a table")');
  target.querySelector('button.inline-source').click();assert.equal(sourceOpened,true);
  assert.ok([...target.querySelectorAll('p')].some(p=>p.textContent==='After the loop.'));assert.equal(target.querySelector('.notes-table').tabIndex,0);
  function channels(value){
    const variable=value.match(/^var\((--[\w-]+)(?:,\s*([^)]*))?\)$/);if(variable)return channels(w.getComputedStyle(w.document.documentElement).getPropertyValue(variable[1]).trim()||variable[2]);
    if(/^#[\da-f]{6}$/i.test(value))return [1,3,5].map(index=>parseInt(value.slice(index,index+2),16));
    assert.match(value,/^rgb\(/,'Resolved foreground/background colour');return value.match(/[\d.]+/g).slice(0,3).map(Number);
  }
  const luminance=value=>channels(value).map(n=>{n/=255;return n<=.04045?n/12.92:((n+.055)/1.055)**2.4;}).reduce((sum,n,i)=>sum+n*[.2126,.7152,.0722][i],0);
  for(const context of ['vs-course-reading','vs-pane','vs-turn','notes-reader-body']){
    const host=w.document.createElement('section');host.className=context;const body=w.document.createElement('div');host.append(body);w.document.body.append(host);
    w.LessonTraceNotes.render(body,'```python\nwidth = 20\nprint(width)\n```\n\n```text\n20\n```');
    assert.deepEqual([...body.querySelectorAll('pre code')].map(n=>n.textContent),['width = 20\nprint(width)','20']);
    for(const pre of body.querySelectorAll('pre')){const style=w.getComputedStyle(pre),fg=luminance(style.color),bg=luminance(style.backgroundColor),ratio=(Math.max(fg,bg)+.05)/(Math.min(fg,bg)+.05);assert.ok(ratio>=4.5,context+' code/output contrast '+ratio.toFixed(2)+' must be readable');}
  }
  process.stdout.write('Readable table, safe text, preserved code/output and all four notes contexts meet 4.5:1 contrast.\n');
}finally{w.close();}

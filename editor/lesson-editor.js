import {basicSetup} from 'codemirror';
import {EditorState,StateEffect,StateField} from '@codemirror/state';
import {EditorView,Decoration,keymap} from '@codemirror/view';
import {indentWithTab} from '@codemirror/commands';
import {indentUnit} from '@codemirror/language';
import {python} from '@codemirror/lang-python';

const highlightedLine=StateEffect.define();
const traceField=StateField.define({
  create:()=>Decoration.none,
  update(value,transaction){
    if(transaction.docChanged)value=Decoration.none;
    for(const effect of transaction.effects)if(effect.is(highlightedLine)){
      const line=effect.value;
      value=line>0&&line<=transaction.state.doc.lines?Decoration.set([Decoration.line({class:'cm-executed-line'}).range(transaction.state.doc.line(line).from)]):Decoration.none;
    }
    return value;
  },
  provide:field=>EditorView.decorations.from(field)
});

window.LessonTraceEditor={
  create(host,onChange){
    let replacing=false,lastHighlight=null;
    const view=new EditorView({parent:host,state:EditorState.create({doc:'',extensions:[EditorView.cspNonce.of(document.querySelector('meta[name="lessontrace-style-nonce"]')?.content||''),basicSetup,python(),EditorView.lineWrapping,indentUnit.of('    '),keymap.of([indentWithTab]),traceField,
      EditorView.contentAttributes.of({'aria-label':'Python code editor','aria-multiline':'true',spellcheck:'false'}),
      EditorView.theme({'&':{height:'100%',fontSize:'14px'},'.cm-scroller':{fontFamily:'Consolas, monospace',lineHeight:'1.75',overflow:'auto'},'.cm-content':{padding:'12px 0'},'.cm-line':{padding:'0 13px'},'.cm-gutters':{backgroundColor:'#eef3e8',color:'#71836b',border:'none'},'.cm-activeLine,.cm-activeLineGutter':{backgroundColor:'transparent'},'.cm-executed-line':{backgroundColor:'#dceccf',boxShadow:'inset 3px 0 #426c36'},'&.cm-focused':{outline:'2px solid #72976a',outlineOffset:'-2px'}}),
      EditorView.updateListener.of(update=>{if(update.docChanged){lastHighlight=null;if(!replacing)queueMicrotask(()=>onChange(view.state.doc.toString()));}})]})});
    return {getValue:()=>view.state.doc.toString(),setValue(value){replacing=true;view.dispatch({changes:{from:0,to:view.state.doc.length,insert:value}});replacing=false;},
      highlight(line){if(line===lastHighlight)return;lastHighlight=line;const effects=[highlightedLine.of(line)];if(line>0&&line<=view.state.doc.lines)effects.push(EditorView.scrollIntoView(view.state.doc.line(line).from,{y:'nearest'}));view.dispatch({effects});},measure:()=>view.requestMeasure(),focus:()=>view.focus()};
  }
};

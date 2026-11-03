"""Readable, owner-scoped note exports. No provider calls or learner-code execution."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import re
from urllib.parse import urlsplit
from threading import Lock
from xml.sax.saxutils import escape


MIME_TYPES = {
    'pdf': 'application/pdf',
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'md': 'text/markdown; charset=utf-8',
}
_fonts_lock = Lock()


@dataclass(frozen=True)
class Block:
    kind: str
    text: str
    number: int = 0


def revision(record):
    return sha256((record['video_id']+'\n'+record['answer']).encode()).hexdigest()


def source_links(record):
    if record.get('context') in {'hub','course'}:
        def safe(url):
            parts=urlsplit(url)
            if parts.scheme!='https' or parts.hostname not in {'www.youtube.com','docs.python.org','www.learnpython.org'} or parts.username or parts.password or parts.port not in {None,443}:
                raise ValueError('This lesson has an invalid public reference.')
            return url
        return safe(record['url']),{chunk['id']:(chunk['source_title']+' · '+chunk['heading'],safe(chunk['url'])) for chunk in record['caption_chunks']}
    identifier = record['video_id']
    if not re.fullmatch(r'[A-Za-z0-9_-]{11}', identifier):
        raise ValueError('This lesson has an invalid source video.')
    url = 'https://www.youtube.com/watch?v='+identifier
    sources = {}
    for chunk in record['caption_chunks']:
        start = chunk['start']
        label = 'Caption source' if start is None else f'{int(start)//60}:{int(start)%60:02d}'
        sources[chunk['id']] = (label, url if start is None else url+'&t='+str(int(start)))
    return url, sources


def blocks(text):
    result, paragraph, code = [], [], None
    def flush():
        if paragraph:
            result.append(Block('paragraph', ' '.join(paragraph)))
            paragraph.clear()
    def cells(line):
        row=line.strip()
        if row.startswith('|'):row=row[1:]
        if row.endswith('|') and not row.endswith('\\|'):row=row[:-1]
        return [cell.strip().replace('\\|','|') for cell in re.split(r'(?<!\\)\|',row)]
    lines=text.replace('\r\n','\n').replace('\r','\n').split('\n');skip=0
    for index,line in enumerate(lines):
        if index<skip:continue
        if re.fullmatch(r'\s*```[\w-]*\s*',line):
            if code is None:
                flush(); code=[]
            else:
                result.append(Block('code','\n'.join(code))); code=None
            continue
        if code is not None:
            code.append(line); continue
        if not line.strip():
            flush(); continue
        headers=cells(line);divider=cells(lines[index+1]) if index+1<len(lines) else []
        if '|' in line and len(headers)>=2 and len(divider)==len(headers) and all(re.fullmatch(r':?-{3,}:?',cell) for cell in divider):
            flush();skip=index+2
            while skip<len(lines) and '|' in lines[skip]:
                row=cells(lines[skip])
                if len(row)!=len(headers):break
                # Label each row for readable narrow-page Word/PDF exports.
                result.append(Block('bullet','; '.join('**'+header+':** '+cell for header,cell in zip(headers,row))))
                skip+=1
            continue
        heading = re.match(r'^#{1,4}\s+(.+)',line)
        item = re.match(r'^\s*(?:([-*])|(\d+)[.)])\s+(.+)',line)
        if heading:
            flush(); result.append(Block('heading',heading[1]))
        elif item:
            flush(); result.append(Block('bullet' if item[1] else 'number',item[3],int(item[2] or 0)))
        else:
            paragraph.append(line.strip())
    flush()
    if code is not None:
        result.append(Block('code','\n'.join(code)))
    return result


def inlines(text, sources):
    for part in re.split(r'(`[^`\n]+`|\*\*[^*\n]+\*\*|\[(?:video|hub)-[A-Za-z0-9_-]+\])',text):
        if part.startswith('`') and part.endswith('`'):
            yield 'code',part[1:-1],None
        elif part.startswith('**') and part.endswith('**'):
            yield 'bold',part[2:-2],None
        elif part[1:-1] in sources:
            label,url=sources[part[1:-1]]
            yield 'link','['+label+']',url
        else:
            yield 'text',part,None


def heading(text):
    # Export headings use words and whitespace; Python code itself is unchanged.
    return re.sub(r'\s+',' ',re.sub(r'[^\w\s]',' ',text).replace('_',' ')).strip()


def caption_basis(record):
    if record.get('context')=='hub':
        return 'Based on selected passages from the listed public references and creator-published captions when included. This is not a complete-source review; audio and video frames were not analysed.'
    if record.get('caption_source','').startswith('Learner-supplied'):
        return 'Based on reviewed, pasted caption text. Its timing and completeness are unverified.'
    return 'Based on available video captions. Audio and video frames were not analysed separately.'


def markdown(record):
    url,sources=source_links(record)
    answer=re.sub(r'\[((?:video|hub)-[A-Za-z0-9_-]+)\]',lambda m:'['+sources[m[1]][0]+']('+sources[m[1]][1]+')' if m[1] in sources else m[0],record['answer'])
    return '# '+record['title']+'\n\n'+caption_basis(record)+'\n\n'+answer+'\n\nSource: '+url+'\n'


def _docx(record):
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Inches,Pt,RGBColor
    from docx.opc.constants import RELATIONSHIP_TYPE
    doc=Document()
    section=doc.sections[0]
    section.page_width,section.page_height=Inches(8.27),Inches(11.69)
    section.top_margin=section.bottom_margin=Inches(.65)
    section.left_margin=section.right_margin=Inches(.75)
    normal=doc.styles['Normal']
    normal.font.name='Arial';normal.font.size=Pt(11)
    normal.font.color.rgb=RGBColor(0,0,0)
    for attr in ['asciiTheme','hAnsiTheme','eastAsiaTheme','cstheme']:
        normal.element.rPr.rFonts.attrib.pop(qn('w:'+attr),None)
    normal.paragraph_format.line_spacing=1.2
    normal.paragraph_format.space_after=Pt(7)
    for name,size in [('Title',21),('Heading 1',14),('Heading 2',12)]:
        style=doc.styles[name];style.font.name='Arial';style.font.size=Pt(size)
        style.font.color.rgb=RGBColor(0,0,0);style.font.underline=False
        style.paragraph_format.space_before=Pt(12 if name!='Title' else 0)
        style.paragraph_format.space_after=Pt(6)
        style.paragraph_format.keep_with_next=True
        style.element.rPr.rFonts.set(qn('w:ascii'),'Arial')
        style.element.rPr.rFonts.set(qn('w:hAnsi'),'Arial')
        for attr in ['asciiTheme','hAnsiTheme','eastAsiaTheme','cstheme']:
            style.element.rPr.rFonts.attrib.pop(qn('w:'+attr),None)
        for border in list(style.element.iter(qn('w:pBdr'))):border.getparent().remove(border)
        # Explicit black removes the theme colour as well.
        color=style.element.rPr.find(qn('w:color'))
        if color is not None:
            for attr in ['themeColor','themeTint','themeShade']:color.attrib.pop(qn('w:'+attr),None)
    url,sources=source_links(record)
    def link(paragraph,label,target):
        rel=paragraph.part.relate_to(target,RELATIONSHIP_TYPE.HYPERLINK,is_external=True)
        hyper=OxmlElement('w:hyperlink');hyper.set(qn('r:id'),rel)
        run=OxmlElement('w:r');props=OxmlElement('w:rPr')
        color=OxmlElement('w:color');color.set(qn('w:val'),'245E45');props.append(color)
        run.append(props);text=OxmlElement('w:t');text.text=label;run.append(text);hyper.append(run);paragraph._p.append(hyper)
    def content(paragraph,text):
        for kind,value,target in inlines(text,sources):
            if kind=='link':link(paragraph,value,target)
            else:
                run=paragraph.add_run(value)
                if kind=='bold':run.bold=True
                if kind=='code':run.font.name='Consolas';run.font.size=Pt(10)
    doc.add_paragraph(heading(record['title'])+'\nStudy Notes',style='Title')
    intro=doc.add_paragraph(caption_basis(record));intro.paragraph_format.space_after=Pt(5)
    p=doc.add_paragraph();link(p,'Watch the source tutorial',url)
    for block in blocks(record['answer']):
        if block.kind=='heading':doc.add_paragraph(heading(block.text),style='Heading 1')
        elif block.kind=='code':
            p=doc.add_paragraph();p.paragraph_format.left_indent=Inches(.15)
            p.paragraph_format.space_before=Pt(4);p.paragraph_format.space_after=Pt(9)
            p.paragraph_format.keep_together=True;p.paragraph_format.line_spacing=1.1
            run=p.add_run(block.text);run.font.name='Consolas';run.font.size=Pt(9.5)
        else:
            p=doc.add_paragraph(style={'bullet':'List Bullet','number':'List Number'}.get(block.kind,'Normal'))
            content(p,block.text)
    doc.add_paragraph('Video References',style='Heading 1')
    p=doc.add_paragraph()
    for index,identifier in enumerate(dict.fromkeys(record['sources'])):
        if identifier not in sources:continue
        if index:p.add_run('   ')
        label,target=sources[identifier];link(p,label,target)
    footer=section.footer.paragraphs[0];footer.alignment=WD_ALIGN_PARAGRAPH.RIGHT
    footer.add_run('Page ').font.size=Pt(8)
    field=OxmlElement('w:fldSimple');field.set(qn('w:instr'),'PAGE')
    field_run=OxmlElement('w:r');field_props=OxmlElement('w:rPr');size=OxmlElement('w:sz');size.set(qn('w:val'),'16');field_props.append(size);field_run.append(field_props);placeholder=OxmlElement('w:t');placeholder.text='1';field_run.append(placeholder);field.append(field_run);footer._p.append(field)
    doc.core_properties.title=heading(record['title'])+' Study Notes'
    doc.core_properties.author='LessonTrace';doc.core_properties.last_modified_by='LessonTrace'
    doc.core_properties.comments=''
    output=BytesIO();doc.save(output);return output.getvalue()


def _pdf_fonts():
    from reportlab import __file__ as package_file
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    with _fonts_lock:
        if 'LessonTraceBody' not in pdfmetrics.getRegisteredFontNames():
            bundled=Path(package_file).parent/'fonts'
            for name,system,fallback in [('LessonTraceBody','arial.ttf','Vera.ttf'),('LessonTraceBold','arialbd.ttf','VeraBd.ttf'),('LessonTraceCode','consola.ttf','Vera.ttf')]:
                path=Path('C:/Windows/Fonts')/system
                pdfmetrics.registerFont(TTFont(name,str(path if path.is_file() else bundled/fallback)))
            pdfmetrics.registerFontFamily('LessonTraceBody',normal='LessonTraceBody',bold='LessonTraceBold')
    return 'LessonTraceBody','LessonTraceBold','LessonTraceCode'


def _pdf(record):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Preformatted,Spacer
    body,bold,mono=_pdf_fonts()
    styles={
        'body':ParagraphStyle('body',fontName=body,fontSize=10.5,leading=15,spaceAfter=7,alignment=TA_LEFT),
        'title':ParagraphStyle('title',fontName=bold,fontSize=23,leading=28,spaceAfter=12,textColor=colors.black,keepWithNext=True),
        'heading':ParagraphStyle('heading',fontName=bold,fontSize=14,leading=18,spaceBefore=12,spaceAfter=6,textColor=colors.black,keepWithNext=True),
        'code':ParagraphStyle('code',fontName=mono,fontSize=9,leading=12,leftIndent=10,rightIndent=8,spaceBefore=4,spaceAfter=9),
        'list':ParagraphStyle('list',fontName=body,fontSize=10.5,leading=15,leftIndent=16,bulletIndent=3,spaceAfter=5),
    }
    url,sources=source_links(record)
    def rich(text):
        output=[]
        for kind,value,target in inlines(text,sources):
            escaped=escape(value)
            if kind=='bold':escaped='<b>'+escaped+'</b>'
            elif kind=='code':escaped='<font name="'+mono+'">'+escaped+'</font>'
            elif kind=='link':escaped='<link href="'+escape(target,{'"':'&quot;'})+'" color="#245E45">'+escaped+'</link>'
            output.append(escaped)
        return ''.join(output)
    output=BytesIO()
    document=SimpleDocTemplate(output,pagesize=A4,rightMargin=50,leftMargin=50,topMargin=43,bottomMargin=43,title=heading(record['title'])+' Study Notes',author='LessonTrace')
    story=[Paragraph(escape(heading(record['title']))+'<br/>Study Notes',styles['title']),Paragraph(escape(caption_basis(record)),styles['body']),Paragraph('<link href="'+url.replace('&','&amp;')+'" color="#245E45">Watch the source tutorial</link>',styles['body'])]
    for block in blocks(record['answer']):
        if block.kind=='heading':story.append(Paragraph(escape(heading(block.text)),styles['heading']))
        elif block.kind=='code':story.append(Preformatted(block.text,styles['code'],maxLineLength=88,newLineChars='    '))
        else:story.append(Paragraph(rich(block.text),styles['list'] if block.kind in {'bullet','number'} else styles['body'],bulletText='•' if block.kind=='bullet' else str(block.number)+'.' if block.kind=='number' else None))
    refs=[]
    for identifier in dict.fromkeys(record['sources']):
        if identifier in sources:
            label,target=sources[identifier];refs.append('<link href="'+target.replace('&','&amp;')+'" color="#245E45">'+label+'</link>')
    story.append(Paragraph('<b>Video references:</b> '+' &nbsp; '.join(refs),styles['body']))
    def page(canvas,doc):
        canvas.saveState();canvas.setFont(body,8);canvas.drawRightString(A4[0]-50,24,'Page '+str(doc.page));canvas.restoreState()
    document.build(story,onFirstPage=page,onLaterPages=page)
    return output.getvalue()


def export_notes(record,format):
    if format not in MIME_TYPES:raise ValueError('Choose PDF, Word or Markdown.')
    name=re.sub(r'[^a-z0-9]+','-',record['title'].lower()).strip('-')[:75] or 'lessontrace'
    body=markdown(record).encode('utf-8') if format=='md' else _docx(record) if format=='docx' else _pdf(record)
    return body,name+'-notes.'+format,MIME_TYPES[format]

"""Local-only answer-key review, corrections, and explicit source verification."""
from __future__ import annotations
import json
import secrets
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib.parse import parse_qs, urlparse
from .settings import ROOT

HTML = r'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>OMR · Key review</title>
<style>body{font:16px system-ui;background:#f4f6f8;color:#182235;margin:0}header{background:#152b42;color:white;padding:24px 5vw}main{max-width:1280px;margin:24px auto;padding:0 20px}select,input,button{font:inherit;padding:10px;border:1px solid #c3cbd5;border-radius:6px}button{background:#17665c;color:white;cursor:pointer}button:disabled{opacity:.45;cursor:wait}.bar{display:flex;gap:12px;flex-wrap:wrap;align-items:center}.notice{padding:16px;background:#fff0cf;border-radius:8px;margin:18px 0}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}.card{background:white;padding:12px;border:1px solid #d4dbe3;border-radius:8px}.card input{width:85px;margin-left:8px;text-transform:uppercase}.card img{max-width:100%;height:85px;object-fit:contain;display:block;margin:8px 0}.missing{border-color:#c14431}a{color:#17665c}#sources{display:flex;gap:18px;flex-wrap:wrap;margin:20px 0}#status{white-space:pre-wrap}footer{padding:28px 0}small{color:#526075}.sticky{position:sticky;bottom:0;background:#f4f6f8;padding:14px 0;border-top:1px solid #ccd4de}</style>
<header><strong>OMR / Answer-key review</strong><div>Compare printed question numbers and answers before enabling grading.</div></header><main><div class="bar"><label for="exam">Exam</label><select id="exam"></select><span id="summary"></span></div><div class="notice">OCR is a draft. Check the exam heading, all 100 question numbers, and every answer against the original pages. Enter BC when either B or C is accepted. Shading both bubbles on an OMR sheet still counts as wrong.</div><p id="status" role="status"></p><div id="sources"></div><div id="checks"></div><div id="cards" class="cards"></div><footer class="sticky"><div class="bar"><button id="save">Save draft</button><label>Reviewer <input id="reviewer" placeholder="Your name"></label><button id="verify">Verify all 100 answers</button></div><p><small>Verification enables final grading. Saving a draft disables grading until it is verified again.</small></p></footer></main>
<script>
const TOKEN=__TOKEN__; let exams=[],current;
const $=id=>document.getElementById(id);
async function request(url,options={}){const r=await fetch(url,{...options,headers:{'Content-Type':'application/json','X-Review-Token':TOKEN}});const data=await r.json();if(!r.ok)throw Error(data.error||'Request failed');return data}
function text(tag,value){const n=document.createElement(tag);n.textContent=value;return n}
async function load(){const data=await request('/api/keys');exams=data.exams; $('exam').replaceChildren(...exams.map(e=>{const o=text('option',e.name+' ['+e.collection+']');o.value=e.id;return o}));show()}
function show(){current=exams.find(e=>e.id===$('exam').value);$('status').textContent=(current.issues||[]).map(i=>typeof i==='string'?i:JSON.stringify(i)).join('\n');$('summary').textContent=Object.values(current.answers).filter(v=>v&&v.length).length+'/100 · '+current.status; const sources=current.sources||[];$('sources').replaceChildren(...sources.map((s,i)=>{let a=text('a','Open original '+(i+1)+': '+s);a.href='/source?exam='+encodeURIComponent(current.id)+'&index='+i;a.target='_blank';a.rel='noopener';return a}));$('checks').replaceChildren(...sources.map((s,i)=>{const label=document.createElement('label');label.style.display='block';const cb=document.createElement('input');cb.type='checkbox';cb.className='source-check';label.append(cb,document.createTextNode(' I checked the heading and answers in '+s));return label}));$('cards').replaceChildren(...Array.from({length:100},(_,i)=>{let n=i+1;let value=(current.answers[String(n)]||[]).join('');let card=document.createElement('div');card.className='card'+(!value?' missing':'');card.append(text('strong','Question '+n));let input=document.createElement('input');input.value=value;input.dataset.number=n;input.maxLength=4;input.setAttribute('aria-label','Accepted answers for question '+n);card.append(input);if(current.provenance&&current.provenance[String(n)]){const img=document.createElement('img');img.loading='lazy';img.alt='Printed source for question '+n;img.src='/crop?exam='+encodeURIComponent(current.id)+'&question='+n;card.append(img)}else card.append(text('p','No reliable crop — check original page.'));return card}));}
async function save(verify){try{const answers={};document.querySelectorAll('[data-number]').forEach(input=>{const value=input.value.trim().toUpperCase();if(value){if(!/^[ABCD]{1,4}$/.test(value)||new Set(value).size!==value.length)throw Error('Invalid answer at Q'+input.dataset.number);answers[input.dataset.number]=value.split('').sort()}});let reviewer=$('reviewer').value.trim();if(verify&&(!reviewer||![...document.querySelectorAll('.source-check')].every(c=>c.checked)))throw Error('Enter your name and check every source page first.');const result=await request('/api/save',{method:'POST',body:JSON.stringify({id:current.id,answers,verify,reviewer,revision:current.revision||0})});const selected=current.id;await load();$('exam').value=selected;show();$('status').textContent=result.message}catch(e){$('status').textContent=e.message}}
$('exam').onchange=show;$('save').onclick=()=>save(false);$('verify').onclick=()=>save(true);load().catch(e=>$('status').textContent=e.message);
</script></html>'''


def serve(file:Path,port:int=8765):
    token=secrets.token_urlsafe(32)
    write_lock=Lock()
    sources=ROOT/'omr-check-answer-sheet-images'
    def read():return json.loads(file.read_text(encoding='utf-8'))
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,status,body,content_type='application/json'):
            if not isinstance(body,bytes): body=json.dumps(body).encode('utf-8')
            self.send_response(status);self.send_header('Content-Type',content_type);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('X-Frame-Options','DENY');self.end_headers();self.wfile.write(body)
        def do_GET(self):
            if self.headers.get('Host') not in (f'127.0.0.1:{port}',f'localhost:{port}'):
                return self.reply(403,{'error':'Invalid host'})
            parsed=urlparse(self.path);query=parse_qs(parsed.query)
            if parsed.path=='/':return self.reply(200,HTML.replace('__TOKEN__',json.dumps(token)).encode('utf-8'),'text/html; charset=utf-8')
            data=read()
            if parsed.path=='/api/keys':
                if self.headers.get('X-Review-Token')!=token:return self.reply(403,{'error':'Invalid review token'})
                return self.reply(200,data)
            if parsed.path in ('/source','/crop'):
                try:
                    exam=next(e for e in data['exams'] if e['id']==query['exam'][0])
                    if parsed.path=='/source':
                        name=exam['sources'][int(query['index'][0])]
                        if Path(name).name!=name:raise ValueError()
                        return self.reply(200,(sources/name).read_bytes(),'image/jpeg')
                    from PIL import Image,ImageOps,ImageDraw
                    from io import BytesIO
                    evidence=exam.get('provenance',{})[query['question'][0]]
                    name=evidence['source']
                    if Path(name).name!=name:raise ValueError()
                    with Image.open(sources/name) as image:
                        image=ImageOps.exif_transpose(image).convert('RGB')
                        a=evidence['number_box'];b=evidence['box'];x0=max(0,min(a[0],b[0])-4);y0=max(0,min(a[1],b[1])-4);x1=min(image.width,max(a[0]+a[2],b[0]+b[2])+4);y1=min(image.height,max(a[1]+a[3],b[1]+b[3])+4)
                        crop=image.crop((x0,y0,x1,y1));crop.thumbnail((500,180));output=BytesIO();crop.save(output,format='JPEG')
                        return self.reply(200,output.getvalue(),'image/jpeg')
                except (KeyError,IndexError,StopIteration,ValueError,OSError):return self.reply(404,{'error':'Source not available'})
            self.reply(404,{'error':'Not found'})
        def do_POST(self):
            with write_lock:
                self.save_key()
        def save_key(self):
            if self.headers.get('Host') not in (f'127.0.0.1:{port}',f'localhost:{port}'):
                return self.reply(403,{'error':'Invalid host'})
            if self.path!='/api/save':return self.reply(404,{'error':'Not found'})
            if self.headers.get('X-Review-Token')!=token:return self.reply(403,{'error':'Invalid review token'})
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<100_000:raise ValueError('Invalid request size')
                body=json.loads(self.rfile.read(size));data=read();exam=next(e for e in data['exams'] if e['id']==body['id'])
                if body.get('revision')!=exam.get('revision',0):return self.reply(409,{'error':'This key changed. Reload the page before saving.'})
                answers=body['answers']
                if not isinstance(answers,dict):raise ValueError('Invalid answers')
                for n,values in answers.items():
                    if str(int(n))!=n or not 1<=int(n)<=100 or not isinstance(values,list) or not values or any(c not in ('A','B','C','D') for c in values) or len(set(values))!=len(values):raise ValueError('Invalid answer entry')
                verify=body.get('verify') is True
                if verify and (set(answers)!=set(map(str,range(1,101))) or not body.get('reviewer','').strip()):raise ValueError('All 100 answers and a reviewer name are required')
                backup=file.with_name(file.stem+'.before-review.json')
                backup.write_bytes(file.read_bytes())
                exam['answers']=answers;exam['status']='verified' if verify else 'draft';exam['revision']=exam.get('revision',0)+1
                exam['issues']=[] if verify else ['Awaiting complete source verification']
                exam['review']={'reviewer':body.get('reviewer',''),'verified':verify,'at':datetime.now(timezone.utc).isoformat()}
                temporary=file.with_suffix('.tmp');temporary.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8');temporary.replace(file)
                self.reply(200,{'message':'Key verified; grading is enabled.' if verify else 'Draft saved; grading remains disabled.'})
            except (ValueError,KeyError,TypeError,StopIteration) as exc:self.reply(400,{'error':str(exc)})
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    print(f'Key review: http://127.0.0.1:{port} (local computer only)',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()

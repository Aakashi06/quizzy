import json, sqlite3, secrets, hashlib, os, datetime, urllib.request, urllib.error, urllib.parse, re, base64, io, zipfile, xml.etree.ElementTree as ET
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / 'data/quizzy.db'
SESSIONS = {}
def connection():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; return c
with connection() as c:
    c.executescript('''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,name TEXT,email TEXT UNIQUE,password TEXT,salt TEXT); CREATE TABLE IF NOT EXISTS quizzes(id INTEGER PRIMARY KEY,user_id INTEGER,title TEXT,questions TEXT,created TEXT); CREATE TABLE IF NOT EXISTS attempts(id INTEGER PRIMARY KEY,user_id INTEGER,quiz_id INTEGER,answers TEXT,correct INTEGER,total INTEGER,created TEXT,day TEXT); CREATE UNIQUE INDEX IF NOT EXISTS one_submission ON attempts(user_id,quiz_id);''')
BANK = json.loads((ROOT/'data/questions.json').read_text())
def digest(password,salt): return hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
def validate(qs, count, context=None):
    if not isinstance(qs,list) or len(qs)!=count: raise ValueError('The model returned the wrong number of questions. Please try again.')
    seen=set()
    for q in qs:
        if not isinstance(q,dict) or not isinstance(q.get('question'),str) or not q['question'].strip(): raise ValueError('Invalid question text.')
        key=q['question'].strip().lower()
        if key in seen: raise ValueError('Duplicate questions returned. Please try again.')
        seen.add(key)
        opts=q.get('options',[])
        if len(opts)!=4 or any(not isinstance(x,str) or not x.strip() for x in opts) or len({x.strip().lower() for x in opts})!=4: raise ValueError('Questions must have four distinct options.')
        if type(q.get('correct_option')) is not int or q['correct_option'] not in range(4): raise ValueError('Invalid answer key.')
        if q.get('difficulty') not in ['easy','medium','hard'] or not q.get('explanation') or not q.get('source_excerpt'): raise ValueError('Missing explanation or evidence.')
        if context and q['source_excerpt'].lower() not in context.lower(): raise ValueError('A question had evidence that was not in the notes. Please try again.')
    return qs
class Handler(BaseHTTPRequestHandler):
    def send(self,data,status=200):
        raw=json.dumps(data).encode(); self.send_response(status); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def user(self):
        cookie=self.headers.get('Cookie',''); token=next((x.strip()[8:] for x in cookie.split(';') if x.strip().startswith('session=')),None)
        uid=SESSIONS.get(token)
        if not uid: raise PermissionError('Please sign in to continue.')
        with connection() as c: return dict(c.execute('SELECT id,name,email FROM users WHERE id=?',(uid,)).fetchone())
    def do_GET(self):
        if not self.path.startswith('/api/'):
            path=ROOT/'frontend'/('index.html' if self.path.split('?')[0]=='/' else self.path.split('?')[0].lstrip('/'))
            if path.resolve().parent!= (ROOT/'frontend').resolve() or not path.is_file(): self.send_error(404); return
            raw=path.read_bytes(); self.send_response(200); self.send_header('Content-Type', 'text/html' if path.suffix=='.html' else 'text/css' if path.suffix=='.css' else 'text/javascript'); self.end_headers(); self.wfile.write(raw); return
        try:
            u=self.user()
            if self.path=='/api/me': return self.send(u)
            if self.path.split('?')[0]=='/api/overview':
                with connection() as c:
                    attempts=[dict(r) for r in c.execute('SELECT a.*,q.title,q.questions FROM attempts a JOIN quizzes q ON q.id=a.quiz_id WHERE a.user_id=? ORDER BY a.id DESC',(u['id'],))]
                activity={}; topics={t:[] for t in BANK}; total=correct=0
                for a in reversed(attempts):
                    total+=a['total']; correct+=a['correct']; activity[a['day']]=activity.get(a['day'],0)+a['total']
                    for q,ans in zip(json.loads(a['questions']),json.loads(a['answers'])): topics.setdefault(q['topic'],[]).append(int(ans==q['correct_option']))
                scores=[]
                for t,values in topics.items():
                    recent=values[-40:]; weights=list(range(1,len(recent)+1)); score=round(sum(v*w for v,w in zip(recent,weights))/sum(weights)*100) if recent else 0
                    scores.append({'topic':t,'score':score,'count':len(values),'label':'Not enough data' if len(values)<5 else 'Strong' if score>=80 else 'Improving' if score>=50 else 'Needs practice'})
                params=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                try: today=datetime.date.fromisoformat(params.get('day',[datetime.date.today().isoformat()])[0])
                except ValueError: today=datetime.date.today()
                streak=0; d=today if today.isoformat() in activity else today-datetime.timedelta(days=1)
                while d.isoformat() in activity: streak+=1; d-=datetime.timedelta(days=1)
                history=[{k:a[k] for k in ('id','title','correct','total','day')} for a in attempts[:8]]
                return self.send({'user':u,'total':total,'correct':correct,'accuracy':round(correct/total*100) if total else 0,'streak':streak,'active_days':len(activity),'activity':activity,'topics':scores,'history':history,'quizzes':len(attempts)})
            match=re.fullmatch(r'/api/quizzes/(\d+)',self.path)
            if match:
                with connection() as c: q=c.execute('SELECT * FROM quizzes WHERE id=? AND user_id=?',(match[1],u['id'])).fetchone()
                if not q: return self.send({'error':'Quiz not found'},404)
                questions=json.loads(q['questions']); return self.send({'id':q['id'],'title':q['title'],'questions':[{'id':i,'question':x['question'],'options':x['options'],'topic':x['topic'],'difficulty':x['difficulty']} for i,x in enumerate(questions)]})
            self.send({'error':'Not found'},404)
        except PermissionError as e: self.send({'error':str(e)},401)
    def do_POST(self):
        try:
            if self.headers.get('Sec-Fetch-Site')=='cross-site': return self.send({'error':'Cross-site requests are not allowed'},403)
            length=int(self.headers.get('Content-Length',0))
            if length>8_000_000: return self.send({'error':'Upload limit is 5 MB.'},413)
            body=json.loads(self.rfile.read(length))
            if self.path in ['/api/register','/api/login']:
                email=body.get('email','').strip().lower(); password=body.get('password','')
                if '@' not in email or len(password)<8: raise ValueError('Use a valid email and a password with at least 8 characters.')
                with connection() as c:
                    if self.path=='/api/register':
                        name=body.get('name','').strip()[:80]
                        if not name: raise ValueError('Please enter your name.')
                        salt=secrets.token_hex(16)
                        try: c.execute('INSERT INTO users(name,email,password,salt) VALUES(?,?,?,?)',(name,email,digest(password,salt),salt))
                        except sqlite3.IntegrityError: raise ValueError('This email already has an account. Sign in instead.')
                    user=c.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
                if not user or not secrets.compare_digest(user['password'],digest(password,user['salt'])): return self.send({'error':'Email or password is incorrect'},401)
                token=secrets.token_urlsafe(32); SESSIONS[token]=user['id']; raw=json.dumps({'id':user['id'],'name':user['name'],'email':user['email']}).encode(); self.send_response(200); self.send_header('Set-Cookie',f'session={token}; HttpOnly; SameSite=Strict; Path=/'); self.send_header('Content-Type','application/json'); self.end_headers(); self.wfile.write(raw); return
            u=self.user()
            if self.path=='/api/logout':
                for token,uid in list(SESSIONS.items()):
                    if uid==u['id']: del SESSIONS[token]
                return self.send({'ok':True})
            if self.path=='/api/documents/extract':
                filename=body.get('filename',''); suffix=Path(filename).suffix.lower()
                if suffix not in ['.txt','.pdf','.docx']: raise ValueError('Choose a PDF, DOCX, or TXT file.')
                try: raw=base64.b64decode(body.get('content',''),validate=True)
                except Exception: raise ValueError('Could not read the uploaded file.')
                if len(raw)>5_000_000: raise ValueError('Choose a file under 5 MB.')
                if suffix=='.txt':
                    try: text=raw.decode('utf-8-sig')
                    except UnicodeDecodeError: raise ValueError('Please save your TXT file with UTF-8 encoding.')
                elif suffix=='.docx':
                    try:
                        with zipfile.ZipFile(io.BytesIO(raw)) as z:
                            if sum(i.file_size for i in z.infolist())>20_000_000: raise ValueError('This document expands beyond the extraction limit.')
                            root=ET.fromstring(z.read('word/document.xml'))
                            text='\n'.join(''.join(p.itertext()) for p in root.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p'))
                    except (zipfile.BadZipFile,KeyError,ET.ParseError): raise ValueError('This file could not be read as a DOCX document.')
                else:
                    try:
                        from pypdf import PdfReader
                        reader=PdfReader(io.BytesIO(raw))
                        if reader.is_encrypted: raise ValueError('Upload a PDF without password protection.')
                        if len(reader.pages)>100: raise ValueError('Choose a PDF with at most 100 pages.')
                        text='\n'.join(p.extract_text() or '' for p in reader.pages)
                    except ImportError: raise ValueError('PDF support requires pypdf. Start Quizzy using .venv/bin/python backend/server.py.')
                    except ValueError: raise
                    except Exception: raise ValueError('This PDF could not be read. Try a text-based PDF, DOCX, or TXT file.')
                if not text.strip(): raise ValueError('No text was found. Scanned images need OCR; use a text-based document or paste notes.')
                return self.send({'text':text[:24000],'filename':filename,'truncated':len(text)>24000})
            if self.path=='/api/generate':
                topic=body.get('topic','Motion'); count=int(body.get('count',5)); difficulty=body.get('difficulty','easy'); mode=body.get('mode','curriculum')
                if count not in [5,10,15,25] or topic not in BANK or difficulty not in ['mixed','easy','medium','hard']: raise ValueError('Invalid quiz configuration.')
                if mode=='curriculum':
                    pool=BANK[topic]; filtered=[q for q in pool if difficulty=='mixed' or q['difficulty']==difficulty]
                    if len(filtered)<count: raise ValueError('Not enough questions available for this configuration.')
                    import random
                    qs=[]
                    for original in random.sample(filtered,count):
                        q=dict(original); order=random.sample(range(4),4)
                        q['options']=[original['options'][i] for i in order]; q['correct_option']=order.index(original['correct_option']); qs.append(q)
                    title=topic
                else:
                    context=body.get('notes','').strip()[:24000]
                    if len(context)<100: raise ValueError('Add at least 100 characters of chapter notes.')
                    prompt=f'Create exactly {count} school science MCQs grounded ONLY in these notes. Return JSON object with questions array. Each question must have question, options (4 distinct strings), correct_option (integer 0-3), explanation, difficulty (easy/medium/hard), topic, source_excerpt (exact quote from notes). Difficulty: {difficulty}. Notes:\n{context}'
                    request=urllib.request.Request(os.environ.get('OLLAMA_URL','http://localhost:11434')+'/api/generate',data=json.dumps({'model':os.environ.get('OLLAMA_MODEL','qwen3:4b'),'prompt':prompt,'format':'json','stream':False}).encode(),headers={'Content-Type':'application/json'})
                    try:
                        with urllib.request.urlopen(request,timeout=120) as res: payload=json.loads(res.read())
                        qs=validate(json.loads(payload['response'])['questions'],count,context)
                    except (urllib.error.URLError,TimeoutError): raise ValueError('Ollama is unavailable. Start Ollama with qwen3:4b, or choose a curriculum quiz.')
                    for q in qs:
                        if difficulty!='mixed' and q['difficulty']!=difficulty: raise ValueError('The model did not follow the selected difficulty. Please try again.')
                        q['topic']=topic
                    title=(body.get('filename') or 'Uploaded notes')[:100]
                validate(qs,count)
                with connection() as c: cur=c.execute('INSERT INTO quizzes(user_id,title,questions,created) VALUES(?,?,?,?)',(u['id'],title,json.dumps(qs),datetime.datetime.now().isoformat())); qid=cur.lastrowid
                return self.send({'id':qid})
            match=re.fullmatch(r'/api/quizzes/(\d+)/submit',self.path)
            if match:
                with connection() as c:
                    c.execute('BEGIN IMMEDIATE')
                    quiz=c.execute('SELECT * FROM quizzes WHERE id=? AND user_id=?',(match[1],u['id'])).fetchone()
                    if not quiz: return self.send({'error':'Quiz not found'},404)
                    qs=json.loads(quiz['questions']); answers=body.get('answers',[])
                    if len(answers)!=len(qs) or any(type(a) is not int or a not in range(4) for a in answers): raise ValueError('Answer every question before submitting.')
                    if c.execute('SELECT id FROM attempts WHERE user_id=? AND quiz_id=?',(u['id'],quiz['id'])).fetchone(): raise ValueError('This quiz has already been submitted.')
                    score=sum(a==q['correct_option'] for a,q in zip(answers,qs)); day=body.get('day','')
                    datetime.date.fromisoformat(day)
                    c.execute('INSERT INTO attempts(user_id,quiz_id,answers,correct,total,created,day) VALUES(?,?,?,?,?,?,?)',(u['id'],quiz['id'],json.dumps(answers),score,len(qs),datetime.datetime.now().isoformat(),day))
                return self.send({'correct':score,'total':len(qs),'questions':qs,'answers':answers,'title':quiz['title']})
            self.send({'error':'Not found'},404)
        except PermissionError as e: self.send({'error':str(e)},401)
        except (ValueError,KeyError,TypeError) as e: self.send({'error':str(e)},400)
        except Exception: self.send({'error':'Something went wrong. Please try again.'},500)
if __name__=='__main__':
    port=int(os.environ.get('PORT','8000'))
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    print(f'Quizzy running at http://localhost:{port}',flush=True)
    server.serve_forever()

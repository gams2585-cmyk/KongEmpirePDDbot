import os,json,time,sqlite3,urllib.request,urllib.error,uuid,logging,hashlib
from pathlib import Path
ROOT=Path(__file__).parent
CATEGORIES={'sentence':'📝 Sentence · Текстовые вопросы','picture':'🖼 Picture · Фотографии','illustration':'🎨 Illustration · Иллюстрации','sign':'🚸 Safety Sign · Дорожные знаки','video':'▶️ Video · Видео'}
TOTALS={'sentence':97,'picture':100,'illustration':85,'sign':100,'video':35}
LEGACY={'sign1':('sign',0),'sign2':('sign',99),'sentence2':('sentence',0)}
def merge_lessons(source):
 result={k:dict(source.get(k,{})) for k in CATEGORIES}
 for old,(new,offset) in LEGACY.items():
  for number,item in source.get(old,{}).items():
   result[new].setdefault(str(int(number)+offset),item)
 return result

class TelegramError(Exception):
 def __init__(self,method,code,description='',retry_after=0):
  self.method=method;self.code=code;self.retry_after=retry_after
  # Only fixed diagnostic labels are logged, never arbitrary API response text.
  labels={"query is too old":"expired_callback", "query id is invalid":"expired_callback", "file identifier":"invalid_file_id", "file_id":"invalid_file_id", "can't parse entities":"invalid_html", "message is too long":"message_too_long", "photo":"photo_rejected", "blocked":"bot_blocked", "chat not found":"chat_not_found", "conflict":"another_bot_instance", "unauthorized":"invalid_token"}
  self.reason=next((v for k,v in labels.items() if k in description.lower()),'api_rejected')
  super().__init__(f'{method}: HTTP {code} ({self.reason})')

class Bot:
 def __init__(self,token,admin,dbpath):
  self.token=token;self.admin=int(admin);Path(dbpath).parent.mkdir(parents=True,exist_ok=True)
  self.db=sqlite3.connect(dbpath)
  self.db.executescript('CREATE TABLE IF NOT EXISTS access(uid INTEGER PRIMARY KEY);CREATE TABLE IF NOT EXISTS progress(uid INTEGER PRIMARY KEY,category TEXT,number INTEGER);CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value INTEGER);CREATE TABLE IF NOT EXISTS selection(uid INTEGER PRIMARY KEY,category TEXT);')
  self.db.execute('CREATE TABLE IF NOT EXISTS photo_cache(key TEXT PRIMARY KEY,file_id TEXT)')
  self.lessons=merge_lessons(json.loads((ROOT/'lessons.json').read_text()))
  with self.db:
   for old,(new,offset) in LEGACY.items():
    self.db.execute('UPDATE progress SET category=?,number=number+? WHERE category=?',(new,offset,old))
    self.db.execute('UPDATE selection SET category=? WHERE category=?',(new,old))
 def api(self,method,data):
  data=dict(data)
  if method=='sendPhoto' and isinstance(data.get('photo'),Path):
   photo=data.pop('photo');boundary=uuid.uuid4().hex;parts=[]
   for k,v in data.items():
    if isinstance(v,(dict,list,bool)):v=json.dumps(v)
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
   parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="lesson.png"\r\nContent-Type: image/png\r\n\r\n'.encode()+photo.read_bytes()+b'\r\n')
   body=b''.join(parts)+f'--{boundary}--\r\n'.encode();ctype='multipart/form-data; boundary='+boundary
  else:body=json.dumps(data).encode();ctype='application/json'
  req=urllib.request.Request('https://api.telegram.org/bot'+self.token+'/'+method,data=body,headers={'Content-Type':ctype})
  try:
   with urllib.request.urlopen(req,timeout=45) as r:result=json.load(r)
  except urllib.error.HTTPError as exc:
   try:result=json.loads(exc.read())
   except (ValueError,UnicodeError):result={}
   raise TelegramError(method,exc.code,result.get('description',''),result.get('parameters',{}).get('retry_after',0)) from None
  if not result.get('ok'):raise TelegramError(method,result.get('error_code',0),result.get('description',''),result.get('parameters',{}).get('retry_after',0))
  return result['result']
 def send(self,uid,text,rows=None):
  data={'chat_id':uid,'text':text,'parse_mode':'HTML','protect_content':uid != self.admin}
  if rows:data['reply_markup']={'inline_keyboard':[[{'text':t,'callback_data':d} for t,d in row] for row in rows]}
  return self.api('sendMessage',data)
 def allowed(self,uid):return uid==self.admin or bool(self.db.execute('SELECT 1 FROM access WHERE uid=?',(uid,)).fetchone())
 def menu(self,uid):self.send(uid,'<b>ПДД Корея | Kong Empire</b>\nВыбери раздел. Открывай доступные уроки.',[[(f'{v} · {TOTALS[k]} вопросов','cat:'+k)] for k,v in CATEGORIES.items()])
 def category(self,uid,cat):
  if cat not in CATEGORIES:return
  available=self.lessons.get(cat,{})
  if not available:return self.send(uid,CATEGORIES[cat]+f'\nВ разделе будет {TOTALS[cat]} вопросов. Уроки пока готовятся.',[[('🏠 Главное меню','menu')]])
  self.send(uid,CATEGORIES[cat]+f'\nДобавлено уроков: {len(available)} из {TOTALS[cat]}.',[[('Начать с вопроса 1','q:'+cat+':1')],[('Продолжить обучение','resume:'+cat)],[('🔢 Выбрать номер вопроса','pick:'+cat)],[('🏠 Главное меню','menu')]])
 def lesson(self,uid,cat,n):
  item=self.lessons.get(cat,{}).get(str(n))
  if not item:return self.send(uid,'Этот вопрос ещё не добавлен.',[[('⬅️ К разделу','cat:'+cat)]])
  photo=ROOT/item['image']
  if not photo.is_file():
   logging.error('lesson category=%s number=%s reason=missing_image',cat,n)
   return self.send(uid,'Картинка этого вопроса пока недоступна. Попробуйте другой номер.')
  key=hashlib.sha256(self.token.encode()+photo.read_bytes()).hexdigest()
  cached=self.db.execute('SELECT file_id FROM photo_cache WHERE key=?',(key,)).fetchone()
  data={'chat_id':uid,'photo':cached[0] if cached else photo,'caption':f'{CATEGORIES[cat]} · Вопрос {n:02d}','protect_content':uid != self.admin}
  try:sent=self.api('sendPhoto',data)
  except TelegramError as exc:
   if not cached or exc.code!=400 or exc.reason not in ('invalid_file_id','photo_rejected'):raise
   with self.db:self.db.execute('DELETE FROM photo_cache WHERE key=?',(key,))
   data['photo']=photo;sent=self.api('sendPhoto',data)
  if sent.get('photo'):
   with self.db:self.db.execute('INSERT OR REPLACE INTO photo_cache VALUES(?,?)',(key,sent['photo'][-1]['file_id']))
  rows=[];ar=[]
  if str(n-1) in self.lessons[cat]:ar.append(('⬅️ Предыдущий',f'q:{cat}:{n-1}'))
  if str(n+1) in self.lessons[cat]:ar.append(('Следующий ➡️',f'q:{cat}:{n+1}'))
  if ar:rows.append(ar)
  rows.extend([[('🔢 Выбрать вопрос','pick:'+cat)],[('⬅️ К разделу','cat:'+cat),('🏠 Меню','menu')]])
  self.send(uid,item['text'],rows)
  with self.db:self.db.execute('INSERT OR REPLACE INTO progress VALUES(?,?,?)',(uid,cat,n))
 def handle(self,update):
  cb=update.get('callback_query');msg=cb.get('message',{}) if cb else update.get('message',{})
  if not msg or msg.get('chat',{}).get('type')!='private':return
  uid=msg['chat']['id'];text=msg.get('text','')
  if cb:
   try:self.api('answerCallbackQuery',{'callback_query_id':cb['id']})
   except TelegramError as exc:
    if exc.code!=400 or exc.reason!='expired_callback':raise
    logging.warning('answerCallbackQuery: expired_callback; continuing action')
  if not cb and text=='/id':return self.send(uid,f'Твой Telegram ID: <code>{uid}</code>')
  if not cb and uid==self.admin and text.startswith(('/grant ','/revoke ')):
   try:target=int(text.split()[1]);assert target>0
   except (ValueError,IndexError,AssertionError):return self.send(uid,'Формат: /grant 123456 или /revoke 123456')
   grant=text.startswith('/grant ')
   with self.db:
    if grant:self.db.execute('INSERT OR IGNORE INTO access VALUES(?)',(target,))
    else:self.db.execute('DELETE FROM access WHERE uid=?',(target,))
   return self.send(uid,'Доступ выдан.' if grant else 'Доступ закрыт.')
  if not self.allowed(uid):return self.send(uid,'<b>Курс готовится к запуску.</b>\nДоступ пока закрыт.\nТвой ID: <code>'+str(uid)+'</code>')
  if not cb and text.isdigit():
   choice=self.db.execute('SELECT category FROM selection WHERE uid=?',(uid,)).fetchone()
   if choice:return self.lesson(uid,choice[0],int(text))
  data=cb.get('data','') if cb else text
  if data in ('menu','/start','/menu'):return self.menu(uid)
  parts=data.split(':')
  if len(parts)>1 and parts[1] in LEGACY:
   cat,offset=LEGACY[parts[1]];parts[1]=cat
   if len(parts)==3 and parts[0]=='q' and parts[2].isdigit():parts[2]=str(int(parts[2])+offset)
  if len(parts)==2 and parts[1] in CATEGORIES:
   action,cat=parts
   if action=='cat':return self.category(uid,cat)
   if action=='pick':
    with self.db:self.db.execute('INSERT OR REPLACE INTO selection VALUES(?,?)',(uid,cat))
    return self.send(uid,'Доступные номера: '+(', '.join(self.lessons.get(cat,{})) or 'пока нет')+'\nОтправь номер вопроса, например: <b>1</b>',[[('⬅️ Назад','cat:'+cat)]])
   if action=='resume':
    row=self.db.execute('SELECT number FROM progress WHERE uid=? AND category=?',(uid,cat)).fetchone()
    return self.lesson(uid,cat,row[0] if row else 1)
  if data.startswith('/question '):parts=['q']+data.split()[1:]
  if len(parts)==3 and parts[0]=='q' and parts[1] in CATEGORIES:
   try:n=int(parts[2])
   except ValueError:return self.send(uid,'Номер вопроса должен быть числом.')
   return self.lesson(uid,parts[1],n)
  return self.menu(uid)
 def log_failure(self,stage,exc):
  if isinstance(exc,TelegramError):
   logging.error('%s method=%s code=%s reason=%s',stage,exc.method,exc.code,exc.reason)
  else:logging.error('%s exception=%s',stage,type(exc).__name__)
 def poll_once(self):
  row=self.db.execute("SELECT value FROM meta WHERE key='offset'").fetchone()
  updates=self.api('getUpdates',{'offset':row[0] if row else 0,'timeout':30,'allowed_updates':['message','callback_query']})
  for update in updates:
   try:self.handle(update)
   except Exception as exc:
    self.log_failure('update_failed',exc)
    if isinstance(exc,TelegramError) and exc.code==429:
     time.sleep(min(max(exc.retry_after,1),60))
    # Do not resend a partly delivered lesson indefinitely. User can request it again.
    msg=update.get('message') or update.get('callback_query',{}).get('message',{})
    if msg.get('chat',{}).get('type')=='private' and not (isinstance(exc,TelegramError) and exc.code in (401,403,429)):
     try:self.send(msg['chat']['id'],'Не удалось открыть вопрос. Попробуйте другой номер или повторите запрос позже.')
     except Exception as notice_error:self.log_failure('notice_failed',notice_error)
   finally:
    with self.db:self.db.execute("INSERT OR REPLACE INTO meta VALUES('offset',?)",(update['update_id']+1,))
 def run(self):
  info=self.api('getWebhookInfo',{})
  if info.get('url'):raise RuntimeError('Webhook already configured; stop existing deployment first')
  logging.info('Bot started; polling enabled')
  while True:
   try:self.poll_once()
   except Exception as exc:
    self.log_failure('poll_failed',exc)
    delay=exc.retry_after if isinstance(exc,TelegramError) and exc.code==429 else 5
    time.sleep(min(max(delay,1),60))
if __name__=='__main__':
 logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
 token=os.environ.get('BOT_TOKEN');admin=os.environ.get('ADMIN_TELEGRAM_ID')
 if not token or not admin:raise SystemExit('Set BOT_TOKEN and ADMIN_TELEGRAM_ID in server secrets')
 Bot(token,admin,os.environ.get('DB_PATH','/data/bot.sqlite3')).run()

"""Daily conservative collection. Ambiguous candidates never become published records."""
import runpy
import calendar, concurrent.futures, hashlib, json, re, time, unicodedata
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit
import truststore
# Use the maintained OS certificate store, keeping hostname and chain verification.
truststore.inject_into_ssl()
import requests
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parent
PUBLIC=ROOT/'public'
CONTACT=runpy.run_path(str(ROOT/'contact_parser.py'))
EVENTS=runpy.run_path(str(ROOT/'official_events.py'))
JST=timezone(timedelta(hours=9))
FOOD=re.compile(r'飲食|レストラン|カフェ|喫茶|居酒屋|ラーメン|焼肉|焼き肉|寿司|鮨|パン|ベーカリー|スイーツ|菓子|点心|餃子|パフェ|ソフトクリーム|アイス|ヨーグルト|焼き鳥|やきとり|海鮮|そば|蕎麦|うどん|中華|イタリアン|ビストロ|バル|ケーキ|ドーナツ|ピザ|パスタ|食フェス|きのこ|牡蠣|コーヒー|珈琲|バー|食堂|グルメ|フード|物産展|焼き芋|ビール|ワイン|日本酒|カレー|おでん|団子')
NONFOOD=re.compile(r'パーソナルジム|フィットネス|体操教室|スポーツジム|美容クリニック|美容医療|アパレル|整体|(?:APT\s*ROOM)',re.I)
GEO=re.compile(r'札幌')
SOURCE_LIST=[
 ('札幌リスト','https://sapporo-list.info/open/'),
 ('札幌速報','https://sapporo-sokuho.com/archives/category/開店・閉店'),
 ('リビング札幌','https://mrs.living.jp/sapporo/newopen'),
 ('札幌ショップス','https://www.shopship.jp/sapporo/open-close/'),
 ('北3条広場','https://www.kita3jo-plaza.jp/event/'),
 ('チ・カ・ホ','https://www.sapporo-chikamichi.jp/event/'),
 ('札幌三越','https://www.mitsukoshi.mistore.jp/sapporo.html'),
 ('丸井今井','https://www.maruiimai.mistore.jp/sapporo.html'),
 ('サッポロファクトリー','https://sapporofactory.jp/event/'),
 ('焼き芋テラス','https://sapporo-yakiimoterrace.com/')]+EVENTS['SOURCES']
def norm(s): return re.sub(r'\s+','',unicodedata.normalize('NFKC',s or '')).lower()
def canonical(u):
 p=urlsplit(u);return urlunsplit((p.scheme,p.netloc,p.path.rstrip('/') or '/',p.query,''))
def key(r):return '|'.join(map(norm,[r['name'],r['type'],r['date']]))
def address_key(place):
 s=unicodedata.normalize('NFKC',place or '').translate(str.maketrans('一二三四五六七八九','123456789'))
 s=re.sub(r'〒?\d{3}-\d{4}|北海道','',s).strip()
 m=re.search(r'(札幌市[^区\s]+区[^\s]+)',s)
 return re.sub(r'丁目|番地?|号','-',m.group(1)).rstrip('-') if m else ''
def name_overlap(a,b):
 generic=r'北海道海鮮|個室居酒屋|焼き鳥食べ飲み放題'
 a=re.sub(generic,'',norm(a));b=re.sub(generic,'',norm(b))
 return any(a[i:i+4] in b for i in range(max(0,len(a)-3)))
def deduplicate(items):
 records={}
 for r in items:
  if NONFOOD.search(r.get('name','')):continue
  k=key(r)
  for previous,existing in records.items():
   same_event=existing['type']==r['type'] and existing['date']==r['date']
   same_address=bool(address_key(r.get('place'))) and address_key(existing.get('place'))==address_key(r.get('place'))
   same_url=canonical(existing.get('url',''))==canonical(r.get('url','')) and bool(r.get('url'))
   a,b=norm(existing['name']),norm(r['name'])
   if same_event and ((same_url and name_overlap(a,b)) or (same_address and name_overlap(a,b))):k=previous;break
  if k in records:
   old=records[k]
   # Keep original id and editorial description so saved notes remain attached.
   detailed=bool(re.search(r'/post-\d+|/open-close/[^/]+',r.get('url','')))
   merged={**old,**r} if detailed else {**r,**old}
   merged['id']=old['id']
   merged['text']=old.get('text',r.get('text',''))
   merged['genre']=old.get('genre',r.get('genre','飲食店'))
   merged['aliases']=list(dict.fromkeys(old.get('aliases',[])+r.get('aliases',[])+[r['id']]))
   records[k]=merged
  else:records[k]=dict(r)
 return list(records.values())
def shift(t,n):
 m=t.month-1+n;y=t.year+m//12;m=m%12+1
 return date(y,m,min(t.day,calendar.monthrange(y,m)[1]))
def in_sapporo(r):
 place=r.get("place","")
 if re.search(r"小樽市|石狩市|江別市|北広島市|千歳市|恵庭市|苫小牧市",place):return False
 return bool(GEO.search(place) or r.get("area") in ("札幌中心部","札幌市内・周辺","札幌市内（中心部以外）"))
def eligible(r,t):
 try: start=date.fromisoformat(r['date']);end=date.fromisoformat(r.get('end') or r['date'])
 except (KeyError,ValueError): return False
 return end>=start and start<=shift(t,1) and end>=shift(t,-1) and (r['type']!='閉店' or start>=t)
def get(u):
 for attempt in range(2):
  try:
   r=requests.get(u,timeout=(6,18),headers={'User-Agent':'SapporoGourmetRadar/1.0 (+public-news-summary)'})
   r.raise_for_status();r.encoding=r.apparent_encoding;return BeautifulSoup(r.text,'html.parser')
  except requests.RequestException:
   if attempt:raise
   time.sleep(1)
def date_value(s):
 m=re.search(r'(20\d{2})\s*[年/.-]\s*(\d{1,2})\s*[月/.-]\s*(\d{1,2})',s)
 if not m:return ''
 try:return date(*map(int,m.groups())).isoformat()
 except ValueError:return ''
def parse_page(soup,u,source,t):
 heading=soup.select_one('h1') or soup.select_one('title')
 title=heading.get_text(' ',strip=True) if heading else ''
 main=soup.select_one('article') or soup.select_one('main') or soup
 for n in main.select('nav,footer,header,aside,script:not([type="application/ld+json"]),style'):n.decompose()
 text=main.get_text(' ',strip=True)
 candidate={'name':title[:140],'url':u,'source':source,'first_seen':t.isoformat(),'reason':'店名・所在地・実施日を確定できない'}
 if NONFOOD.search(title):return None,{**candidate,'reason':'グルメ対象外'}
 # Category evidence must come from the headline, never related articles or sidebars.
 if not FOOD.search(title):return None,{**candidate,'reason':'見出しに飲食・グルメの根拠がないため要確認'}
 if not GEO.search(title+' '+text[:4000]):return None,candidate
 kind='リニューアル' if re.search('リニューアル',title) else '閉店' if '閉店' in title else '開店' if re.search('オープン|OPEN|開店',title,re.I) else 'イベント'
 # Publication timestamps are deliberately ignored. Dates must sit next to execution labels.
 fields={}
 for tr in main.select('tr'):
  cells=tr.select('th,td')
  if len(cells)>1:fields[cells[0].get_text(' ',strip=True)]=cells[1].get_text(' ',strip=True)
 for dt in main.select('dt'):
  dd=dt.find_next_sibling('dd')
  if dd:fields[dt.get_text(' ',strip=True)]=dd.get_text(' ',strip=True)
 execution=[]
 # Headline and labelled shop fields take priority over article prose.
 if re.search('開催|会期|オープン|OPEN|開店|閉店|リニューアル',title,re.I):execution.append(title)
 execution.extend(v for k,v in fields.items() if re.search('開催日|開催期間|会期|開店日|閉店日|オープン日',k))
 if not any(date_value(v) for v in execution):
  for p in main.select('p'):
   line=p.get_text(' ',strip=True)
   if re.search(r'開催日|開催期間|会期|オープン日|開店日|閉店日|20\d{2}年.{0,35}(?:オープン|OPEN|開店|閉店)',line,re.I):
    execution.append(line[:400])
 dates=list(dict.fromkeys(filter(None,[date_value(x) for line in execution for x in re.findall(r'20\d{2}\s*[年/.-]\s*\d{1,2}\s*[月/.-]\s*\d{1,2}(?:日)?',line)])))
 place=next((v for k,v in fields.items() if re.search('住所|所在地|会場|開催場所',k)),'')
 if not place:
  m=re.search(r'(?:住所|所在地|会場|開催場所)\s*[:：]?\s*(?:〒?[\d－-]+\s*)?((?:北海道)?(?:札幌|小樽|石狩|江別|北広島|千歳|恵庭|苫小牧)[^。]{2,100})',text)
  if m:place=m.group(1)
 if place and not GEO.search(place):return None,{**candidate,'reason':'所在地が対象地域外'}
 name=next((v for k,v in fields.items() if k in ('店名','店舗名','イベント名')),'')
 m=re.search(r'[『「]([^』」]{2,70})[』」]',title)
 if m:name=m.group(1)
 # Prefer machine-readable Event data, where the dates are explicitly event dates.
 for node in soup.select('script[type="application/ld+json"]'):
  try: obj=json.loads(node.string or node.get_text())
  except (ValueError,TypeError):continue
  def walk(o):
   if isinstance(o,list):
    for v in o:yield from walk(v)
   elif isinstance(o,dict):
    yield o
    for v in o.values():
     if isinstance(v,(dict,list)):yield from walk(v)
  for event in walk(obj):
   if 'Event' not in str(event.get('@type','')):continue
   loc=event.get('location',{});loc=loc if isinstance(loc,dict) else {}
   addr=loc.get('address',{});addr=addr if isinstance(addr,dict) else {}
   loc_text=' '.join(str(v) for v in [loc.get('name',''),addr.get('addressRegion',''),addr.get('addressLocality',''),addr.get('streetAddress','')])
   if not GEO.search(loc_text):continue
   name=event.get('name','');place=loc_text.strip();kind='イベント'
   dates=[str(event.get('startDate',''))[:10],str(event.get('endDate',event.get('startDate','')))[:10]]
 if not name or not place or not dates:return None,candidate
 r={'id':int(hashlib.sha256((norm(name)+norm(place)+kind).encode()).hexdigest()[:12],16),'name':name,'type':kind,'date':dates[0],'end':dates[-1] if kind=='イベント' else '', 'place':place,'area':area(place),'genre':'グルメイベント' if kind=='イベント' else '飲食店','text':f'{dates[0]}の{kind}情報。詳細は出典を確認してください。','url':u,'source':source,'official':False,'checked_at':t.isoformat()}
 contacts=CONTACT['extract'](main,u)
 if contacts:r['contacts']={**contacts,'checked_at':t.isoformat()}
 if not in_sapporo(r) or not eligible(r,t):return None,{**candidate,'reason':'掲載期間外・閉店済み'}
 return r,None
def area(place):
 if '中央区' in place or re.search('大通|すすきの|中島公園|北3条広場',place):return '札幌中心部'
 if '札幌' in place:return '札幌市内・周辺'
 if re.search('小樽|石狩',place):return '小樽・石狩'
 if re.search('江別|北広島',place):return '江別・北広島'
 return '千歳・恵庭・苫小牧'
def atomic(p,obj):
 p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix(p.suffix+'.tmp')
 tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf8');tmp.replace(p)
def run():
 t=datetime.now(JST).date();stamp=datetime.now(JST).isoformat()
 old=json.loads((PUBLIC/'news.json').read_text(encoding='utf8')); records={key(r):r for r in deduplicate(old['items'])}
 report={'attempted_at':stamp,'sources':[]};links={};pending=[]
 # Reuse the independent site's discovery, but re-check its original articles.
 try:
  response=requests.get('https://yasu1013siren-code.github.io/sapporo-inshoku/news.json',timeout=(6,18))
  response.raise_for_status();upstream=response.json()
  imported=0
  for rows in upstream.get('areas',{}).values():
   for item in rows:
    if not re.fullmatch(r'20\d{2}-\d{2}-\d{2}',item.get('date','')):continue
    kind={'open':'開店','upcoming':'開店','closed':'閉店','renewal':'リニューアル','event':'イベント'}.get(item.get('type'))
    if not kind or not eligible({'type':kind,'date':item['date'],'end':item.get('end') or item['date']},t):continue
    evidence=item.get('name','')+' '+item.get('note','')
    if NONFOOD.search(evidence) or not FOOD.search(evidence):continue
    urls=[{'url':item.get('url'),'name':item.get('source','既存収集サイト')}]+item.get('sources',[])
    for entry in urls:
     u=entry.get('url','')
     if u.startswith('https://'):
      links.setdefault(canonical(u),entry.get('name','既存収集サイト'));imported+=1
  report['sources'].append({'source':'sapporo-inshoku（原記事再確認）','ok':True,'discovered_links':imported})
 except Exception as e:report['sources'].append({'source':'sapporo-inshoku（原記事再確認）','ok':False,'error':type(e).__name__,'error_detail':str(e)[:500]})
 # Keep a saved URL for direct re-check, alongside newly discovered detail links.
 for r in records.values():links[canonical(r['url'])]=r['source']
 for source,url in SOURCE_LIST:
  try:
   soup=get(url);report['sources'].append({'source':source,'ok':True})
   links[canonical(url)]=source
   found=0
   for a in soup.select('a[href]'):
    label=a.get_text(' ',strip=True)+' '+' '.join(img.get('alt','') for img in a.select('img'));href=urljoin(url,a['href'])
    if not re.search('オープン|開店|閉店|リニューアル|グルメ|フード|食|物産|スイーツ|フェス|マルシェ|うまいもの|菓子|パン|珈琲|コーヒー|チョコ|ケーキ|プリン|期間限定|初登場|初上陸',label):continue
    if urlsplit(href).netloc!=urlsplit(url).netloc:continue
    if canonical(href) in links:continue
    # List and category navigation must not consume the detail-article budget.
    if re.search(r'/(?:category|page|tag)/|/(?:january|february|march|april|may|june|july|august|september|october|november|december)-open/?$',href):continue
    links.setdefault(canonical(href),source);found+=1
    if found>=50:break
  except Exception as e:report['sources'].append({'source':source,'ok':False,'error':type(e).__name__,'error_detail':str(e)[:500]})
 def detail(pair):
  u,source=pair
  try:
   soup=get(u)
   event,candidate=EVENTS['parse'](soup,u,source,t)
   if event:
    return (event,None) if eligible(event,t) else (None,{'name':event['name'],'url':u,'source':source,'reason':'掲載期間外'})
   if candidate:return None,candidate
   return parse_page(soup,u,source,t)
  except Exception as e:return None,{'url':u,'source':source,'reason':type(e).__name__,'error_detail':str(e)[:500]}
 checked=0
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
  for r,c in pool.map(detail,list(links.items())[:300]):
   if r:
    records={key(v):v for v in deduplicate(list(records.values())+[r])};checked+=1
   if c:pending.append(c)
 contacts_path=ROOT/'reviewed_contacts.json'
 if contacts_path.exists():
  verified=json.loads(contacts_path.read_text(encoding='utf8'))
  for r in records.values():
   if str(r['id']) in verified:r['contacts']=verified[str(r['id'])]
 successes=sum(x['ok'] for x in report['sources'])
 report.update({'successful_sources':successes,'accepted_details':checked,'pending':len(pending)})
 atomic(ROOT/'collection-report.json',report);atomic(ROOT/'unconfirmed.json',{'checked_at':stamp,'items':pending})
 if not successes:raise RuntimeError('全情報源の取得失敗。既存公開データは保持します。')
 # Partial failures remain visible; last_success means a collection run, not every item re-verified.
 output={**old,'last_run':stamp,'status':'partial' if successes<len(report['sources']) else 'success','source_success_count':successes,'source_total':len(report['sources']),'items':[r for r in records.values() if in_sapporo(r)]}
 atomic(PUBLIC/'news.json',output)
 print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':run()

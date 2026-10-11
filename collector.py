"""Daily conservative collection. Ambiguous candidates never become published records."""
import calendar, concurrent.futures, hashlib, json, re, time, unicodedata
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit
import requests
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parent
PUBLIC=ROOT/'public'
JST=timezone(timedelta(hours=9))
FOOD=re.compile(r'飲食|レストラン|カフェ|喫茶|居酒屋|ラーメン|焼肉|焼き肉|寿司|鮨|パン|ベーカリー|スイーツ|菓子|コーヒー|珈琲|バー|食堂|グルメ|フード|物産展|焼き芋|ビール|ワイン|日本酒|カレー|おでん|団子')
NONFOOD=re.compile(r'パーソナルジム|フィットネス|体操教室|スポーツジム|美容クリニック|美容医療|アパレル|整体|(?:APT\s*ROOM)',re.I)
GEO=re.compile(r'札幌|小樽|石狩|江別|北広島|千歳|恵庭|苫小牧')
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
 ('焼き芋テラス','https://sapporo-yakiimoterrace.com/')]
def norm(s): return re.sub(r'\s+','',unicodedata.normalize('NFKC',s or '')).lower()
def canonical(u):
 p=urlsplit(u);return urlunsplit((p.scheme,p.netloc,p.path.rstrip('/') or '/',p.query,''))
def key(r):return '|'.join(map(norm,[r['name'],r['type'],r['date']]))
def deduplicate(items):
 records={}
 for r in items:
  if NONFOOD.search(r.get('name','')):continue
  k=key(r)
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
 main=soup.select_one('article') or soup.select_one('main') or soup
 for n in main.select('nav,footer,header,aside,script:not([type="application/ld+json"]),style'):n.decompose()
 heading=main.select_one('h1') or soup.select_one('title')
 title=heading.get_text(' ',strip=True) if heading else ''
 text=main.get_text(' ',strip=True)
 candidate={'name':title[:140],'url':u,'source':source,'first_seen':t.isoformat(),'reason':'店名・所在地・実施日を確定できない'}
 if NONFOOD.search(title):return None,{**candidate,'reason':'グルメ対象外'}
 # Category evidence must come from the headline, never related articles or sidebars.
 if not FOOD.search(title):return None,{**candidate,'reason':'見出しに飲食・グルメの根拠がないため要確認'}
 if not GEO.search(title+' '+text[:4000]):return None,candidate
 kind='リニューアル' if re.search('リニューアル',title) else '閉店' if '閉店' in title else '開店' if re.search('オープン|開店',title) else 'イベント'
 # Publication timestamps are deliberately ignored. Dates must sit next to execution labels.
 execution=[]
 for line in re.split(r'[。\n]',text):
  if re.search(r'開催日|開催期間|会期|オープン日|開店日|閉店日|リニューアルオープン|20\d{2}年.{0,35}(?:オープン|開店|閉店)',line):
   execution.extend(re.findall(r'20\d{2}\s*[年/.-]\s*\d{1,2}\s*[月/.-]\s*\d{1,2}(?:日)?',line[:400]))
 dates=list(dict.fromkeys(filter(None,map(date_value,execution))))
 place=''
 for tr in main.select('tr'):
  cells=tr.select('th,td')
  if len(cells)>1 and re.search('住所|所在地|会場|開催場所',cells[0].get_text()):place=cells[1].get_text(' ',strip=True);break
 if not place:
  m=re.search(r'(?:住所|所在地|会場|開催場所)\s*[:：]?\s*((?:北海道)?(?:札幌|小樽|石狩|江別|北広島|千歳|恵庭|苫小牧)[^。]{2,100})',text)
  if m:place=m.group(1)
 name=''
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
 if not eligible(r,t):return None,{**candidate,'reason':'掲載期間外・閉店済み'}
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
 # Keep a saved URL for direct re-check, alongside newly discovered detail links.
 for r in records.values():links[canonical(r['url'])]=r['source']
 for source,url in SOURCE_LIST:
  try:
   soup=get(url);report['sources'].append({'source':source,'ok':True})
   links[canonical(url)]=source
   found=0
   for a in soup.select('a[href]'):
    label=a.get_text(' ',strip=True);href=urljoin(url,a['href'])
    if not re.search('オープン|開店|閉店|リニューアル|グルメ|フード|食|物産|スイーツ|フェス|マルシェ',label):continue
    if urlsplit(href).netloc!=urlsplit(url).netloc:continue
    links.setdefault(canonical(href),source);found+=1
    if found>=16:break
  except Exception as e:report['sources'].append({'source':source,'ok':False,'error':type(e).__name__})
 def detail(pair):
  u,source=pair
  try:return parse_page(get(u),u,source,t)
  except Exception as e:return None,{'url':u,'source':source,'reason':type(e).__name__}
 checked=0
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
  for r,c in pool.map(detail,list(links.items())[:150]):
   if r:
    records={key(v):v for v in deduplicate(list(records.values())+[r])};checked+=1
   if c:pending.append(c)
 successes=sum(x['ok'] for x in report['sources'])
 report.update({'successful_sources':successes,'accepted_details':checked,'pending':len(pending)})
 atomic(ROOT/'collection-report.json',report);atomic(ROOT/'unconfirmed.json',{'checked_at':stamp,'items':pending})
 if not successes:raise RuntimeError('全情報源の取得失敗。既存公開データは保持します。')
 # Partial failures remain visible; last_success means a collection run, not every item re-verified.
 output={**old,'last_run':stamp,'status':'partial' if successes<len(SOURCE_LIST) else 'success','source_success_count':successes,'source_total':len(SOURCE_LIST),'items':list(records.values())}
 atomic(PUBLIC/'news.json',output)
 print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':run()

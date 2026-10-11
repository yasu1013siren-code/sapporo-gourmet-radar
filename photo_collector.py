"""Collect conservative article thumbnails; preserve previous photos on failure."""
import hashlib,json,re,unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse,urljoin
import requests
from bs4 import BeautifulSoup
from PIL import Image,ImageOps
ROOT=Path(__file__).parent;PUBLIC=ROOT/'public';JST=timezone(timedelta(hours=9))
HEADERS={'User-Agent':'SapporoGourmetRadar/1.0 (+https://yasu1013siren-code.github.io/sapporo-gourmet-radar/)'}
SOURCES={'sapporo-sokuho.com','sapporo-list.info','www.shopship.jp','chamonix-cakes.com'}
def normalized(s):return re.sub(r'[\W_]+','',unicodedata.normalize('NFKC',s)).lower()
def matching(photo,item):return (photo.get('match_url') or photo['url']).rstrip('/')==item['url'].rstrip('/') or normalized(photo['name'])==normalized(item['name'])
def image_candidate(html,url,name):
 soup=BeautifulSoup(html,'html.parser');h=soup.find('h1')
 if not h or normalized(name) not in normalized(h.get_text()):return None
 text=soup.get_text(' ',strip=True)
 if re.search(r'写真はイメージ|画像はイメージ|写真は参考|イメージ画像',text):return None
 og=soup.find('meta',attrs={'property':'og:image'})
 if not og:return None
 image=urljoin(url,og.get('content',''));p=urlparse(image)
 if p.scheme!='https' or re.search(r'logo|ogp|favicon|kaihei|/event\.|/2021/02/|/themes/',image,re.I):return None
 if p.hostname!=urlparse(url).hostname:return None
 return image

def get(url):
 r=requests.get(url,timeout=(5,15),headers=HEADERS);r.raise_for_status();return r

def cache_photo(photo):
 path=PUBLIC/photo.get('local_image','_missing')
 if photo.get('local_image') and path.is_file():return photo
 r=get(photo['image'])
 if not r.headers.get('Content-Type','').lower().startswith('image/') or len(r.content)>12_000_000:raise ValueError('Unsupported image')
 im=ImageOps.exif_transpose(Image.open(BytesIO(r.content)))
 if min(im.size)<150:raise ValueError('Image too small')
 im.thumbnail((960,960));im=im.convert('RGB')
 relative='assets/photos/'+hashlib.sha256(photo['image'].encode()).hexdigest()[:20]+'.webp'
 target=PUBLIC/relative;target.parent.mkdir(parents=True,exist_ok=True)
 tmp=target.with_suffix('.tmp');im.save(tmp,format='WEBP',quality=82);tmp.replace(target)
 return {**photo,'local_image':relative,'cached_at':datetime.now(JST).isoformat()}

def run():
 target=PUBLIC/'photos.json';old=json.loads(target.read_text());photos=old['photos'];items=json.loads((PUBLIC/'news.json').read_text())['items'];now=datetime.now(JST);report={'attempted_at':now.isoformat(),'added':[],'failures':[],'skipped':[]}
 todo=[d for d in items if d.get('area') in ('札幌中心部','札幌市内・周辺','札幌市内（中心部以外）') and d['type']=='開店' and (now.date()-timedelta(days=60)).isoformat()<=d['date']<=now.date().isoformat() and not any(matching(p,d) for p in photos) and (urlparse(d['url']).hostname in SOURCES or (urlparse(d['url']).hostname or '').endswith('.goguynet.jp')) and not re.search(r'/archives/category/|/open/[^/]+open',d['url'])][:24]
 def discover(d):
  try:
   image=image_candidate(get(d['url']).text,d['url'],d['name'])
   if not image:return None,d['name'],None
   p={'name':d['name'],'url':d['url'],'image':image,'alt':d['name']+'の紹介記事掲載写真','source':d['source'],'official':bool(d.get('official')),'checked_at':now.date().isoformat(),'selection':'matched article thumbnail'}
   return cache_photo(p),d['name'],None
  except Exception as e:return None,d['name'],type(e).__name__
 with ThreadPoolExecutor(max_workers=4) as pool:
  for p,name,error in pool.map(discover,todo):
   if p:photos.append(p);report['added'].append(name)
   elif error:report['failures'].append({'name':name,'error':error})
   else:report['skipped'].append(name)
 def cache(p):
  try:return cache_photo(p),None
  except Exception as e:return p,{'name':p['name'],'error':type(e).__name__}
 with ThreadPoolExecutor(max_workers=4) as pool:
  results=list(pool.map(cache,photos))
 photos=[p for p,e in results];report['failures'].extend(e for p,e in results if e)
 # Append-only registry and atomically written files: failures never erase a photo.
 output={**old,'last_run':now.isoformat(),'photos':photos,'report':report}
 tmp=target.with_suffix('.tmp');tmp.write_text(json.dumps(output,ensure_ascii=False,indent=2));tmp.replace(target)
 print(json.dumps({'added':len(report['added']),'preserved':len(photos),'failures':len(report['failures'])}))
if __name__=='__main__':run()

"""Official department-store event parsing; unknown years stay in review."""
import re,hashlib
from datetime import date
from urllib.parse import urlsplit

SOURCES=[
 ('大丸札幌 食品催事','https://www.daimaru.co.jp/sapporo/hoppetown/'),
 ('大丸札幌 グルメ企画','https://www.daimaru.co.jp/sapporo/topics/'),
 ('札幌三越 食品ニュース','https://www.mitsukoshi.mistore.jp/sapporo/shops/foods/foods/shopnews_list.html'),
 ('丸井今井 食品催事','https://www.maruiimai.mistore.jp/sapporo/event_calendar.html'),
 ('クラシェ 食品出店','https://kurache.com/')]
FOOD=re.compile('食品|グルメ|スイーツ|菓子|パン|珈琲|コーヒー|ワイン|うまいもの|物産|シュークリーム|チョコ|ケーキ|マフィン|プリン')
PLACES={'www.daimaru.co.jp':'大丸札幌店（売場は出典で確認）','www.mitsukoshi.mistore.jp':'札幌三越（売場は出典で確認）','www.maruiimai.mistore.jp':'丸井今井札幌本店（売場は出典で確認）','kurache.com':'札幌駅前通地下歩行空間'}
def parse(soup,url,source,t):
 host=urlsplit(url).netloc
 if host not in PLACES:return None,None
 h=soup.select_one('h1') or soup.select_one('title')
 title=h.get_text(' ',strip=True) if h else ''
 if not FOOD.search(title):return None,None
 root=soup.select_one('article') or soup.select_one('main') or soup
 text=root.get_text(' ',strip=True).split('OTHER NEWS')[0]
 pos=text.find(title)
 if pos>=0:text=text[pos:]
 # Require an explicit event year and range, excluding publication timestamps.
 pattern=r'(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日.{0,18}?[～〜~→－-]\s*(?:(20\d{2})年)?\s*(?:(\d{1,2})月)?\s*(\d{1,2})日'
 m=re.search(pattern,text[:1800])
 candidate={'name':title,'url':url,'source':source,'first_seen':t.isoformat(),'reason':'食品催事候補：会期の年・売場を要確認'}
 if not m:return None,candidate
 y,mo,d,ey,em,ed=m.groups()
 try:start=date(int(y),int(mo),int(d));end=date(int(ey or y),int(em or mo),int(ed))
 except ValueError:return None,candidate
 if end<start:return None,candidate
 tags=['百貨店催事'] if host!='kurache.com' else ['食品マルシェ']
 if '北海道初' in text[:1800]:tags.append('北海道初登場（出典の対象商品を確認）')
 record={'id':int(hashlib.sha256((title+url+start.isoformat()).encode()).hexdigest()[:12],16),'name':title,'type':'イベント','date':start.isoformat(),'end':end.isoformat(),'place':PLACES[host],'area':'札幌中心部','genre':'食品催事・期間限定','text':'公式に告知された食品企画。出店ブランド・売場・販売条件は出典の最新案内を確認してください。','url':url,'source':source,'official':True,'checked_at':t.isoformat(),'tags':tags}
 return record,None

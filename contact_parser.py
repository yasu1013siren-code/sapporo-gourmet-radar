"""Only extract business contacts from labelled shop-information fields."""
import re
from urllib.parse import urljoin,urlsplit
def extract(soup,base):
 out={};sections=[]
 for tr in soup.select('tr'):
  cells=tr.select('th,td')
  if len(cells)>1:sections.append((cells[0].get_text(' ',strip=True),cells[1]))
 for dt in soup.select('dt'):
  dd=dt.find_next_sibling('dd')
  if dd:sections.append((dt.get_text(' ',strip=True),dd))
 for label,node in sections:
  text=node.get_text(' ',strip=True)
  if re.search('電話|TEL',label,re.I):
   m=re.search(r'0\d{1,4}[-－]\d{1,4}[-－]\d{3,4}',text)
   if m:out['phone']=m.group(0).replace('－','-')
  if re.search('メール|mail',label,re.I):
   m=re.search(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}',text)
   if m:out['email']=m.group(0)
  if not re.search('リンク|SNS|公式|予約|ホームページ|WEB|サイト',label,re.I):continue
  for a in node.select('a[href]'):
   u=urljoin(base,a['href']);host=urlsplit(u).netloc.lower();name=a.get_text(' ',strip=True)
   if u.startswith('tel:'):out['phone']=u[4:]
   elif u.startswith('mailto:'):out['email']=u[7:].split('?')[0]
   elif host in ('www.hotpepper.jp','tabelog.com','www.tablecheck.com','www.ozmall.co.jp'):out.setdefault('reservation_url',u)
   elif u.startswith('https://') and re.search('公式|ホームページ|WEB|サイト',label+' '+name,re.I):out.setdefault('website_url',u)
 if out:out['source_url']=base
 return out

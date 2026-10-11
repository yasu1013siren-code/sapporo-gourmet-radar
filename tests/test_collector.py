import importlib.util, pathlib, unittest
from datetime import date
from bs4 import BeautifulSoup
spec=importlib.util.spec_from_file_location('collector',pathlib.Path(__file__).parents[1]/'collector.py');c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
class CollectorTests(unittest.TestCase):
 def test_month_and_closed(self):
  self.assertEqual(c.shift(date(2026,3,31),-1),date(2026,2,28))
  self.assertFalse(c.eligible({'type':'閉店','date':'2026-10-10'},date(2026,10,11)))
  self.assertTrue(c.eligible({'type':'イベント','date':'2026-09-01','end':'2026-10-15'},date(2026,10,11)))
 def test_published_date_is_not_execution(self):
  soup=BeautifulSoup('<article><h1>札幌 カフェ「テスト」開店</h1><time>2026年10月10日</time><p>住所：札幌市中央区南1条1丁目</p></article>','html.parser')
  self.assertIsNone(c.parse_page(soup,'https://example.org/a','fixture',date(2026,10,11))[0])
 def test_structured_event(self):
  soup=BeautifulSoup('''<h1>札幌 グルメイベント</h1><script type="application/ld+json">{"@type":"Event","name":"グルメフェス","startDate":"2026-10-15","endDate":"2026-10-16","location":{"name":"札幌 中央区","address":{"addressLocality":"札幌市中央区"}}}</script>''','html.parser')
  r,_=c.parse_page(soup,'https://example.org/a','fixture',date(2026,10,11));self.assertEqual(r['date'],'2026-10-15')
 def test_branches_not_merged(self):
  a={'name':'カフェ','place':'札幌市中央区1','type':'開店','date':'2026-10-11'};b={**a,'place':'札幌市中央区2'}
  self.assertNotEqual(c.key(a),c.key(b))
if __name__=='__main__':unittest.main()

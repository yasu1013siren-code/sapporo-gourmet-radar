import unittest
from unittest.mock import patch
import photo_collector as p
class PhotoSelectionTests(unittest.TestCase):
 def page(self,title,img,body=''):
  return f'<h1>{title}</h1><meta property="og:image" content="{img}">{body}'
 def test_matching_article_photo(self):
  self.assertEqual(p.image_candidate(self.page('新店 安安 札幌篠路店','https://example.org/photo.jpg'),'https://example.org/post','安安 札幌篠路店'),'https://example.org/photo.jpg')
 def test_other_branch_rejected(self):
  self.assertIsNone(p.image_candidate(self.page('安安 札幌麻生店','https://example.org/photo.jpg'),'https://example.org/post','安安 札幌篠路店'))
 def test_stock_and_logo_rejected(self):
  for img,body in [('https://example.org/ogp.png',''),('https://example.org/photo.jpg','写真はイメージです。')]:
   self.assertIsNone(p.image_candidate(self.page('安安 札幌篠路店',img,body),'https://example.org/post','安安 札幌篠路店'))
 def test_existing_image_is_not_downloaded_again(self):
  photo={'local_image':'assets/miyakoshiya.webp'}
  with patch.object(p,'get',side_effect=AssertionError('Unexpected download')):
   self.assertEqual(p.cache_photo(photo),photo)
if __name__=='__main__':unittest.main()

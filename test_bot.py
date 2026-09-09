import tempfile,unittest
from pathlib import Path
from bot import Bot
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=str(Path(self.tmp.name)/'test.db');self.b=Bot('fake',1,self.path);self.calls=[]
  self.b.api=lambda method,data:self.calls.append((method,data))
 def tearDown(self):self.b.db.close();self.tmp.cleanup()
 def message(self,uid,text):self.b.handle({'message':{'chat':{'id':uid,'type':'private'},'text':text}})
 def callback(self,uid,data):self.b.handle({'callback_query':{'id':'fake','data':data,'message':{'chat':{'id':uid,'type':'private'}}}})
 def test_access(self):
  self.callback(2,'q:picture:1');self.assertFalse(any(m=='sendPhoto' for m,d in self.calls))
  self.message(2,'/grant 2');self.assertFalse(self.b.allowed(2))
  self.message(1,'/grant 2');self.assertTrue(self.b.allowed(2));self.callback(2,'q:picture:1');self.assertTrue(any(m=='sendPhoto' for m,d in self.calls))
  self.message(1,'/revoke 2');self.assertFalse(self.b.allowed(2))
 def test_number_and_persistence(self):
  self.callback(1,'pick:picture');self.message(1,'1');self.assertTrue(any(m=='sendPhoto' for m,d in self.calls))
  other=Bot('fake',1,self.path);self.assertEqual(other.db.execute('SELECT number FROM progress WHERE uid=1').fetchone()[0],1);other.db.close()
 def test_missing(self):
  self.callback(1,'q:picture:999');self.assertFalse(any(m=='sendPhoto' for m,d in self.calls))
if __name__=='__main__':unittest.main()

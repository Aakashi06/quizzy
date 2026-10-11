import unittest, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server import BANK, validate, digest
class CoreTests(unittest.TestCase):
    def test_curated_library(self):
        self.assertEqual(sum(map(len,BANK.values())),255)
        for qs in BANK.values():
            validate(qs,85)
            for difficulty in ('easy','medium','hard'):
                self.assertGreaterEqual(len([q for q in qs if q['difficulty']==difficulty]),25)
    def test_reject_duplicate(self):
        q=BANK['Motion'][0]
        with self.assertRaises(ValueError): validate([q,q],2)
    def test_grounding(self):
        q=BANK['Motion'][0]
        with self.assertRaises(ValueError): validate([q],1,'Unrelated notes')
        validate([q],1,q['source_excerpt'])
    def test_password_salts(self):
        self.assertNotEqual(digest('password123','00'*16),digest('password123','01'*16))
if __name__=='__main__': unittest.main()

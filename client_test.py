import unittest
from client import getRatio

class TestGetRatio(unittest.TestCase):
    def test_divide_by_zero(self):
        passed = self.assertIsNone(getRatio(10, 0)) == None
        if passed:
            print('[PASS] GetRatio - Divide By Zero')
        else:
            print('[FAIL] GetRatio - Divide By Zero')
        
    def test_normal_case(self):
        passed = self.assertEqual(getRatio(10, 5), 2) == None
        if passed:
            print('[PASS] GetRatio - Normal Case')
        else:
            print('[FAIL] GetRatio - Normal Case')

        
if __name__ == '__main__':
    unittest.main()

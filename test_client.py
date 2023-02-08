import unittest


class TestClass(unittest.TestCase):
    def test_get_data_point(self):
        self.bid = 100
        self.ask = 60
        self.price = self.bid + self.ask / 2
        self.assertEqual(self.price, 130)

    def test_get_ratio(self):
        self.price_a = 12
        self.price_b = 2
        self.assertEqual(self.price_a / self.price_b, 6)

    if __name__ == '__main__':
        unittest.main()

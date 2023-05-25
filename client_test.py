import unittest
from client3 import getDataPoint, getRatio

class ClientTest(unittest.TestCase):
  def test_getDataPoint_calculatePrice(self):
    quotes = [
      {'top_ask': {'price': 121.2, 'size': 36}, 'timestamp': '2019-02-11 22:06:30.572453', 'top_bid': {'price': 120.48, 'size': 109}, 'id': '0.109974697771', 'stock': 'ABC'},
      {'top_ask': {'price': 121.68, 'size': 4}, 'timestamp': '2019-02-11 22:06:30.572453', 'top_bid': {'price': 117.87, 'size': 81}, 'id': '0.109974697771', 'stock': 'DEF'}
    ]
    """ ------------ Add the assertion below ------------ """
    expected_result = getDataPoint(quotes[0])
    excepted_result2 = getDataPoint(quotes[1])
    first_price = (121.2+120.48)/2
    second_price = (121.68+117.87)/2
    assert expected_result == ("ABC",120.48,121.2,first_price), "The calculated price is not correct."
    assert excepted_result2 == ("DEF",117.87,121.68,second_price), "The calculated price is not correct."

  def test_getDataPoint_calculatePriceBidGreaterThanAsk(self):
    quotes = [
      {'top_ask': {'price': 119.2, 'size': 36}, 'timestamp': '2019-02-11 22:06:30.572453', 'top_bid': {'price': 120.48, 'size': 109}, 'id': '0.109974697771', 'stock': 'ABC'},
      {'top_ask': {'price': 121.68, 'size': 4}, 'timestamp': '2019-02-11 22:06:30.572453', 'top_bid': {'price': 117.87, 'size': 81}, 'id': '0.109974697771', 'stock': 'DEF'}
    ]
    """ ------------ Add the assertion below ------------ """
    expected_result = getDataPoint(quotes[0])
    expected_result2 = getDataPoint(quotes[1])
    first_price = (119.2+120.48)/2
    second_price = (117.87+121.68)/2
    assert expected_result == ("ABC",120.48,119.2,first_price)
    assert expected_result2 == ("DEF",117.87,121.68,second_price)
    
  """ ------------ Add more unit tests ------------ """
  
  def test_getRatio(self):
    # test case 1: price_b is non-zero
    price_a = 121.2
    price_b = 120.48
    expected_ratio = price_a/price_b
    assert getRatio(price_a,price_b) == expected_ratio, "ratio is not correct"
    
    # test case 2: price_b zero
    price_a = 121.68
    price_b = 0
    assert getRatio(price_a,price_b) is None,"ratio is not correct"



if __name__ == '__main__':
    unittest.main()

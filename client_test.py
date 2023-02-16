import client

def test_getRatio():
    assert client.getRatio(118,59) == 2, "Should be 2"

if __name__ == "__main__":
    test_getRatio()
    print("Unit test passed")
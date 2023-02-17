import client
import pytest


def test_checkRatio():
    assert client.getRatio(127.34, 50.77) != 1
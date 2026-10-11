# tests/core/conftest.py – make real network fail
import os
import socket
import urllib.request

# monkeypatch urllib.request.urlopen to raise
class FakeURLopener:
    def __init__(self, *a, **k):
        pass
    def read(self):
        raise urllib.error.URLError("network disabled in test")

urllib.request.urlopen = lambda *a, **k: FakeURLopener()
# also disable socket
socket.create_connection = lambda *a, **k: (_ for _ in ()).throw(urllib.error.URLError("network disabled in test"))

# set env var to a fake key for cloud
os.environ['OPENROUTER_API_KEY'] = 'sk_test_notused'

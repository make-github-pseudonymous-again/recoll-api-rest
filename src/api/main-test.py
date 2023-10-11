from .main import chunked_str


def test_chunked_str():
    x = "abracadabra" * 2**9
    assert x == "".join(chunked_str(x, chunk_size=10))

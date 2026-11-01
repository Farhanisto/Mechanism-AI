"""The production server must be reachable over both address families."""

import socket

import pytest
from run_server import build_sockets


@pytest.mark.skipif(not socket.has_ipv6, reason="IPv6 is unavailable")
def test_build_sockets_listens_on_ipv4_and_ipv6() -> None:
    probe = socket.socket(socket.AF_INET)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()

    sockets = build_sockets(port)
    try:
        families = {sock.family for sock in sockets}
        assert families == {socket.AF_INET, socket.AF_INET6}
    finally:
        for sock in sockets:
            sock.close()

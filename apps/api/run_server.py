"""Start uvicorn on both IPv4 and IPv6 sockets.

Railway private DNS can return A and AAAA records, and nginx may pick either
address. Binding both families avoids intermittent "connection refused" errors
when the proxy chooses the family the server was not listening on.
"""

import os
import socket

import uvicorn


def build_sockets(port: int) -> list[socket.socket]:
    sockets: list[socket.socket] = []
    specs = (
        (socket.AF_INET6, "::", True),
        (socket.AF_INET, "0.0.0.0", False),
    )
    for family, host, ipv6_only in specs:
        try:
            sock = socket.socket(family, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if ipv6_only:
                sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
            sock.bind((host, port))
            sock.listen(2048)
        except OSError as exc:
            print(f"Could not listen on {host}:{port}: {exc}", flush=True)
            continue
        sockets.append(sock)
    if not sockets:
        raise SystemExit(f"Could not bind port {port} on IPv4 or IPv6")
    return sockets


def main() -> None:
    from app.main import app

    port = int(os.environ.get("PORT", "8000"))
    sockets = build_sockets(port)
    families = ", ".join(sock.family.name.replace("AF_", "") for sock in sockets)
    print(f"Listening on port {port} ({families})", flush=True)
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="0.0.0.0",
            port=port,
            proxy_headers=True,
            forwarded_allow_ips="*",
        )
    )
    server.run(sockets=sockets)


if __name__ == "__main__":
    main()

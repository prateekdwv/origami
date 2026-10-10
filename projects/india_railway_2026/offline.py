"""Fail closed on Python networking in rendering and verification processes."""
import socket

def deny_network():
    def blocked(*args, **kwargs):
        raise RuntimeError("Offline replay: network access is disabled")
    socket.socket.connect = blocked
    socket.socket.connect_ex = blocked
    socket.create_connection = blocked
    socket.getaddrinfo = blocked

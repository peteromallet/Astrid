import socket
import threading
import time
from types import SimpleNamespace

from astrid.core.execution.network_broker import ObservableNetworkBroker, _BrokerHandler


def test_tunnel_survives_poll_idle_and_stops_on_cancellation():
    client, caller = socket.socketpair()
    upstream, server = socket.socketpair()
    broker = ObservableNetworkBroker(tunnel_idle_seconds=1.0)
    handler = object.__new__(_BrokerHandler)
    handler.connection = client
    handler.server = SimpleNamespace(broker=broker)
    worker = threading.Thread(target=handler._tunnel, args=(upstream,))
    worker.start()
    try:
        # Exceed the cancellation poll interval without exceeding the
        # admitted idle budget: idle polls must not close model streams.
        time.sleep(0.35)
        server.sendall(b"delayed image response")
        caller.settimeout(1)
        assert caller.recv(128) == b"delayed image response"
        broker.stop()
        worker.join(timeout=1)
        assert not worker.is_alive()
    finally:
        broker.stop()
        worker.join(timeout=1)
        for stream in (client, caller, upstream, server):
            stream.close()


def test_tunnel_expires_at_its_bounded_idle_budget():
    client, caller = socket.socketpair()
    upstream, server = socket.socketpair()
    broker = ObservableNetworkBroker(tunnel_idle_seconds=0.05)
    handler = object.__new__(_BrokerHandler)
    handler.connection = client
    handler.server = SimpleNamespace(broker=broker)
    worker = threading.Thread(target=handler._tunnel, args=(upstream,))
    worker.start()
    worker.join(timeout=1)
    assert not worker.is_alive()
    for stream in (client, caller, upstream, server):
        stream.close()

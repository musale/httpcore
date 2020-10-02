import contextlib
import functools
import threading
import time
from typing import Callable, Tuple, Iterator

import sniffio
import trio

try:
    from hypercorn import config as hypercorn_config, trio as hypercorn_trio
except ImportError:
    # Python 3.6.
    hypercorn_config = None  # type: ignore
    hypercorn_trio = None  # type: ignore


def lookup_async_backend():
    return sniffio.current_async_library()


def lookup_sync_backend():
    return "sync"


class Server:
    """
    Represents the server we're testing against.
    """

    def __init__(
        self,
        app: Callable,
        host: str,
        port: int,
        bind: str = None,
        certfile: str = None,
        keyfile: str = None,
    ) -> None:
        self._app = app
        self._host = host
        self._port = port
        self._config = hypercorn_config.Config()
        self._config.bind = [bind or f"{host}:{port}"]
        self._config.certfile = certfile
        self._config.keyfile = keyfile
        self._config.worker_class = "asyncio"
        self._started = False
        self._should_exit = False

    @property
    def netloc(self) -> Tuple[bytes, int]:
        return (self._host.encode("ascii"), self._port)

    @property
    def host_header(self) -> Tuple[bytes, bytes]:
        return (b"host", self._host.encode("ascii"))

    def _run(self) -> None:
        async def shutdown_trigger() -> None:
            while not self._should_exit:
                await trio.sleep(0.01)

        serve = functools.partial(
            hypercorn_trio.serve, shutdown_trigger=shutdown_trigger
        )

        async def main() -> None:
            async with trio.open_nursery() as nursery:
                await nursery.start(serve, self._app, self._config)
                self._started = True

        trio.run(main)

    @contextlib.contextmanager
    def serve_in_thread(self) -> Iterator[None]:
        thread = threading.Thread(target=self._run)
        thread.start()
        try:
            while not self._started:
                time.sleep(1e-3)
            yield
        finally:
            self._should_exit = True
            thread.join()

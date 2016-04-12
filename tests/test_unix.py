import asyncio
import os
import socket
import tempfile
import uvloop
import unittest.mock

from uvloop import _testbase as tb


class _TestUnix:
    def test_create_server_1(self):
        CNT = 0           # number of clients that were successful
        TOTAL_CNT = 100   # total number of clients that test will create
        TIMEOUT = 5.0     # timeout for this test

        async def handle_client(reader, writer):
            nonlocal CNT

            data = await reader.readexactly(4)
            self.assertEqual(data, b'AAAA')
            writer.write(b'OK')

            data = await reader.readexactly(4)
            self.assertEqual(data, b'BBBB')
            writer.write(b'SPAM')

            await writer.drain()
            writer.close()

            CNT += 1

        async def test_client(addr):
            sock = socket.socket(socket.AF_UNIX)
            with sock:
                sock.setblocking(False)
                await self.loop.sock_connect(sock, addr)

                await self.loop.sock_sendall(sock, b'AAAA')
                data = await self.loop.sock_recv(sock, 2)
                self.assertEqual(data, b'OK')

                await self.loop.sock_sendall(sock, b'BBBB')
                data = await self.loop.sock_recv(sock, 4)
                self.assertEqual(data, b'SPAM')

        async def start_server():
            nonlocal CNT
            CNT = 0

            with tempfile.TemporaryDirectory() as td:
                sock_name = os.path.join(td, 'sock')
                try:
                    srv = await asyncio.start_unix_server(
                        handle_client,
                        sock_name,
                        loop=self.loop)

                    try:
                        srv_socks = srv.sockets
                        self.assertTrue(srv_socks)

                        tasks = []
                        for _ in range(TOTAL_CNT):
                            tasks.append(test_client(sock_name))

                        try:
                            await asyncio.wait_for(
                                asyncio.gather(*tasks, loop=self.loop),
                                TIMEOUT, loop=self.loop)
                        finally:
                            self.loop.stop()

                    finally:
                        srv.close()

                        # Check that the server cleaned-up proxy-sockets
                        for srv_sock in srv_socks:
                            self.assertEqual(srv_sock.fileno(), -1)

                except:
                    self.loop.stop()  # We don't want this test to stuck when
                                      # it fails.
                    raise

        async def start_server_sock():
            nonlocal CNT
            CNT = 0

            with tempfile.TemporaryDirectory() as td:
                sock_name = os.path.join(td, 'sock')
                sock = socket.socket(socket.AF_UNIX)
                sock.bind(sock_name)
                try:
                    srv = await asyncio.start_unix_server(
                        handle_client,
                        None,
                        loop=self.loop,
                        sock=sock)

                    try:
                        srv_socks = srv.sockets
                        self.assertTrue(srv_socks)

                        tasks = []
                        for _ in range(TOTAL_CNT):
                            tasks.append(test_client(sock_name))

                        try:
                            await asyncio.wait_for(
                                asyncio.gather(*tasks, loop=self.loop),
                                TIMEOUT, loop=self.loop)
                        finally:
                            self.loop.stop()

                    finally:
                        srv.close()

                        # Check that the server cleaned-up proxy-sockets
                        for srv_sock in srv_socks:
                            self.assertEqual(srv_sock.fileno(), -1)

                except:
                    self.loop.stop()  # We don't want this test to stuck when
                                      # it fails.
                    raise

        self.loop.create_task(start_server())
        self.loop.run_forever()
        self.assertEqual(CNT, TOTAL_CNT)

        self.loop.create_task(start_server_sock())
        self.loop.run_forever()
        self.assertEqual(CNT, TOTAL_CNT)

    def test_create_unix_connection_1(self):
        CNT = 0
        TOTAL_CNT = 100

        def server():
            data = yield tb.read(4)
            self.assertEqual(data, b'AAAA')
            yield tb.write(b'OK')

            data = yield tb.read(4)
            self.assertEqual(data, b'BBBB')
            yield tb.write(b'SPAM')

        async def client(addr):
            reader, writer = await asyncio.open_unix_connection(
                addr,
                loop=self.loop)

            writer.write(b'AAAA')
            self.assertEqual(await reader.readexactly(2), b'OK')

            writer.write(b'BBBB')
            self.assertEqual(await reader.readexactly(4), b'SPAM')

            nonlocal CNT
            CNT += 1

            writer.close()

        async def client_2(addr):
            sock = socket.socket(socket.AF_UNIX)
            sock.connect(addr)
            reader, writer = await asyncio.open_unix_connection(
                sock=sock,
                loop=self.loop)

            writer.write(b'AAAA')
            self.assertEqual(await reader.readexactly(2), b'OK')

            writer.write(b'BBBB')
            self.assertEqual(await reader.readexactly(4), b'SPAM')

            nonlocal CNT
            CNT += 1

            writer.close()

        def run(coro):
            nonlocal CNT
            CNT = 0

            srv = tb.unix_server(server,
                                 max_clients=TOTAL_CNT,
                                 backlog=TOTAL_CNT,
                                 timeout=5)
            srv.start()

            tasks = []
            for _ in range(TOTAL_CNT):
                tasks.append(coro(srv.addr))

            self.loop.run_until_complete(
                asyncio.gather(*tasks, loop=self.loop))
            srv.join()
            self.assertEqual(CNT, TOTAL_CNT)

        run(client)
        run(client_2)

    def test_create_unix_connection_2(self):
        with tempfile.NamedTemporaryFile() as tmp:
            path = tmp.name

        async def client():
            reader, writer = await asyncio.open_unix_connection(
                path,
                loop=self.loop)

        async def runner():
            with self.assertRaises(FileNotFoundError):
                await client()

        self.loop.run_until_complete(runner())

    def test_create_unix_connection_3(self):
        CNT = 0
        TOTAL_CNT = 100

        def server():
            data = yield tb.read(4)
            self.assertEqual(data, b'AAAA')
            yield tb.close()

        async def client(addr):
            reader, writer = await asyncio.open_unix_connection(
                addr,
                loop=self.loop)

            writer.write(b'AAAA')

            with self.assertRaises(asyncio.IncompleteReadError):
                await reader.readexactly(10)

            writer.close()

            nonlocal CNT
            CNT += 1

        def run(coro):
            nonlocal CNT
            CNT = 0

            srv = tb.unix_server(server,
                                 max_clients=TOTAL_CNT,
                                 backlog=TOTAL_CNT,
                                 timeout=5)
            srv.start()

            tasks = []
            for _ in range(TOTAL_CNT):
                tasks.append(coro(srv.addr))

            self.loop.run_until_complete(asyncio.gather(*tasks, loop=self.loop))
            srv.join()
            self.assertEqual(CNT, TOTAL_CNT)

        run(client)

    def test_create_unix_connection_4(self):
        sock = socket.socket()
        sock.close()

        async def client():
            reader, writer = await asyncio.open_unix_connection(
                sock=sock,
                loop=self.loop)

        async def runner():
            with self.assertRaisesRegex(OSError, 'Bad file'):
                await client()

        self.loop.run_until_complete(runner())

    def test_create_unix_connection_5(self):
        s1, s2 = socket.socketpair(socket.AF_UNIX)

        excs = []

        class Proto(asyncio.Protocol):
            def connection_lost(self, exc):
                excs.append(exc)

        proto = Proto()

        async def client():
            t, _ = await self.loop.create_unix_connection(
                lambda: proto,
                None,
                sock=s2)

            t.write(b'AAAAA')
            s1.close()
            t.write(b'AAAAA')
            await asyncio.sleep(0.1, loop=self.loop)

        self.loop.run_until_complete(client())

        self.assertEqual(len(excs), 1)
        self.assertIn(excs[0].__class__,
            (BrokenPipeError, ConnectionResetError))


class Test_UV_Unix(_TestUnix, tb.UVTestCase):
    pass


class Test_AIO_Unix(_TestUnix, tb.AIOTestCase):
    pass

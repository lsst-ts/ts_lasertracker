import asyncio


class MockT2SA():
    """
    Emulates New River Kinematics's T2SA application.
    """

    def __init__(self):
        self.response_dict = {}
        asyncio.run(self.run_server())

    async def responder(reader, writer):
        data = await reader.read(100)
        msg = data.decode()
        addr = writer.get_extra_info('peername')
        print(f"Received {msg} from {addr}")
        print(f"send: {msg}")
        writer.write(data)
        await writer.drain()
        writer.close()

    async def run_server(self):
        server = await asyncio.start_server(self.responder, '127.0.0.1', 50000)
        addr = server.sockets[0].getsockname()
        print(f"serving on {addr}")

        async with server:
            await server.serve_forever()

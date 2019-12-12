import asyncio


class MockT2SA():
    """
    Emulates New River Kinematics's T2SA application.
    """

    def __init__(self):
        self.server = None
        self.response_dict = {"?STAT": "READY",
                              "!CMDEXE:M1M3": "ACK300"}

    async def start(self, timeout=5):
        self.server = await asyncio.start_server(self.response_loop, host="172.17.0.2", port=50000)

    async def stop(self, timeout=5):
        if self.server is None:
            return
        server = self.server
        self.server = None
        server.close()
        await asyncio.wait_for(server.wait_closed(), timeout=5)

    async def response_loop(self, reader, writer):
        print("Response Loop begins")
        while True:
            line = await reader.readline()
            line = line.decode()
            if not line:
                writer.close()
                print("no line")
                return
            line = line.strip()
            print(f"read command: {line!r}")
            if line:
                try:
                    response = self.response_dict[line] + "\r\n"
                    writer.write(response.encode())
                except Exception as e:
                    print(e)
            await writer.drain()
        print("while loop over")
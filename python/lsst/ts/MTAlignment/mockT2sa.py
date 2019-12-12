import asyncio
from random import randrange


class MockT2SA():
    """
    Emulates New River Kinematics's T2SA application.
    """

    def __init__(self, ip="172.17.0.2"):
        self.server = None
        self.ip = ip
        self.measuring = False
        self.response_dict = {"?STAT": self.status,
                              "!CMDEXE:M1M3": self.execute_measurement_plan,
                              "!CMDEXE:CAM": self.execute_measurement_plan,
                              "!CMDEXE:M2": self.execute_measurement_plan,
                              "?POS M1M3": "<m1m3_coordinates>",
                              "?POS CAM": "<cam_coordinates>",
                              "?POS M2": "<m2_coordinates>"
                              }

    async def start(self, timeout=5):
        self.server = await asyncio.start_server(self.response_loop, host=self.ip, port=50000)

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
            print(f"Mock T2SA received line: {line}")
            line = line.decode()
            if not line:
                writer.close()
                return
            line = line.strip()
            if line:
                try:
                    response = self.response_dict[line]
                    if isinstance(response, str):
                        response = response + "\r\n"
                    else:
                        response = await response(writer)
                    if response is not None:
                        writer.write(response.encode())
                except Exception as e:
                    print(e)
            await writer.drain()
        print("while loop over")

    async def execute_measurement_plan(self, writer):
        print("begin measuring")
        ack = "ACK300\r\n"
        writer.write(ack.encode())
        await writer.drain()

        self.measuring = True
        await asyncio.sleep(randrange(5,15))
        self.measuring = False
        print("done measuring")

    async def status(self, writer):
        if self.measuring:
            return "EMP\r\n"
        else:
            return "READY\r\n"
import asyncio
from random import randrange
import logging


class MockT2SA():
    """
    Emulates New River Kinematics's T2SA application.
    """

    def __init__(self, ip="172.17.0.3"):
        self.server = None
        self.ip = ip
        self.measuring = False
        self.log = logging.getLogger()
        self.run_loop_flag = True
        self.response_dict = {"?STAT": self.status,
                              "!CMDEXE:M1M3": self.execute_measurement_plan,
                              "!CMDEXE:CAM": self.execute_measurement_plan,
                              "!CMDEXE:M2": self.execute_measurement_plan,
                              "?POS M1M3": "<m1m3_coordinates>",
                              "?POS CAM": "<cam_coordinates>",
                              "?POS M2": "<m2_coordinates>"
                              }

    async def start(self, timeout=5):
        """
        Start the server
        """
        self.server = await asyncio.start_server(self.response_loop, host=self.ip, port=50000)

    async def stop(self, timeout=5):
        """
        Stop the server
        """
        if self.server is None:
            return
        server = self.server
        self.server = None
        server.close()
        await asyncio.wait_for(server.wait_closed(), timeout=5)
        self.run_loop_flag = False

    async def response_loop(self, reader, writer):
        """
        Listens for messages from the CSC and responds either with canned text or
        by invoking a method from self.response_dict.
        """

        self.log.debug("Response Loop begins")
        while self.run_loop_flag:
            line = await reader.readline()
            self.log.debug(f"Mock T2SA received line: {line}")
            line = line.decode()
            if not line:
                writer.close()
                return
            line = line.strip()
            if line:
                try:
                    response = self.response_dict[line]
                    # some responses are just strings, others are coroutines
                    if isinstance(response, str):
                        response = response + "\r\n"
                    else:
                        # coroutines get passed writer so they can send messages to the CSC.
                        response = await response(writer)
                    if response is not None:
                        writer.write(response.encode())
                except Exception as e:
                    self.log.debug(e)
            await writer.drain()
        self.log.debug("response loop ends")

    async def execute_measurement_plan(self, writer):
        """
        Acknowledges the request to measure, then pretends to measure.
        """

        self.log.debug("begin measuring")
        ack = "ACK300\r\n"
        writer.write(ack.encode())
        await writer.drain()

        self.measuring = True
        await asyncio.sleep(randrange(5, 15))
        self.measuring = False
        self.log.debug("done measuring")

    async def status(self, writer):
        """
        While pretend measuring is happening, status should return "EMP"--
        Executing Measurement Plan
        """

        if self.measuring:
            return "EMP\r\n"
        else:
            return "READY\r\n"

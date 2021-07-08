import asyncio
import logging


class MockT2SA:
    """
    Emulates New River Kinematics's T2SA application.
    """

    def __init__(self, ip="127.0.0.1", port=50000):
        self.server = None
        self.ip = ip
        self.port = port
        self.measuring = False
        self.log = logging.getLogger()
        self.run_loop_flag = True
        self._measure_task = None
        self.response_dict = {
            "?STAT": self.status,
            "!CMDEXE:M1M3": self.execute_measurement_plan,
            "!CMDEXE:CAM": self.execute_measurement_plan,
            "!CMDEXE:M2": self.execute_measurement_plan,
            "?POS M1M3": "<m1m3_coordinates>",
            "?POS CAM": "<cam_coordinates>",
            "?POS M2": "<m2_coordinates>",
            "?OFFSET M1M3": "<m1m3_offset>",
            "?OFFSET CAM": "<cam_offset>",
            "?OFFSET M2": "<m2_offset>",
            "?LSTA": "LON",
            "!LST:0": "ACK300",
            "!LST:1": "ACK300",
            "SET_RANDOMIZE_POINTS:1": "ACK300",
            "SET_RANDOMIZE_POINTS:0": "ACK300",
        }

    async def start(self, timeout=5):
        """
        Start the server
        """
        self.server = await asyncio.start_server(
            self.response_loop, host=self.ip, port=self.port
        )
        return self.server.sockets[0].getsockname()[1]

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
        Listens for messages from the CSC and responds either with canned
        text or by invoking a method from self.response_dict.
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
                        # coroutines get passed writer so they can send
                        # messages to the CSC.
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
        # Schedule task that will emulate measurement in the background
        if self._measure_task is None or self._measure_task.done():
            self.measuring = True
            self._measure_task = asyncio.create_task(self.measure_task())
        else:
            # this need to fail
            ack = "ACK000\r\n"
            writer.write(ack.encode())
            await writer.drain()
        ack = "ACK300\r\n"
        writer.write(ack.encode())
        await writer.drain()

    async def measure_task(self):
        """Emulate measurement plan."""
        await asyncio.sleep(2)
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

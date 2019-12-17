
import asyncio
from enum import IntEnum


class LaserStatus(IntEnum):
    LASERNOTCONNECTED = -1
    LASEROFF = 0
    LASERON = 1


class TrackerStatus(IntEnum):
    READY = 1
    TWOFACE = 2
    ADM = 3
    DRIFT = 4
    EMP = 5
    ERR = 6


class AlignmentModel():

    def __init__(self):
        self.server_address = ("172.17.0.3", 50000)
        self.connected = False
        self.reader = None
        self.writer = None
        self.first_measurement = True

        self.trackerstatus = None

    async def connect(self):
        self.reader, self.writer = await asyncio.open_connection(*self.server_address)
        self.connected = True
        asyncio.create_task(self.status_loop())

    async def status_loop(self):
        """
        pings T2SA for status every second, and updates internal state.
        """
        while self.connected:
            stat = await self.status()
            if stat == "READY":
                self.trackerstatus = TrackerStatus.READY
            elif stat == "2FACE":
                self.trackerstatus = TrackerStatus.TWOFACE
            elif stat == "ADM":
                self.trackerstatus = TrackerStatus.ADM
            elif stat == "DRIFT":
                self.trackerstatus = TrackerStatus.DRIFT
            elif stat == "EMP":
                self.trackerstatus = TrackerStatus.EMP
            elif stat == "ERR":
                self.trackerstatus = TrackerStatus.ERR
            await asyncio.sleep(1)



    async def wait_for_ready(self):

        wait_states = ("EMP\r\n")
        msg = bytes("?STAT\r\n", 'ascii')
        self.writer.write(msg)
        await self. writer.drain()
        data = await  self.reader.read(64)
        stat = data.decode()
        if stat == "INIT" or stat == "INIT\r\n":
            print("waiting for init")
            await asyncio.sleep(5)
        while stat in wait_states:
            print("...")
            await asyncio.sleep(0.3)
            self.writer.write(msg)
            await self. writer.drain()
            data = await  self.reader.read(64)
            stat = data.decode()
        await asyncio.sleep(0.5)

    async def send_msg(self, msg):
        msg = msg + "\r\n"
        if type(msg) == str:  # this may move
            msg = bytes(msg, 'ascii')
        print(f"sending {msg}")
        self.writer.write(msg)
        await self. writer.drain()
        data = await self.reader.readuntil(separator=bytes("\n", 'ascii'))
        print(f'Received: {data.decode()!r}')
        return data.decode()

    async def status(self):
        response = await self.send_msg("?STAT")
        return response

    async def laser_status(self):
        msg = self.msgformat("?LSTA")
        laser_status_data = await self.send_msg(msg)
        return laser_status_data

    async def laser_on(self):
        msg = "!CMDTLON"
        data = await self.send_msg(msg)
        return data

    async def laser_off(self):
        msg = "!CMDTLOFF"
        data = await self.send_msg(msg)
        return data

    async def measure_m2(self):
        if self.first_measurement:
            print("first measurement, waiting for tracker warmup")
            await asyncio.sleep(5)
            self.first_measurement = False
        print("measure m2")
        msg = "!CMDEXE:M2"
        print(f"waiting for ready before sending {msg}")
        await self.wait_for_ready()
        data = await self.send_msg(msg)
        return data

    async def measure_m1m3(self):
        if self.first_measurement:
            print("first measurement, waiting for tracker warmup")
            await asyncio.sleep(5)
            self.first_measurement = False
        print("measure m1m3")
        msg = "!CMDEXE:M1M3"
        print(f"waiting for ready before sending {msg}")
        await self.wait_for_ready()
        data = await self.send_msg(msg)
        return data

    async def measure_cam(self):
        if self.first_measurement:
            print("first measurement, waiting for tracker warmup")
            await asyncio.sleep(2)
            self.first_measurement = False
        print("measure cam")
        msg = "!CMDEXE:CAM"
        print(f"waiting for ready before sending {msg}")
        await self.wait_for_ready()
        data = await self.send_msg(msg)
        return data

    async def query_m2(self):
        print("query m2")
        msg = "?POS M2"
        data = await self.send_msg(msg)
        return data

    async def query_m1m3(self):
        print("query m1m3")
        msg = "?POS M1M3"
        data = await self.send_msg(msg)
        return data

    async def query_cam(self):
        print("query cam")
        msg = "?POS CAM"
        data = await self.send_msg(msg)
        return data

    async def twoFace_m2(self):
        msg = "?2FACE M2"
        data = await self.send_msg(msg)
        return data

    async def twoFace_m1m3(self):
        msg = "?2FACE M1M3"
        data = await self.send_msg(msg)
        return data

    async def twoFace_cam(self):
        msg = "?2FACE CAM"
        data = await self.send_msg(msg)
        return data

    async def disconnect(self):
        self.writer.close()
        self.connected = False

    def msgformat(self, st):
        '''
        takes a string, converts to bytes, and adds the end-of-line characters
        '''
        msg = bytes(st + "\r\n", 'ascii')
        return msg

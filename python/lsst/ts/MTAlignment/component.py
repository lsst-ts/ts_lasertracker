
import asyncio
from random import randrange
import time


class AscComponent():
    """
         communicates with the T2SA application
    """

    def __init__(self):
        self.server_address = ('140.252.33.138', 50000)
        self.connected = False
        self.reader = None
        self.writer = None
        self.first_measurement = True

    async def connect(self):
        self.reader, self.writer = await asyncio.open_connection(*self.server_address)
    
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
        print("waiting for ready")
        await self.wait_for_ready()
        print("ready received")

        if type(msg) == str:  # this may move
            msg = bytes(msg, 'ascii')
        print(f"writing {msg}")
        self.writer.write(msg)
        await self. writer.drain()
        # data = await self.reader.readuntil(separator=bytes("\n", 'ascii'))
        data = await  self.reader.read(256)
        print(f'Received: {data.decode()!r}')
        return data.decode()

    async def status(self):
        response = await self.send_msg("?STAT")
        return response

    async def statloop(self):
        while True:
            s = await self.status()
            print(s)
            asyncio.sleep(0.2)


    async def laser_status(self):
        msg = self.msgformat("?LSTA")
        laser_status_data = await self.send_msg(msg)
    
    async def laser_on(self):
        msg = "!CMDTLON"
        data = await self.send_msg(msg)


    async def laser_off(self):
        msg = "!CMDTLOFF"
        data = await self.send_msg(msg)


    async def measure_m2(self):
        if self.first_measurement:
            print("first measurement, waiting for tracker warmup")
            await asyncio.sleep(5)
            self.first_measurement = False
        print("measure m2")
        msg = "!CMDEXE:M2"
        data = await self.send_msg(msg)
        await asyncio.sleep(2)

    async def measure_m1m3(self):
        if self.first_measurement:
            print("first measurement, waiting for tracker warmup")
            await asyncio.sleep(5)
            self.first_measurement = False
        print ("measure m1m3")
        msg = "!CMDEXE:M1M3"
        data = await self.send_msg(msg)
        await asyncio.sleep(2)

    async def measure_cam(self):
        if self.first_measurement:
            print("first measurement, waiting for tracker warmup")
            await asyncio.sleep(2)
            self.first_measurement = False
        print("measure cam")
        msg = "!CMDEXE:CAM"
        data = await self.send_msg(msg)
        await asyncio.sleep(5)

    async def query_m2(self):
        print("query m2")
        msg = "?POS M2"
        data = await self.send_msg(msg)

    async def query_m1m3(self):
        print("query m1m3")
        msg = "?POS M1M3"
        data = await self.send_msg(msg)

    async def query_cam(self):
        print("query cam")
        msg = "?POS CAM"
        data = await self.send_msg(msg)

    async def twoFace_m2(self):
        msg = "?2FACE M2"
        data = await self.send_msg(msg)

    async def twoFace_m1m3(self):
        msg = "?2FACE M1M3"
        data = await self.send_msg(msg)

    async def twoFace_cam(self):
        msg = "?2FACE CAM"
        data = await self.send_msg(msg)

    async def apply_correction(self):
        n = 10 
        cam_aligned = False
        m2_aligned = False
        await self.measure_m1m3()
        print("Now is when we would be doing m1m3 fit to fiducials...")
        await asyncio.sleep(5)
        while n > 0:
            if cam_aligned is False:
                await self.measure_cam()
                cam_offset = await self.query_cam()
                if randrange(5) == 4:
                    cam_aligned = True
                    print("cam aligned")
            asyncio.sleep(0.5)
            if m2_aligned == False:
                await self.measure_m2()
                m2_offset = await self.query_m2()
                if randrange(5) == 4:
                    m2_aligned = True
                    print ("M2 aligned")
            n -= 1
            asyncio.sleep(0.5)


    async def disconnect(self):
        self.writer.close()

    def msgformat(self, st):
        '''
        takes a string, converts to bytes, and adds the end-of-line characters
        '''
        msg = bytes(st + "\r\n", 'ascii')
        return msg


import asyncio
import component as com


async def turnLaserOn(self):
    pass


async def turnLaserOff(self):
    pass


async def align_optics(self):

    iteration = 0

    M2_aligned = False
    Cam_aligned = False

    #measure M1M3
    await M1M3_fit_to_fiducials()

    #correction loop
    while not M2_aligned or not Cam_aligned:

        iteration =+ 1

        M2_offsets = await measureM2(iteration)
        Cam_offsets = await measureCam(iteration)

        if M2_out_of_tolerance(M2_offsets):
            M2_apply_corrections(M2_offsets) #command M2 hexapod to move
        else:
            M2_aligned = True

        if Cam_out_of_tolerance(Cam_offsets):
            Cam_apply_corrections(Cam_offsets) #command camera hexapod to move
        else:
            Cam_aligned = True


async def measureM2(self, iteration):
    asyncio.sleep(3)
    com.
    return [1, 2, 3, 4, 5, 6]


async def measureCam(self, iteration):
    asyncio.sleep(3)
    return [1, 2, 3, 4, 5, 6]

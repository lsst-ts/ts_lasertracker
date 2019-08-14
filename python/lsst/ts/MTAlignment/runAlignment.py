import asyncio
from component import AscComponent

def testComponent():
    c = AscComponent()

    c.server_address = ('140.252.33.138', 50000)

    asyncio.get_event_loop().run_until_complete(c.connect())
    asyncio.get_event_loop().run_until_complete(c.apply_correction())


if __name__ == "__main__":
    testComponent()
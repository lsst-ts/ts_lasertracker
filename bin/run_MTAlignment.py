#!/usr/bin/env python
import asyncio
from lsst.ts import asc

asyncio.run(asc.AlignmentCSC.amain(index=None))

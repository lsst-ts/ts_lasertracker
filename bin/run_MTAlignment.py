#!/usr/bin/env python3
import asyncio
from lsst.ts import MTAlignment

asyncio.run(MTAlignment.AlignmentCSC.amain(index=None))

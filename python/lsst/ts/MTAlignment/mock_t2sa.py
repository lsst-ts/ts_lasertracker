__all__ = ["MockT2SA"]

import asyncio

from lsst.ts import utils
from lsst.ts import tcpip

FAILED_ACK = "ACK000"
OK_ACK = "ACK300"


class MockT2SA(tcpip.OneClientServer):
    """Emulate a New River Kinematics T2SA application.

    This is a very simplistic mock with canned replys
    for many commands.

    Parameters
    ----------
    host : `str` or `None`
        IP address for this server; typically `LOCALHOST`
    port : `int`
        IP port for this server. If 0 then randomly pick an available port
        (or ports, if listening on multiple sockets).
        0 is strongly recommended for unit tests.
    log : `logging.Logger`
        Logger; if None create a new one.

    Attributes
    ----------
    host : `str` or `None`
        IP address for this server; typically `LOCALHOST`
    port : `int`
        IP port for this server. If this mock was constructed with port=0
        then this will be the assigned port, once `start` is done.
    """

    # How long to wait while pretending to measure (seconds)
    measurement_duration = 2

    def __init__(self, log, host="127.0.0.1", port=0):
        self.reader = None
        self.writer = None
        self.run_loop_flag = True
        self.measure_task = utils.make_done_future()
        self.reply_loop_task = utils.make_done_future()
        self.canned_replies = {
            "?POS M1M3": "RefFrame:A;X:-7.812891;Y:6.121484;Z:6.846499;"
            + "Rx:41.406838;Ry:19.410126;Rz:-14.458803;03/05/2020 17:05:05",
            "?POS CAM": "<cam_coordinates>",
            "?POS M2": "RefFrame:FRAMEM1M3;X:14.782662;Y:216.367336;Z:1384.403204;"
            + "Rx:0.607295;Ry:-1.374755;Rz:-1.822576;07/22/2021 18:20:21",
            "?OFFSET M1M3": "<m1m3_offset>",
            "?OFFSET CAM": "<cam_offset>",
            "?OFFSET M2": "<m2_offset>",
            "?LSTA": "LON",
            "!LST:0": "ACK300",
            "!LST:1": "ACK300",
            "SET_RANDOMIZE_POINTS:1": "ACK300",
            "SET_RANDOMIZE_POINTS:0": "ACK300",
            "!SET_SIM:0": "ACK300",
            "!SET_SIM:1": "ACK300",
        }
        self.comamnd_handlers = {
            "?STAT": self.do_status,
            "!CMDEXE:M1M3": self.do_measure,
            "!CMDEXE:CAM": self.do_measure,
            "!CMDEXE:M2": self.do_measure,
        }

        duplicate_keys = self.comamnd_handlers.keys() & self.canned_replies.keys()
        if duplicate_keys:
            raise RuntimeError(
                f"Bug: keys {duplicate_keys} appear in both "
                "canned_replies and comamnd_handlers"
            )

        super().__init__(
            name="MockT2SA",
            host=host,
            port=port,
            connect_callback=self.run_reply_loop,
            log=log,
        )

    @property
    def measuring(self):
        """Returning true if executing a measurement plan."""
        return not self.measure_task.done()

    async def do_measure(self):
        """Pretend to execute a measurment plan.

        Acknowledge the request to measure, then pretend to measure.
        """

        self.log.debug("begin measuring")
        # Schedule task that will emulate measurement in the background
        if self.measuring:
            await self.write_reply(FAILED_ACK)
        else:
            self.measure_task = asyncio.create_task(self.measure())
            await self.write_reply(OK_ACK)

    async def do_status(self):
        """Return status.

        While pretend measuring is happening, status should return
        "EMP" -- Executing Measurement Plan
        """

        if self.measuring:
            await self.write_reply("EMP")
        else:
            await self.write_reply("READY")

    def run_reply_loop(self, server):
        self.reply_loop_task.cancel()
        if self.connected:
            self.reply_loop_task = asyncio.create_task(self.reply_loop())

    async def reply_loop(self):
        """Listen for commands and issue replies."""

        self.log.debug("reply loop begins")
        try:
            while self.connected:
                cmd_bytes = await self.reader.readline()
                self.log.debug(f"Mock T2SA received cmd: {cmd_bytes}")
                if not cmd_bytes:
                    self.log.info(
                        "read loop ending; null data read indicates client hung up"
                    )
                    break

                cmd = cmd_bytes.decode().strip()
                if not cmd:
                    continue

                comamnd_handler = self.comamnd_handlers.get(cmd)
                if comamnd_handler:
                    await comamnd_handler()
                else:
                    canned_reply = self.canned_replies.get(cmd)
                    if canned_reply:
                        await self.write_reply(canned_reply)
                    else:
                        self.log.error(f"Unsupported command {cmd!r}")
                        await self.write_reply(FAILED_ACK)
        except asyncio.CancelledError:
            pass
        except (asyncio.IncompleteReadError, ConnectionResetError):
            self.log.info("reply loop ending; connection lost")
        except Exception:
            self.log.exception("reply loop failed")
        self.log.debug("reply loop ends")
        asyncio.create_task(self.close_client())

    async def measure(self):
        """Emulate measurement plan."""
        self.log.debug("start pretending to measure")
        await asyncio.sleep(self.measurement_duration)
        self.log.debug("stop pretending to measure")

    async def write_reply(self, reply):
        """Write a reply to the client.

        Parameters
        ----------
        reply : `str`
            The reply (without a trailing "\r\n")
        """
        self.writer.write(reply.encode() + tcpip.TERMINATOR)
        await self.writer.drain()

import logging
from asyncio import sleep

import pyartnet
from homeassistant.core import HomeAssistant
from pyartnet import BaseUniverse
from pyartnet.base import BaseNode
from pyartnet.base.base_node import TYPE_U
from pyartnet.errors import InvalidUniverseAddressError

from custom_components.artnet_led.client import PortAddress
from custom_components.artnet_led.client.artnet_server import ArtNetServer

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

HA_OEM = 0x2BE9


class ArtNetController(BaseNode):
    NET = 0  # Library doesn't support others yet
    SUB_NET = 0  # Library doesn't support others yet

    def __init__(self, hass: HomeAssistant, max_fps: int = 25, refresh_every: int = 2):
        super().__init__("", 0, max_fps=max_fps, refresh_every=0, start_refresh_task=False)

        self._hass = hass

        self.__server = ArtNetServer(hass, state_update_callback=self.update_dmx_data, oem=HA_OEM,
                                     short_name="ha-artnet-led", long_name="HomeAssistant ArtNet integration",
                                     retransmit_time_ms=int(refresh_every / 1000.0)
                                     )

    def _send_universe(self, id: int, byte_size: int, values: bytearray, universe: pyartnet.impl_artnet.ArtNetUniverse):
        log.debug(f"Going to send universe {universe._universe}: {universe._data.hex()}")
        self.__server.send_dmx(PortAddress(self.NET, self.SUB_NET, universe._universe), universe._data)

    def _create_universe(self, nr: int) -> TYPE_U:
        if nr >= 32_768:
            raise InvalidUniverseAddressError()
        return pyartnet.impl_artnet.ArtNetUniverse(self, nr)

    def add_universe(self, nr: int = 0) -> BaseUniverse:
        dmx_universe = super().add_universe(nr)

        self.__server.add_port(PortAddress(self.NET, self.SUB_NET, nr))
        return dmx_universe

    async def start(self):
        return self.__server.start_server()

    def update_dmx_data(self, address: PortAddress, data: bytearray):
        assert address.net == self.NET
        assert address.sub_net == self.SUB_NET

        self.get_universe(address.universe).data = data
#         TODO schedule HA state update

    async def _process_values_task(self):
        log.debug(f"Processing values changed")
        idle_ct = 0
        while idle_ct < 10:
            idle_ct += 1

            # process jobs
            to_remove = []
            for job in self._process_jobs:
                job.process()
                idle_ct = 0

                if job.is_done:
                    to_remove.append(job)

            # send data of universe
            for universe in self._universes:
                if not universe._data_changed:
                    continue
                universe.send_data()
                idle_ct = 0

            if to_remove:
                for job in to_remove:
                    self._process_jobs.remove(job)
                    job.fade_complete()

            await sleep(self._process_every)

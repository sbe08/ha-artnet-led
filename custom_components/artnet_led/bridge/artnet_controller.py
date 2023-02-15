from homeassistant.core import HomeAssistant
from pyartnet import BaseUniverse
from pyartnet.base import BaseNode
from pyartnet.base.base_node import TYPE_U

from custom_components.artnet_led.client import PortAddress
from custom_components.artnet_led.client.artnet_server import ArtNetServer

HA_OEM = 0x2BE9


class ArtNetController(BaseNode):
    def _send_universe(self, id: int, byte_size: int, values: bytearray, universe: TYPE_U):
        pass

    def _create_universe(self, nr: int) -> TYPE_U:
        pass

    NET = 0  # Library doesn't support others yet
    SUB_NET = 0  # Library doesn't support others yet

    def __init__(self, hass: HomeAssistant, max_fps: int = 25, refresh_every: int = 2):
        super().__init__("", 0, max_fps=max_fps, refresh_every=0, start_refresh_task=False)

        self.__server = ArtNetServer(hass, state_update_callback=self.update_dmx_data, oem=HA_OEM,
                                     short_name="ha-artnet-led", long_name="HomeAssistant ArtNet integration",
                                     retransmit_time_ms=int(refresh_every / 1000.0)
                                     )

    def update(self):
        for universe_nr, universe in enumerate(self._universes):
            self.__server.send_dmx(PortAddress(self.NET, self.SUB_NET, universe_nr), universe.data)

    def add_universe(self, nr: int = 0) -> BaseUniverse:
        dmx_universe = super().add_universe(nr)

        self.__server.add_port(PortAddress(self.NET, self.SUB_NET, nr))
        return dmx_universe

    async def start(self):
        self.__server.start_server()

    def update_dmx_data(self, address: PortAddress, data: bytearray):
        assert address.net == self.NET
        assert address.sub_net == self.SUB_NET

        self.get_universe(address.universe).data = data
#         TODO schedule HA state update

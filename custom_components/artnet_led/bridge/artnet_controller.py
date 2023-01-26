from homeassistant.core import HomeAssistant
from pyartnet import ArtNetNode, DmxUniverse

from custom_components.artnet_led.client import PortAddress
from custom_components.artnet_led.client.artnet_server import ArtNetServer

HA_OEM = 0x2BE9


class ArtNetController(ArtNetNode):
    NET = 0  # Library doesn't support others yet
    SUB_NET = 0  # Library doesn't support others yet

    def __init__(self, hass: HomeAssistant, max_fps: int = 25, refresh_every: int = 2):
        super().__init__("", max_fps=max_fps, refresh_every=0)

        self.__server = ArtNetServer(hass, state_update_callback=self.update_dmx_data, oem=HA_OEM,
                                     short_name="ha-artnet-led", long_name="HomeAssistant ArtNet integration",
                                     retransmit_time_ms=int(refresh_every / 1000.0)
                                     )

    def update(self):
        for universe_nr, universe in self.__universe.items():
            self.__server.send_dmx(PortAddress(self.NET, self.SUB_NET, universe_nr), universe.data)

    def add_universe(self, nr: int = 0) -> DmxUniverse:
        dmx_universe = super().add_universe(nr)

        self.__server.add_port(PortAddress(self.NET, self.SUB_NET, nr))
        return dmx_universe

    async def start(self):
        await super().start()
        self.__server.start_server()

    def update_dmx_data(self, address: PortAddress, data: bytearray):
        assert address.net == self.NET
        assert address.sub_net == self.SUB_NET

        self.get_universe(address.universe).data = data
#         TODO schedule HA state update

from __future__ import annotations

import asyncio
import logging
import time
from array import array
from typing import Union

import homeassistant.helpers.config_validation as cv
import homeassistant.util.color as color_util
import pyartnet
import voluptuous as vol
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_RGB_COLOR,
    ATTR_RGBW_COLOR,
    ATTR_RGBWW_COLOR,
    ATTR_TRANSITION,
    PLATFORM_SCHEMA,
    LightEntity, ATTR_WHITE, ATTR_COLOR_TEMP_KELVIN, ATTR_FLASH,
    FLASH_SHORT, FLASH_LONG, ATTR_HS_COLOR, LightEntityFeature, ColorMode)
from homeassistant.const import CONF_DEVICES, STATE_OFF, STATE_ON
from homeassistant.const import CONF_FRIENDLY_NAME as CONF_DEVICE_FRIENDLY_NAME
from homeassistant.const import CONF_HOST as CONF_NODE_HOST
from homeassistant.const import CONF_NAME as CONF_DEVICE_NAME
from homeassistant.const import CONF_PORT as CONF_NODE_PORT
from homeassistant.const import CONF_TYPE as CONF_DEVICE_TYPE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_registry import async_get
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util.color import color_rgb_to_rgbw
from pyartnet import BaseUniverse, Channel
from pyartnet.errors import UniverseNotFoundError

from custom_components.artnet_led.bridge.artnet_controller import ArtNetController
from custom_components.artnet_led.bridge.channel_bridge import ChannelBridge
from custom_components.artnet_led.util.channel_switch import validate, to_values, from_values

ARTNET_DEFAULT_PORT = 6454
SACN_DEFAULT_PORT = 5568
KINET_DEFAULT_PORT = 6038

CONF_DEVICE_TRANSITION = ATTR_TRANSITION

CONF_SEND_PARTIAL_UNIVERSE = "send_partial_universe"

log = logging.getLogger(__name__)

CONF_NODE_HOST_OVERRIDE = "host_override"
CONF_NODE_PORT_OVERRIDE = "port_override"

CONF_NODE_TYPE = "node_type"
CONF_NODE_MAX_FPS = "max_fps"
CONF_NODE_REFRESH = "refresh_every"
CONF_NODE_UNIVERSES = "universes"

CONF_DEVICE_CHANNEL = "channel"
CONF_OUTPUT_CORRECTION = "output_correction"
CONF_CHANNEL_SIZE = "channel_size"
CONF_BYTE_ORDER = "byte_order"

CONF_DEVICE_MIN_TEMP = "min_temp"
CONF_DEVICE_MAX_TEMP = "max_temp"
CONF_CHANNEL_SETUP = "channel_setup"


CONF_SWAP_GREEN_BLUE = "swap_green_blue"
CONF_RGB_OFFSETS = "rgb_offsets"


DOMAIN = "dmx"

AVAILABLE_CORRECTIONS = {"linear": pyartnet.output_correction.linear, "quadratic": pyartnet.output_correction.quadratic,
                         "cubic": pyartnet.output_correction.cubic, "quadruple": pyartnet.output_correction.quadruple}

CHANNEL_SIZE = {
    "8bit": (1, 1),
    "16bit": (2, 256),
    "24bit": (3, 256 ** 2),
    "32bit": (4, 256 ** 3),
}

NODES = {}


async def async_setup_platform(hass: HomeAssistant, config, async_add_devices, discovery_info=None):
    pyartnet.base.CREATE_TASK = hass.async_create_task

    client_type = config.get(CONF_NODE_TYPE)
    max_fps = config.get(CONF_NODE_MAX_FPS)
    refresh_interval = config.get(CONF_NODE_REFRESH)

    host = config.get(CONF_NODE_HOST)
    port = config.get(CONF_NODE_PORT)

    real_host = config.get(CONF_NODE_HOST_OVERRIDE)
    if len(real_host) == 0:
        real_host = host
    real_port = config.get(CONF_NODE_PORT_OVERRIDE)
    if real_port is None:
        real_port = port

    # setup Node
    node: pyartnet.base.BaseNode
    if client_type == "artnet-direct":
        if real_port is None:
            real_port = ARTNET_DEFAULT_PORT

        __id = f"{host}:{port}"
        if __id not in NODES:
            __node = pyartnet.ArtNetNode(
                real_host,
                real_port,
                max_fps=max_fps,
                refresh_every=refresh_interval,
                start_refresh_task=(refresh_interval > 0),
                sequence_counter=True
            )
            NODES[__id] = __node

        node = NODES[__id]

    elif client_type == "artnet-controller":
        if "server" not in NODES:
            __node = ArtNetController(hass, max_fps=max_fps, refresh_every=refresh_interval)
            NODES["server"] = __node
            __node.start()
        node = NODES["server"]

    elif client_type == "sacn":
        if real_port is None:
            real_port = SACN_DEFAULT_PORT

        __id = f"{host}:{port}"
        if __id not in NODES:
            __node = pyartnet.SacnNode(
                real_host,
                real_port,
                max_fps=max_fps,
                refresh_every=refresh_interval,
                start_refresh_task=(refresh_interval > 0),
                source_name="ha-artnet-led"
            )
            NODES[__id] = __node

        node = NODES[__id]
    elif client_type == "kinet":
        if real_port is None:
            real_port = KINET_DEFAULT_PORT

        __id = f"{host}:{port}"
        if __id not in NODES:
            __node = pyartnet.KiNetNode(
                real_host,
                real_port,
                max_fps=max_fps,
                refresh_every=refresh_interval,
                start_refresh_task=(refresh_interval > 0),
            )
            NODES[__id] = __node

        node = NODES[__id]

    else:
        raise NotImplementedError(f"Unknown client type '{client_type}'")

    entity_registry = async_get(hass)

    device_list = []
    used_unique_ids = []
    for universe_nr, universe_cfg in config[CONF_NODE_UNIVERSES].items():
        try:
            universe = node.get_universe(universe_nr)
        except UniverseNotFoundError:
            universe: BaseUniverse = node.add_universe(universe_nr)
            universe.output_correction = AVAILABLE_CORRECTIONS.get(
                universe_cfg[CONF_OUTPUT_CORRECTION]
            )

        for device in universe_cfg[CONF_DEVICES]:  # type: dict
            device = device.copy()
            cls = __CLASS_TYPE[device[CONF_DEVICE_TYPE]]

            channel = device[CONF_DEVICE_CHANNEL]
            unique_id = f"{DOMAIN}:{host}/{universe_nr}/{channel}"

            name: str = device[CONF_DEVICE_NAME]
            byte_size = CHANNEL_SIZE[device[CONF_CHANNEL_SIZE]][0]
            byte_order = device[CONF_BYTE_ORDER]

            entity_id = f"light.{name.replace(' ', '_').lower()}"

            # Use existing entity's unique_id if available.
            entity = entity_registry.async_get(entity_id)
            if entity:
                log.info(f"Found existing entity for name {entity_id}, using unique id {unique_id}")
                if entity.unique_id is not None and entity.unique_id not in used_unique_ids:
                    unique_id = entity.unique_id
            used_unique_ids.append(unique_id)

            # Set new default options.
            device.setdefault(CONF_SWAP_GREEN_BLUE, False)
            device.setdefault(CONF_RGB_OFFSETS, [0, 1, 2])

            # Create device.
            device["unique_id"] = unique_id
            d = cls(**device)  # type: DmxBaseLight
            d.set_type(device[CONF_DEVICE_TYPE])
            
            ################################################################
            # NEW: group_dimmer logic:
            ################################################################
            if device[CONF_DEVICE_TYPE] == "group_dimmer":
                group_count = device.get("group_count", 1)
                channels = []
                for i in range(group_count):
                    ch = universe.add_channel(
                        start=(channel + i),
                        width=1,
                        channel_name=f"{name}_ch{i+1}",
                        byte_size=byte_size,
                        byte_order=byte_order,
                    )
                    channels.append(ch)
                d.set_group_channels(channels)


            ################################################################
            # NEW Group RGB Logic):
            ################################################################
                
            elif device[CONF_DEVICE_TYPE] == "group_rgb":
                group_count = device.get("group_count", 1)
                rgb_offsets = device.get(CONF_RGB_OFFSETS, [0, 1, 2])
                # Decide how much to move for each sub-fixture:
                # - If offsets == [0,1,2], that means standard consecutive R/G/B,
                #   so each sub-fixture is 3 channels apart (3*i).
                # - If offsets != [0,1,2], user likely has large offsets,
                #   so each sub-fixture only moves +1 (i).
                if rgb_offsets == [0, 1, 2]:
                    sub_fixture_spacing = 3
                else:
                    sub_fixture_spacing = 1
            
                channels = []
                for i in range(group_count):
                    r_chan = universe.add_channel(
                        start=(channel + sub_fixture_spacing * i + rgb_offsets[0]),
                        width=1,
                        channel_name=f"{name}_R{i+1}",
                        byte_size=byte_size,
                        byte_order=byte_order,
                    )
                    g_chan = universe.add_channel(
                        start=(channel + sub_fixture_spacing * i + rgb_offsets[1]),
                        width=1,
                        channel_name=f"{name}_G{i+1}",
                        byte_size=byte_size,
                        byte_order=byte_order,
                    )
                    b_chan = universe.add_channel(
                        start=(channel + sub_fixture_spacing * i + rgb_offsets[2]),
                        width=1,
                        channel_name=f"{name}_B{i+1}",
                        byte_size=byte_size,
                        byte_order=byte_order,
                    )
                    channels.extend([r_chan, g_chan, b_chan])
            
                d.set_group_channels(channels)
                
            ################################################################
            # Existing logic for separate-channels (e.g. RGB with offsets):
            ################################################################
            elif device[CONF_DEVICE_TYPE] == "rgb":
                # Check the RGB offsets.
                rgb_offsets = device.get(CONF_RGB_OFFSETS, [0, 1, 2])
                if rgb_offsets != [0, 1, 2]:
                    red_channel = universe.add_channel(
                        start=channel + rgb_offsets[0] - 1,
                        width=1,
                        channel_name=f"{name}_red",
                        byte_size=byte_size,
                        byte_order=byte_order,
                    )
                    green_channel = universe.add_channel(
                        start=channel + rgb_offsets[1] - 1,
                        width=1,
                        channel_name=f"{name}_green",
                        byte_size=byte_size,
                        byte_order=byte_order,
                    )
                    blue_channel = universe.add_channel(
                        start=channel + rgb_offsets[2] - 1,
                        width=1,
                        channel_name=f"{name}_blue",
                        byte_size=byte_size,
                        byte_order=byte_order,
                    )
                    # e.g. d.set_color_channels(red_channel, green_channel, blue_channel)
                    if hasattr(d, "set_color_channels"):
                        d.set_color_channels(red_channel, green_channel, blue_channel)
                else:
                    # Unified mode for an RGB device. 
                    if d.channel_width <= 0:
                        d._channel_width = 3
                    ch = universe.add_channel(
                        start=channel,
                        width=d.channel_width,
                        channel_name=d.name,
                        byte_size=byte_size,
                        byte_order=byte_order,
                    )
                    d.set_channel(ch)

                    if hasattr(d.channel, "output_correction"):
                        d.channel.output_correction = AVAILABLE_CORRECTIONS.get(device[CONF_OUTPUT_CORRECTION])

            ################################################################
            # Otherwise, default logic (e.g. normal dimmer, color_temp, etc.)
            ################################################################
            else:
                # If the device is something else (e.g., "dimmer"), 
                # we do the standard approach: create a single channel
                if d.channel_width <= 0:
                    # For a basic dimmer, typically 1 channel
                    d._channel_width = 1
                ch = universe.add_channel(
                    start=channel,
                    width=d.channel_width,
                    channel_name=d.name,
                    byte_size=byte_size,
                    byte_order=byte_order,
                )
                d.set_channel(ch)

                if hasattr(d.channel, "output_correction"):
                    d.channel.output_correction = AVAILABLE_CORRECTIONS.get(device[CONF_OUTPUT_CORRECTION])
            
            device_list.append(d)

            send_partial_universe = universe_cfg[CONF_SEND_PARTIAL_UNIVERSE]
            if not send_partial_universe:
                universe._resize_universe(512)

    async_add_devices(device_list)

    return True


def convert_to_kelvin(kelvin_string) -> int:
    return int(kelvin_string[:-1])


class DmxBaseLight(LightEntity, RestoreEntity):
    def __init__(self, name, unique_id: str, **kwargs):
        self._name = name
        self._channel: Union[Channel, ChannelBridge] = kwargs[CONF_DEVICE_CHANNEL]

        self._unique_id = unique_id

        self.entity_id = f"light.{name.replace(' ', '_').lower()}"
        self._attr_brightness = 255
        self._fade_time = kwargs[CONF_DEVICE_TRANSITION]
        self._state = False
        self._channel_size = CHANNEL_SIZE[kwargs[CONF_CHANNEL_SIZE]]
        self._color_mode = kwargs[CONF_DEVICE_TYPE]
        self._vals = []
        self._features = 0
        self._supported_color_modes = set()
        self._channel_last_update = 0
        self._channel_width = 0
        self._type = None

        self._channel: pyartnet.base.Channel

    def set_channel(self, channel: pyartnet.base.Channel):
        """Set the channel"""
        self._channel = channel
        self._channel.callback_fade_finished = self._channel_fade_finish

        if isinstance(channel, ChannelBridge):
            channel.callback_values_updated = self._update_values

    def set_type(self, type):
        self._type = type

    @property
    def name(self):
        """Return the display name of this light."""
        return self._name

    @property
    def unique_id(self):
        """Return unique ID for light."""
        return self._unique_id

    @property
    def color_mode(self) -> str | None:
        """Return the color mode of the light."""
        return self._color_mode

    @property
    def supported_features(self):
        """Flag supported features."""
        return self._features

    @property
    def extra_state_attributes(self):
        data = {
            "type": self._type,
            "values": self._vals,
            "bright": self._attr_brightness
        }
        try:
            # Check if separate channels are being used.
            if hasattr(self, "_red_channel") and self._red_channel is not None:
                data["dmx_channels"] = {
                    "red": getattr(self._red_channel, "_start", None),
                    "green": getattr(self._green_channel, "_start", None),
                    "blue": getattr(self._blue_channel, "_start", None)
                }
                # Retrieve the DMX values from each channel, if available.
                data["dmx_values"] = {
                    "red": self._red_channel.get_values() if hasattr(self._red_channel, "get_values") else None,
                    "green": self._green_channel.get_values() if hasattr(self._green_channel, "get_values") else None,
                    "blue": self._blue_channel.get_values() if hasattr(self._blue_channel, "get_values") else None
                }
            elif hasattr(self, "_channel") and hasattr(self._channel, "_start"):
                # Unified (single-channel) mode.
                data["dmx_channels"] = [
                    k for k in range(
                        self._channel._start, self._channel._start + self._channel._width, 1
                    )
                ]
                data["dmx_values"] = self._channel.get_values()
            else:
                data["dmx_channels"] = None
                data["dmx_values"] = None
        except Exception as e:
            log.exception("Error computing extra_state_attributes: %s", e)
        self._channel_last_update = time.time()
        return data

    @property
    def is_on(self):
        """Return true if light is on."""
        return self._state

    @property
    def should_poll(self):
        return False

    @property
    def supported_color_modes(self) -> set | None:
        """Flag supported color modes."""
        return self._supported_color_modes

    @property
    def fade_time(self):
        return self._fade_time

    @fade_time.setter
    def fade_time(self, value):
        self._fade_time = value

    def _update_values(self, values: array[int]):
        assert len(values) == len(self._vals)
        self._vals = tuple(values)

        self._channel_value_change()

    def _channel_value_change(self):
        """Schedule update while fade is running"""
        if time.time() - self._channel_last_update > 1.1:
            self._channel_last_update = time.time()
        self.async_schedule_update_ha_state()

    def _channel_fade_finish(self, channel):
        """Fade is finished -> schedule update"""
        self._channel_last_update = time.time()
        self.async_schedule_update_ha_state()

    @staticmethod
    def _default_calculation_function(channel_value):
        return channel_value if isinstance(channel_value, int) else 0

    def get_target_values(self) -> list:
        """Return the Target DMX Values"""
        raise NotImplementedError()

    async def flash(self, old_values, old_brightness, **kwargs):
        transition = kwargs.get(ATTR_TRANSITION, self._fade_time)
        if transition == 0:
            transition = 1

        old_state = self._state
        self._state = True

        flash_time = kwargs.get(ATTR_FLASH)

        if old_state and old_values == self._vals and old_brightness == self._attr_brightness:
            if self._attr_brightness < 128:
                self._attr_brightness = 255
            else:
                self._attr_brightness = 0

        if flash_time == FLASH_SHORT:
            self._channel.set_values(self.get_target_values())
            await self._channel
        elif flash_time == FLASH_LONG:
            self._channel.set_fade(self.get_target_values(), transition * 1000)
            await self._channel
        else:
            log.error(f"{flash_time} is not a valid value for attribute {ATTR_FLASH}")
            return

        self._state = old_state
        self._attr_brightness = old_brightness
        self._vals = old_values

        self._channel.set_fade(self.get_target_values(), transition * 1000)

    async def async_create_fade(self, **kwargs):
        """
        Instruct the light to turn on with fade.
        Handles both:
          - A single DMX channel (e.g. a dimmer or dimmer group).
          - Three DMX channels (e.g. an RGB light with separate channels).
        """
        self._state = True
        transition = kwargs.get(ATTR_TRANSITION, self._fade_time)
        target_vals = self.get_target_values()
    
        if len(target_vals) == 3 and hasattr(self, "_red_channel") and self._red_channel is not None:
            # We have an RGB-style setup with separate channels.
            # Apply brightness scaling if needed.
            red, green, blue = target_vals
            if self._attr_brightness < 255:
                red = int(red * self._attr_brightness / 255)
                green = int(green * self._attr_brightness / 255)
                blue = int(blue * self._attr_brightness / 255)
    
            # Send fade commands to each color channel.
            self._red_channel.set_fade([red], transition * 1000)
            self._green_channel.set_fade([green], transition * 1000)
            self._blue_channel.set_fade([blue], transition * 1000)
    
        elif len(target_vals) == 1 and hasattr(self, "_channel") and self._channel is not None:
            # We have a single-channel device (e.g. dimmer).
            val = target_vals[0]
            if self._attr_brightness < 255:
                val = int(val * self._attr_brightness / 255)
    
            # Send fade command to single DMX channel.
            if transition > 0:
                self._channel.set_fade([val], transition * 1000)
            else:
                self._channel.set_values([val])
    
        else:
            # You could either log a warning or handle other multi-channel cases.
            log.warning("Unhandled channel configuration in async_create_fade. "
                        f"target_vals={target_vals}")
    
        self.async_schedule_update_ha_state()
        
    async def async_turn_off(self, **kwargs):
        """
        Instruct the light to turn off. If a transition time has been specified in seconds
        the controller will fade.
        """
        transition = kwargs.get(ATTR_TRANSITION, self._fade_time)

        self._channel.set_fade(
            [0 for _ in range(self._channel._width)],
            transition * 1000
        )

        self._state = False
        self.async_schedule_update_ha_state()

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        old_state = await self.async_get_last_state()
        if old_state:
            old_type = old_state.attributes.get('type')
            if old_type != self._type:
                log.debug("Channel type changed. Unable to restore state.")
                old_state = None

        if old_state is not None:
            await self.restore_state(old_state)

    async def restore_state(self, old_state):
        log.error("Derived class should implement this. Report this to the repository author.")

    @property
    def channel_width(self):
        return self._channel_width

    @property
    def channel_size(self):
        return self._channel_size

    @property
    def channel(self):
        return self._channel


class DmxFixed(DmxBaseLight):
    CONF_TYPE = "fixed"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._color_mode = ColorMode.ONOFF
        self._channel_setup = kwargs.get(CONF_CHANNEL_SETUP) or [255]
        self._channel_width = len(self._channel_setup)

    def get_target_values(self):
        return to_values(self._channel_setup, self._channel_size[1], self.is_on, self._attr_brightness)

    def set_channel(self, channel: pyartnet.base.Channel):
        super().set_channel(channel)
        channel.set_values(self.get_target_values())

    async def async_turn_on(self, **kwargs):
        pass  # do nothing, fixed is constant value

    async def async_turn_off(self, **kwargs):
        pass  # do nothing, fixed is constant value

    async def restore_state(self, old_state):
        log.debug("Added fixed to hass. Do nothing to restore state. Fixed is constant value")
        await super().async_create_fade()


class DmxBinary(DmxBaseLight):
    CONF_TYPE = "binary"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._channel_width = 1
        self._features = LightEntityFeature.FLASH
        self._color_mode = ColorMode.ONOFF
        self._supported_color_modes.add(ColorMode.ONOFF)

    def _update_values(self, values: array[int]):
        self._state, _, _, _, _, _, _, color_temp = from_values("d", self.channel_size[1], values)

        self._channel_value_change()

    def get_target_values(self):
        return [self.brightness * self._channel_size[1]]

    async def async_turn_on(self, **kwargs):
        if ATTR_FLASH in kwargs:
            flash_time = kwargs[ATTR_FLASH]
            if flash_time == FLASH_SHORT:
                duration = 0.5
            else:
                duration = 2.0

            await self.flash_binary(duration)
            return

        self._state = True
        self._attr_brightness = 255
        self._channel.set_fade(
            self.get_target_values(), 0
        )
        self.async_schedule_update_ha_state()

    async def flash_binary(self, duration: float):
        self._state = not self._state
        self._attr_brightness = 255 if self._state else 0
        self._channel.set_fade(
            self.get_target_values(), 0
        )
        await asyncio.sleep(duration)
        self._state = not self._state
        self._attr_brightness = 255 if self._state else 0
        self._channel.set_fade(
            self.get_target_values(), 0
        )

    async def async_turn_off(self, **kwargs):
        self._state = False
        self._attr_brightness = 0
        self._channel.set_fade(
            self.get_target_values(), 0
        )
        self.async_schedule_update_ha_state()

    async def restore_state(self, old_state):
        log.debug("Added binary light to hass. Try restoring state.")
        self._state = old_state.state
        self._attr_brightness = old_state.attributes.get('bright')

        if old_state.state == STATE_ON:
            await self.async_turn_on()
        else:
            await self.async_turn_off()


class DmxDimmer(DmxBaseLight):
    CONF_TYPE = "dimmer"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._channel_width = 1
        self._features = LightEntityFeature.TRANSITION | LightEntityFeature.FLASH
        self._color_mode = ColorMode.BRIGHTNESS
        self._supported_color_modes.add(ColorMode.BRIGHTNESS)
        self._channel_setup = kwargs.get(CONF_CHANNEL_SETUP) or "d"
        validate(self._channel_setup, self.CONF_TYPE)

    def _update_values(self, values: array[int]):
        self._state, self._attr_brightness, _, _, _, _, _, _ = \
            from_values(self._channel_setup, self.channel_size[1], values)

        self._channel_value_change()

    def get_target_values(self):
        return to_values(self._channel_setup, self._channel_size[1], self.is_on, self._attr_brightness)

    async def async_create_fade(self, **kwargs):
        """
        Override the base logic which assumes 3 channels.
        Dimmer only has a single channel to fade.
        """
        self._state = True
        transition = kwargs.get(ATTR_TRANSITION, self._fade_time)
        target_values = self.get_target_values()  # e.g. [brightness]

        if transition > 0:
            self._channel.set_fade(target_values, transition * 1000)
        else:
            self._channel.set_values(target_values)

        self.async_schedule_update_ha_state()
        
    async def async_turn_on(self, **kwargs):

        # Update state from service call
        if ATTR_BRIGHTNESS in kwargs:
            self._attr_brightness = kwargs[ATTR_BRIGHTNESS]

        await super().async_create_fade(**kwargs)

    async def restore_state(self, old_state):
        log.debug("Added dimmer to hass. Try restoring state.")

        if old_state:
            prev_brightness = old_state.attributes.get('bright')
            self._attr_brightness = prev_brightness

        if old_state.state != STATE_OFF:
            await super().async_create_fade(brightness=self._attr_brightness, transition=0)

class DmxDimmerGroup(DmxBaseLight):
    CONF_TYPE = "group_dimmer"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._channel_width = 1
        self._features = LightEntityFeature.TRANSITION
        self._color_mode = ColorMode.BRIGHTNESS
        self._supported_color_modes.add(ColorMode.BRIGHTNESS)

        self._group_count = kwargs.get("group_count", 1)
        # Always define the attribute here, so it exists even before set_group_channels() is called
        self._dimmer_channels: list[pyartnet.base.Channel] = []

    def set_group_channels(self, channels: list[pyartnet.base.Channel]):
        """Called from async_setup_platform to store all DMX channels for this group."""
        self._dimmer_channels = channels
        # If you want to do anything with each channel (like set callbacks), do it here:
        for ch in channels:
            if isinstance(ch, ChannelBridge):
                ch.callback_values_updated = self._update_values

    def set_channel(self, channel: pyartnet.base.Channel):
        """
        Overridden to do nothing since we're controlling multiple sub-channels.
        The base code sometimes calls set_channel, so we define it but leave it blank.
        """
        pass

    def _update_values(self, values: array[int]):
        # If you need to react when a sub-channel updates, handle it here
        self._channel_value_change()

    def get_target_values(self) -> list[int]:
        """Return a brightness value for each channel in the group."""
        if not self._state:
            # Off => all zero
            return [0] * len(self._dimmer_channels)
        # On => each channel uses the same brightness
        return [self._attr_brightness] * len(self._dimmer_channels)

    async def restore_state(self, old_state):
        """Re-apply brightness/on-off status after HA restart."""
        log.debug("Restoring state for group dimmer '%s': %s", self._name, old_state)

        if old_state:
            prev_brightness = old_state.attributes.get('bright')
            if prev_brightness is not None:
                self._attr_brightness = prev_brightness
            if old_state.state.lower() == STATE_OFF:
                self._state = False
            else:
                self._state = True

        await self.async_create_fade()

    async def async_turn_on(self, **kwargs):
        self._state = True
        if ATTR_BRIGHTNESS in kwargs:
            self._attr_brightness = kwargs[ATTR_BRIGHTNESS]
        await self.async_create_fade(**kwargs)

    async def async_turn_off(self, **kwargs):
        self._state = False
        await self.async_create_fade(**kwargs)

    async def async_create_fade(self, **kwargs):
        """
        Override the base fade to handle multiple addresses rather than a single or triple.
        """
        transition = kwargs.get(ATTR_TRANSITION, self._fade_time)
        target_values = self.get_target_values()

        for channel, val in zip(self._dimmer_channels, target_values):
            if transition > 0:
                channel.set_fade([val], transition * 1000)
            else:
                channel.set_values([val])

        self.async_schedule_update_ha_state()
        
class DmxWhite(DmxBaseLight):
    CONF_TYPE = "color_temp"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._features = LightEntityFeature.TRANSITION | LightEntityFeature.FLASH

        self._color_mode = ColorMode.COLOR_TEMP
        self._supported_color_modes.add(ColorMode.COLOR_TEMP)
        # Intentionally switching min and max here; it's inverted in the conversion.

        self._min_kelvin = convert_to_kelvin(kwargs[CONF_DEVICE_MIN_TEMP])
        self._max_kelvin = convert_to_kelvin(kwargs[CONF_DEVICE_MAX_TEMP])
        self._vals = int((self._max_kelvin + self._min_kelvin) / 2)

        self._channel_setup = kwargs.get(CONF_CHANNEL_SETUP) or "ch"
        validate(self._channel_setup, self.CONF_TYPE)

        self._channel_width = len(self._channel_setup)

    @property
    def color_temp_kelvin(self) -> int | None:
        return self._vals

    @property
    def min_color_temp_kelvin(self) -> int:
        """Return the warmest color_temp_kelvin that this light supports."""
        return self._min_kelvin

    @property
    def max_color_temp_kelvin(self) -> int:
        """Return the coldest color_temp_kelvin that this light supports."""
        return self._max_kelvin

    def _update_values(self, values: array[int]):
        self._state, self._attr_brightness, _, _, _, _, _, color_temp = from_values(self._channel_setup,
                                                                                    self.channel_size[1], values,
                                                                                    self._min_kelvin, self._max_kelvin)
        self._vals = color_temp

        self._channel_value_change()

    def get_target_values(self):
        return to_values(self._channel_setup, self._channel_size[1], self.is_on, self._attr_brightness,
                         color_temp_kelvin=self.color_temp_kelvin,
                         min_kelvin=self.min_color_temp_kelvin,
                         max_kelvin=self.max_color_temp_kelvin)

    async def async_turn_on(self, **kwargs):
        """
        Instruct the light to turn on.
        """

        old_values = self._vals
        old_brightness = self._attr_brightness

        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            self._vals = kwargs[ATTR_COLOR_TEMP_KELVIN]

        elif ATTR_WHITE in kwargs:
            self._vals = (self._max_kelvin + self._min_kelvin) / 2
            self._attr_brightness = kwargs[ATTR_WHITE]

        if ATTR_BRIGHTNESS in kwargs:
            self._attr_brightness = kwargs[ATTR_BRIGHTNESS]

        if ATTR_FLASH in kwargs:
            await super().flash(old_values, old_brightness, **kwargs)
        else:
            await super().async_create_fade(**kwargs)

        return None

    async def restore_state(self, old_state):
        log.debug("Added color_temp to hass. Try restoring state.")

        if old_state:
            prev_vals = old_state.attributes.get('values')
            self._vals = prev_vals
            prev_brightness = old_state.attributes.get('bright')
            self._attr_brightness = prev_brightness

        if old_state.state != STATE_OFF:
            await super().async_create_fade(brightness=self._attr_brightness, rgb_color=self._vals, transition=0)


class DmxRGB(DmxBaseLight):
    CONF_TYPE = "rgb"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._features = LightEntityFeature.TRANSITION | LightEntityFeature.FLASH
        self._color_mode = ColorMode.RGB
        self._supported_color_modes.add(ColorMode.RGB)
        self._supported_color_modes.add(ColorMode.HS)
        self._vals = (255, 255, 255)
        self._channel_setup = kwargs.get(CONF_CHANNEL_SETUP) or "rgb"
        validate(self._channel_setup, self.CONF_TYPE)
        self._auto_scale_white = ("w" in self._channel_setup or "W" in self._channel_setup)
        # For overlapping channels (separate-channel mode) we will use these attributes.
        # In unified mode, these remain None.
        self._red_channel = None
        self._green_channel = None
        self._blue_channel = None
        # Save our new options from configuration.
        self._rgb_offsets = kwargs.get(CONF_RGB_OFFSETS, [0, 1, 2])
        self._swap_green_blue = kwargs.get(CONF_SWAP_GREEN_BLUE, False)

    def set_color_channels(self, red_channel, green_channel, blue_channel):
        """Assign individual DMX channels for red, green, and blue."""
        self._red_channel = red_channel
        self._green_channel = green_channel
        self._blue_channel = blue_channel

    @property
    def rgb_color(self) -> tuple:
        """Return the current RGB color as a tuple."""
        return self._vals

    def get_target_values(self):
        """
        When using separate channels, return the current RGB values (applying swap if enabled).
        In unified mode, this method is used by to_values to build a full DMX frame.
        """
        red, green, blue = self._vals
        if self._swap_green_blue:
            green, blue = blue, green
        return (red, green, blue)

    def _update_values(self, values: array[int]):
        self._state, self._attr_brightness, red, green, blue, _, _, _ = \
            from_values(self._channel_setup, self.channel_size[1], values)
        self._vals = (red, green, blue)
        self._channel_value_change()

    async def async_turn_on(self, **kwargs):
        """
        Update the light's state from service call parameters and then delegate to async_create_fade.
        """
        old_values = self._vals
        old_brightness = self._attr_brightness
        if ATTR_RGB_COLOR in kwargs:
            self._vals = kwargs[ATTR_RGB_COLOR]
        if ATTR_HS_COLOR in kwargs:
            hue, sat = kwargs[ATTR_HS_COLOR]
            self._vals = color_util.color_hs_to_RGB(hue, sat)
        if ATTR_BRIGHTNESS in kwargs:
            self._attr_brightness = kwargs[ATTR_BRIGHTNESS]
        if ATTR_FLASH in kwargs:
            await super().flash(old_values, old_brightness, **kwargs)
        else:
            await self.async_create_fade(**kwargs)
        return None

    async def async_create_fade(self, **kwargs):
        """
        Instruct the light to fade on.
        If separate channels are defined (i.e. _red_channel is not None), send individual fade
        commands on each channel; otherwise, build a full DMX frame for the unified channel.
        """
        self._state = True
        transition = kwargs.get(ATTR_TRANSITION, self._fade_time)
        if self._red_channel is not None:
            # Separate-channel mode.
            red, green, blue = self.get_target_values()
            # Apply brightness scaling if needed.
            if self._attr_brightness < 255:
                red = int(red * self._attr_brightness / 255)
                green = int(green * self._attr_brightness / 255)
                blue = int(blue * self._attr_brightness / 255)
            self._red_channel.set_fade([red], transition * 1000)
            self._green_channel.set_fade([green], transition * 1000)
            self._blue_channel.set_fade([blue], transition * 1000)
        else:
            # Unified mode: build the full DMX frame using the helper function.
            target = to_values(self._channel_setup,
                               self._channel_size[1],
                               self.is_on,
                               self._attr_brightness,
                               *self._vals)
            self._channel.set_fade(target, transition * 1000)
        self.async_schedule_update_ha_state()

    async def restore_state(self, old_state):
        """
        Restore the light's previous state.
        Make sure to call our own async_create_fade so that the unified vs separate-channel branch is used.
        """
        log.debug("Added rgb to hass. Try restoring state.")
        if old_state:
            prev_vals = old_state.attributes.get('values')
            self._vals = prev_vals if prev_vals is not None else (255, 255, 255)
            prev_brightness = old_state.attributes.get('bright')
            self._attr_brightness = prev_brightness if prev_brightness is not None else 255

        if not hasattr(self, '_swap_green_blue'):
            self._swap_green_blue = False
        if not hasattr(self, '_rgb_offsets'):
            self._rgb_offsets = [0, 1, 2]

        if old_state.state != STATE_OFF:
            await self.async_create_fade(brightness=self._attr_brightness, rgb_color=self._vals, transition=0)

class DmxRGBGroup(DmxBaseLight):
    """
    A grouped RGB device, controlling N sets of R/G/B channels
    as one logical RGB light in Home Assistant.
    """
    CONF_TYPE = "group_rgb"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._features = LightEntityFeature.TRANSITION | LightEntityFeature.FLASH
        self._color_mode = ColorMode.RGB
        self._supported_color_modes.add(ColorMode.RGB)
        self._supported_color_modes.add(ColorMode.HS)

        # One color is used for the entire group
        self._vals = (255, 255, 255)  # (R, G, B)
        self._rgb_offsets = kwargs.get(CONF_RGB_OFFSETS, [0, 1, 2])
        self._swap_green_blue = kwargs.get(CONF_SWAP_GREEN_BLUE, False)

        # group_count sets of RGB channels
        self._group_count = kwargs.get("group_count", 1)

        # We'll store the channels for every sub-RGB set:
        # total channels = group_count * 3
        self._rgb_channels = []

    def set_group_channels(self, channels: list[pyartnet.base.Channel]):
        """
        Called from async_setup_platform once the channels are allocated.
        `channels` should be in the order: 
          R1, G1, B1, R2, G2, B2, ... up to group_count * 3.
        """
        self._rgb_channels = channels

    def set_channel(self, channel: pyartnet.base.Channel):
        """
        Overridden to do nothing for group mode since we create multiple channels.
        """
        pass

    def get_target_values(self) -> list[int]:
        """
        Returns a DMX value for each channel in the group.
        For each sub-RGB set, we replicate the same color.
        """
        # If the entity is off, all channels = 0
        if not self._state:
            return [0] * (self._group_count * 3)

        # On => replicate (r, g, b) across group_count sets
        r, g, b = self._vals
        if self._swap_green_blue:
            g, b = b, g

        # Example: if group_count=2 and color=(128,64,10),
        # we want [128,64,10, 128,64,10]
        values = []
        for _ in range(self._group_count):
            values.extend([r, g, b])
        return values

    async def async_create_fade(self, **kwargs):
        """
        Fade each channel in the group. The base class tries 
        to handle 1 or 3 channels, so we override for 3*N.
        """
        transition = kwargs.get(ATTR_TRANSITION, self._fade_time)
        target_values = self.get_target_values()  # length = group_count * 3

        # If brightness < 255, scale them
        # Alternatively, you can store brightness in self._attr_brightness 
        # and incorporate it in get_target_values, but we do it here:
        if self._attr_brightness < 255 and self._attr_brightness >= 0:
            target_values = [
                int(v * self._attr_brightness / 255) for v in target_values
            ]

        # Now send fade commands to each channel
        # zip the channels with their corresponding DMX value
        for ch, val in zip(self._rgb_channels, target_values):
            if transition > 0:
                ch.set_fade([val], transition * 1000)
            else:
                ch.set_values([val])

        self.async_schedule_update_ha_state()

    async def async_turn_on(self, **kwargs):
        """
        Turn on the grouped RGB device. 
        We'll parse optional rgb_color or hs_color, brightness, etc.
        """
        self._state = True
        if ATTR_RGB_COLOR in kwargs:
            self._vals = kwargs[ATTR_RGB_COLOR]
        if ATTR_HS_COLOR in kwargs:
            hue, sat = kwargs[ATTR_HS_COLOR]
            self._vals = color_util.color_hs_to_RGB(hue, sat)
        if ATTR_BRIGHTNESS in kwargs:
            self._attr_brightness = kwargs[ATTR_BRIGHTNESS]
        if ATTR_FLASH in kwargs:
            # If you want a flash effect, adapt from the base 
            # or do your own approach
            old_vals = self._vals
            old_brightness = self._attr_brightness
            await super().flash(old_vals, old_brightness, **kwargs)
        else:
            await self.async_create_fade(**kwargs)

    async def async_turn_off(self, **kwargs):
        self._state = False
        await self.async_create_fade(**kwargs)

    async def restore_state(self, old_state):
        """
        Attempt to restore color, brightness, and on/off state.
        """
        log.debug("Restoring state for group rgb '%s': %s", self._name, old_state)
        if old_state:
            # old_state.attributes.get('values') might be your last color 
            prev_vals = old_state.attributes.get('values')
            # If we stored (red, green, blue) in 'values', 
            # we can restore it:
            if prev_vals is not None and len(prev_vals) >= 3:
                self._vals = (prev_vals[0], prev_vals[1], prev_vals[2])

            prev_brightness = old_state.attributes.get('bright')
            if prev_brightness is not None:
                self._attr_brightness = prev_brightness

            if old_state.state.lower() == STATE_OFF:
                self._state = False
            else:
                self._state = True

        await self.async_create_fade()

class DmxRGBW(DmxBaseLight):
    CONF_TYPE = "rgbw"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._features = LightEntityFeature.TRANSITION | LightEntityFeature.FLASH
        self._color_mode = ColorMode.RGBW
        self._supported_color_modes.add(ColorMode.RGBW)
        self._supported_color_modes.add(ColorMode.HS)
        self._vals = [255, 255, 255, 255]

        self._channel_setup = kwargs.get(CONF_CHANNEL_SETUP) or "rgbw"
        validate(self._channel_setup, self.CONF_TYPE)

        self._channel_width = len(self._channel_setup)

    @property
    def rgbw_color(self) -> tuple:
        """Return the rgbw color value."""
        return tuple(self._vals)

    def _update_values(self, values: array[int]):
        self._state, self._attr_brightness, red, green, blue, white, _, _ = \
            from_values(self._channel_setup, self.channel_size[1], values)

        self._vals = [red, green, blue, white]

        self._channel_value_change()

    def get_target_values(self):
        red = self._vals[0]
        green = self._vals[1]
        blue = self._vals[2]
        white = self._vals[3]

        return to_values(self._channel_setup, self._channel_size[1], self.is_on, self._attr_brightness, red, green,
                         blue,
                         white)

    async def async_turn_on(self, **kwargs):
        """
        Instruct the light to turn on.
        """

        old_values = list(self._vals)
        old_brightness = self._attr_brightness

        # RGB already contains brightness information
        if ATTR_RGBW_COLOR in kwargs:
            self._vals = list(kwargs[ATTR_RGBW_COLOR])

        if ATTR_HS_COLOR in kwargs:
            hue, sat = kwargs[ATTR_HS_COLOR]
            self._vals[0:3] = list(color_util.color_hs_to_RGB(hue, sat))

        if ATTR_BRIGHTNESS in kwargs:
            self._attr_brightness = kwargs[ATTR_BRIGHTNESS]

        if ATTR_FLASH in kwargs:
            await super().flash(old_values, old_brightness, **kwargs)
        else:
            await super().async_create_fade(**kwargs)

        return None

    async def restore_state(self, old_state):
        log.debug("Added rgbw to hass. Try restoring state.")

        if old_state:
            prev_vals = old_state.attributes.get('values')
            self._vals = prev_vals

            prev_brightness = old_state.attributes.get('bright')
            self._attr_brightness = prev_brightness

        if old_state.state != STATE_OFF:
            await super().async_create_fade(brightness=self._attr_brightness, rgbw_color=self._vals, transition=0)


class DmxRGBWW(DmxBaseLight):
    CONF_TYPE = "rgbww"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._features = LightEntityFeature.TRANSITION | LightEntityFeature.FLASH
        self._color_mode = ColorMode.RGBWW
        self._supported_color_modes.add(ColorMode.RGBWW)
        self._supported_color_modes.add(ColorMode.COLOR_TEMP)
        self._supported_color_modes.add(ColorMode.HS)

        # Intentionally switching min and max here; it's inverted in the conversion.
        self._min_kelvin = convert_to_kelvin(kwargs[CONF_DEVICE_MIN_TEMP])
        self._max_kelvin = convert_to_kelvin(kwargs[CONF_DEVICE_MAX_TEMP])
        self._vals = [255, 255, 255, 255, 255, (self._max_kelvin - self._min_kelvin) / 2]

        self._channel_setup = kwargs.get(CONF_CHANNEL_SETUP) or "rgbch"
        validate(self._channel_setup, self.CONF_TYPE)

        self._channel_width = len(self._channel_setup)

    def _update_values(self, values: array[int]):
        self._state, self._attr_brightness, red, green, blue, cold_white, warm_white, color_temp = \
            from_values(self._channel_setup, self.channel_size[1], values)

        self._vals = (red, green, blue, cold_white, warm_white, color_temp)

        self._channel_value_change()

    @property
    def rgbww_color(self) -> tuple:
        """Return the rgbww color value."""
        return tuple(self._vals[0:5])

    @property
    def min_color_temp_kelvin(self) -> int:
        """Return the warmest color_temp_kelvin that this light supports."""
        return self._min_kelvin

    @property
    def max_color_temp_kelvin(self) -> int:
        """Return the coldest color_temp_kelvin that this light supports."""
        return self._max_kelvin

    @property
    def color_temp_kelvin(self) -> int | None:
        return self._vals[5]

    def get_target_values(self):
        red = self._vals[0]
        green = self._vals[1]
        blue = self._vals[2]
        cold_white = self._vals[3]
        warm_white = self._vals[4]
        color_temperature_kelvin = self._vals[5]

        return to_values(self._channel_setup, self._channel_size[1], self.is_on, self._attr_brightness,
                         red, green, blue, cold_white, warm_white,
                         color_temp_kelvin=color_temperature_kelvin,
                         min_kelvin=self.min_color_temp_kelvin,
                         max_kelvin=self.max_color_temp_kelvin)

    async def async_turn_on(self, **kwargs):
        """
        Instruct the light to turn on.
        """
        old_values = list(self._vals)
        old_brightness = self._attr_brightness

        # RGB already contains brightness information
        if ATTR_RGBWW_COLOR in kwargs:
            self._vals[0:5] = kwargs[ATTR_RGBWW_COLOR]

            if self._vals[3] != old_values[3] or self._vals[4] != old_values[4]:
                self._vals[5], _ = color_util.rgbww_to_color_temperature(
                    (self._vals[0], self._vals[1], self._vals[2], self._vals[3], self._vals[4]),
                    self.min_color_temp_kelvin, self.max_color_temp_kelvin
                )
                self._channel_value_change()

        if ATTR_HS_COLOR in kwargs:
            hue, sat = kwargs[ATTR_HS_COLOR]
            self._vals[0:3] = list(color_util.color_hs_to_RGB(hue, sat))

        if ATTR_BRIGHTNESS in kwargs:
            self._attr_brightness = kwargs[ATTR_BRIGHTNESS]

        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            self._vals[5] = kwargs[ATTR_COLOR_TEMP_KELVIN]
            _, _, _, self._vals[3], self._vals[4] = color_util.color_temperature_to_rgbww(
                self._vals[5], self._attr_brightness, self.min_color_temp_kelvin, self.max_color_temp_kelvin)
            self._channel_value_change()

        if ATTR_FLASH in kwargs:
            await super().flash(old_values, old_brightness, **kwargs)
        else:
            await super().async_create_fade(**kwargs)

        return None

    async def restore_state(self, old_state):
        log.debug("Added rgbww to hass. Try restoring state.")

        if old_state:
            prev_vals = old_state.attributes.get('values')
            if len(prev_vals) == 6:
                self._vals = prev_vals

            prev_brightness = old_state.attributes.get('bright')
            self._attr_brightness = prev_brightness

        if old_state.state != STATE_OFF:
            await super().async_create_fade(brightness=self._attr_brightness, rgbww_color=self._vals, transition=0)


# ------------------------------------------------------------------------------
# conf
# ------------------------------------------------------------------------------

__CLASS_LIST = [DmxDimmer, DmxRGB, DmxWhite, DmxRGBW, DmxRGBWW, DmxBinary, DmxFixed, DmxDimmerGroup, DmxRGBGroup]
__CLASS_TYPE = {k.CONF_TYPE: k for k in __CLASS_LIST}

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_NODE_HOST): cv.string,
        vol.Required(CONF_NODE_UNIVERSES): {
            vol.All(int, vol.Range(min=0, max=1024)): {
                vol.Optional(CONF_SEND_PARTIAL_UNIVERSE, default=True): cv.boolean,
                vol.Optional(CONF_OUTPUT_CORRECTION, default='linear'): vol.Any(
                    None, vol.In(AVAILABLE_CORRECTIONS)
                ),
                CONF_DEVICES: vol.All(
                    cv.ensure_list,
                    [
                        {
                            vol.Required(CONF_DEVICE_CHANNEL): vol.All(
                                vol.Coerce(int), vol.Range(min=1, max=512)
                            ),
                            vol.Required(CONF_DEVICE_NAME): cv.string,
                            vol.Optional(CONF_DEVICE_FRIENDLY_NAME): cv.string,
                            vol.Optional(CONF_DEVICE_TYPE, default='dimmer'): vol.In(
                                [k.CONF_TYPE for k in __CLASS_LIST]
                            ),
                            vol.Optional(CONF_DEVICE_TRANSITION, default=0): vol.All(
                                vol.Coerce(float), vol.Range(min=0, max=999)
                            ),
                            vol.Optional(CONF_OUTPUT_CORRECTION, default='linear'): vol.Any(
                                None, vol.In(AVAILABLE_CORRECTIONS)
                            ),
                            vol.Optional(CONF_CHANNEL_SIZE, default='8bit'): vol.Any(
                                None, vol.In(CHANNEL_SIZE)
                            ),
                            vol.Optional(CONF_BYTE_ORDER, default='big'): vol.Any(
                                None, vol.In(['little', 'big'])
                            ),
                            vol.Optional(CONF_DEVICE_MIN_TEMP, default='2700K'): vol.Match(
                                "\\d+(k|K)"
                            ),
                            vol.Optional(CONF_DEVICE_MAX_TEMP, default='6500K'): vol.Match(
                                "\\d+(k|K)"
                            ),
                            vol.Optional(CONF_CHANNEL_SETUP, default=None): vol.Any(
                                None, cv.string, cv.ensure_list
                            ),
                            vol.Optional(CONF_SWAP_GREEN_BLUE, default=False): bool,
                            vol.Optional(CONF_RGB_OFFSETS, default=[0, 1, 2]): vol.All([vol.Coerce(int)]),
                            vol.Optional("group_count", default=1): vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
                        }
                    ],
                )
            },
        },
        vol.Optional(CONF_NODE_HOST_OVERRIDE, default=""): cv.string,
        vol.Optional(CONF_NODE_PORT): cv.port,
        vol.Optional(CONF_NODE_PORT_OVERRIDE): cv.port,
        vol.Optional(CONF_NODE_MAX_FPS, default=25): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=50)
        ),
        vol.Optional(CONF_NODE_REFRESH, default=120): vol.All(
            vol.Coerce(float), vol.Range(min=0, max=9999)
        ),
        vol.Optional(CONF_NODE_TYPE, default="artnet-direct"): vol.Any(
            None, vol.In(["artnet-direct", "artnet-controller", "sacn", "kinet"])
        ),
    },
    required=True,
    extra=vol.PREVENT_EXTRA,
)

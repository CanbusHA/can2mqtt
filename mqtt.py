import paho.mqtt.client as mqtt

import colorsys

import bus

import json

from recordclass import recordclass

RGBCCTState = recordclass("RGBCCTState", ["white_state", "color_state", "brightness", "temp", "white_value", "hue", "saturation", "r", "g", "b", "cw", "ww"])

class Context(object):
    def __init__(self, mqtt, config):
        self.mqtt = mqtt
        self.config = config
        self.mqtt_hass_prefix = config["mqtt"]["hass_prefix"]
        self.mqtt_node_id = config["mqtt"]["node_id"]

        self.availability_topic = "{}/availability".format(self.mqtt_node_id)

        self.can = bus.Bus(config["can"]["dev"])

        self.devices = []

        devices_config = config["devices"]
        for device_config in devices_config:
            typ = device_types[device_config["type"]]
            inst = typ(self, device_config)
            self.devices.append(inst)

        self.can.loop.run_until_complete(self.can.do_enumerate())

    def on_connect(self):
        for dev in self.devices:
            dev.on_connect()

    def on_message(self, msg):
        print(msg)
        for dev in self.devices:
            dev.on_message(msg)

class Device(object):
    def __init__(self, ctx, config):
        self.ctx = ctx
        self.config = config

    def on_connect(self):
        pass

    def on_message(self, msg):
        pass

class Dimmer(Device):
    def __init__(self, ctx, config):
        super().__init__(ctx, config)

        self.bus_id = self.config["busid"]
        self.dev = self.ctx.can.get_device_proxy(self.bus_id, bus.Dimmer)

        self.id = config["id"]
        self.name = config["name"]

        self.availability_topic = "{}/light/{}/availability".format(self.ctx.mqtt_node_id, self.id)

        base_topic = "{}/light/{}/{}".format(
            self.ctx.mqtt_hass_prefix, 
            self.ctx.mqtt_node_id, 
            self.id,
        )
        print(base_topic)
        self.topics = {
            "base": base_topic,
            "config": base_topic + "/config",
            "state": base_topic + "/state",
            "command": base_topic + "/set",
        }

        def set_avail(avail):
            avail_str = "online" if avail else "offline"
            self.ctx.mqtt.publish(self.availability_topic, payload=avail_str, retain=True)
        self.dev.availability_slot.register(set_avail)

        self.min_mr = int(1000000 / 6500)
        self.max_mr = int(1000000 / 2200)

        self.state = RGBCCTState(
            white_state=False,
            color_state=False,
            brightness=128,
            temp=int((self.min_mr + self.max_mr) / 2),
            white_value=255,
            hue=0,
            saturation=0,
        )

    def on_connect(self):

        mqtt_config = {
            "name": self.name,
            "unique_id": self.id,

            "device": {
                #"connections": {
                #    "bus_id": self.bus_id,
                #},
                "identifiers": ["canbridge_" + self.bus_id],
                "name": self.name,
            },

            "command_topic": self.topics["command"],
            "state_topic": self.topics["state"],
            
            "availability": [
                {
                    "topic": self.availability_topic,
                },
                {
                    "topic": self.ctx.availability_topic,
                    "payload_not_available": "NEVERMATCH",
                },
            ],

            "schema": "json",

            "supported_color_modes": ["color_temp", "rgbww"],
            "color_mode": True,
            #"color_mode": "rgbww",
            #"brightness": True,
            #"white_value": True,
            #"hs": True,
            #"color_temp": True,
            "min_mireds": self.min_mr,
            "max_mireds": self.max_mr,
        }
        self.ctx.mqtt.publish(self.topics["config"], payload=json.dumps(mqtt_config), retain=True)

        self.ctx.mqtt.subscribe(self.topics["command"])

        avail_str = "online" if self.dev.availability else "offline"
        self.ctx.mqtt.publish(self.availability_topic, payload=avail_str, retain=True)

    def update_mqtt_state(self):
        state = {
            "state": "ON" if (self.state.white_state or self.state.color_state) else "OFF",
            "brightness": self.state.brightness,
            "color_temp": self.state.temp,
            "white_value": self.state.white_value,
            "color": {"h": self.state.hue, "s": self.state.saturation},
        }
        self.ctx.mqtt.publish(self.topics["state"], payload=json.dumps(state), retain=True)

    def update_dev_from_state(self):
        #ww = 0.0
        #cw = 0.0
        #if self.state.white_state:
        #    # Modified DALI log dimming curve
        #    br_pre = 50 + ((self.state.brightness / 255) * (self.state.white_value / 255) * 205)
        #    dali_factor = 10.0**((-255.0+br_pre)/(253.0/3.0))

        #    if self.state.brightness == 0 or self.state.white_value == 0:
        #        dali_factor = 0.0

        #    ct_factor = (self.state.temp - self.min_mr) / (self.max_mr - self.min_mr)
        #    ww = ct_factor * dali_factor
        #    cw = (1 - ct_factor) * dali_factor

        #r = 0.0
        #g = 0.0
        #b = 0.0
        #if self.state.color_state:
        #    # Modified DALI log dimming curve
        #    br_pre = 50 + ((self.state.brightness / 255) * (self.state.saturation / 100) * 205)
        #    dali_factor = 10.0**((-255.0+br_pre)/(253.0/3.0))

        #    if self.state.brightness == 0 or self.state.saturation == 0:
        #        dali_factor = 0.0

        #    hue = 1.0 - (self.state.hue / 360) + (1/3)
        #    (r, g, b) = colorsys.hsv_to_rgb(hue, 1.0, 1.0)

        #    r = r * dali_factor
        #    g = g * dali_factor
        #    b = b * dali_factor

        self.dev.set(self.state.ww, self.state.r, self.state.g, self.state.b, self.state.cw)

    def on_message(self, msg):
        if msg.topic == self.topics["command"]:
            data = json.loads(msg.payload)
            if "state" in data:
                if data["state"] == "ON":
                    self.state.white_state = True
                    self.state.color_state = True
                else:
                    self.state.white_state = False
                    self.state.color_state = False
            if "color_mode" in data:
                print(color_mode)
                self.state.color_mode = data["color_mode"]
            if "brightness" in data:
                self.state.brightness = data["brightness"]
            if "color_temp" in data:
                self.state.temp = data["color_temp"]
            if "white_value" in data:
                self.state.white_value = data["white_value"]
            if "color" in data:
                color = data["color"]
                self.state.r = color["r"]
                self.state.g = color["g"]
                self.state.b = color["b"]
                self.state.cw = color["cw"]
                self.state.ww = color["ww"]
                #self.state.hue = color["h"]
                #self.state.saturation = color["s"]

        self.update_dev_from_state()
        self.update_mqtt_state()

device_types = {
    "5ch_dimmer": Dimmer,
}


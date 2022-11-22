import logging
paho_mqtt_logger = logging.getLogger('mqtt')
paho_mqtt_logger.setLevel(logging.DEBUG)

import yaml
try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper

import paho.mqtt.client as mqtt
import mqtt as lmqtt

print("start")

with open("config.yaml", "r") as f:
    config = yaml.load(f, Loader=Loader)

def on_connect(client, userdata, flags, rc):
    print("Connected with result code "+str(rc))
    ctx.on_connect()

def on_message(client, userdata, msg):
    print(msg.topic+" "+str(msg.payload))
    ctx.on_message(msg)

mqtt_config = config["mqtt"]

client = mqtt.Client()
client.enable_logger(logger=paho_mqtt_logger)
client.username_pw_set(mqtt_config["username"], password=mqtt_config["password"])
client.on_connect = on_connect
client.on_message = on_message

ctx = lmqtt.Context(client, config)

client.connect(mqtt_config["host"], mqtt_config["port"], 60)

# Blocking call that processes network traffic, dispatches callbacks and
# handles reconnecting.
# Other loop*() functions are available that give a threaded interface and a
# manual interface.
client.loop_forever()

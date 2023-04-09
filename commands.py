from __future__ import annotations
import subprocess
import time
import socket
import json
from dataclasses import dataclass
from typing import Callable, TYPE_CHECKING

from loguru import logger

from mqttconsumer import MQTTConsumer

PAYLOAD_PRESS = "press"

if TYPE_CHECKING:
    from settings import Settings
    from main import Linux2MQTT


@dataclass
class MQTTButton:
    name: str
    base_topic: str
    icon: str
    callback: Callable = None

    @property
    def command_topic(self):
        return f"{self.base_topic}/set"

    @property
    def availability_topic(self):
        return f"{self.base_topic}/availability"


class LinuxCommands(MQTTConsumer):
    def __init__(self, config: Settings, runtime: Linux2MQTT):
        super().__init__(config, runtime)
        self.config = config
        self.runtime = runtime
        self.will_suspend = False
        self.will_poweroff = False
        head_topic = self.config.get("mqtt", "topic", "linux2mqtt")
        self.client_name = self.config.get("client", "name", socket.gethostname())
        our_topic = self.config.get("commands", "sub_topic", "commands")
        self.subtopic = f"{head_topic}/{self.client_name}/{our_topic}"
        self.buttons = []

        # Suspend button
        if self.config.get("commands", "suspend", "false").lower() == "true":
            topic = f"{self.subtopic}/suspend"
            self.buttons.append(MQTTButton("suspend", topic, "mdi:power-sleep", self.suspend_callback))
        # Poweroff button
        if self.config.get("commands", "poweroff", "false").lower() == "true":
            topic = f"{self.subtopic}/poweroff"
            self.buttons.append(MQTTButton("poweroff", topic, "mdi:power", self.poweroff_callback))

    def poweroff_callback(self):
        # This callback will be called within the MQTT thread,
        # so we need to do the poweroff next time we are called normally
        self.will_poweroff = True

    def do_poweroff(self):
        self.runtime.on_poweroff()
        # Execute the poweroff command in a subprocess after some waiting
        # This is to give the MQTT broker time to send the last will message
        logger.info("Powering off")
        subprocess.Popen("sleep 5 && poweroff", shell=True, executable="/bin/bash")

    def suspend_callback(self):
        # This callback will be called within the MQTT thread,
        # so we need to do the suspend next time we are called normally
        logger.info("Suspending requested")
        self.will_suspend = True

    def do_suspend(self):
        self.runtime.on_suspend()
        subprocess.call(["systemctl", "suspend"])
        time.sleep(10)
        logger.info("System resumed")
        self.runtime.on_resume()

    def on_connect(self, mqtt_client):
        # Build the homeassistant discovery message for the suspend and poweroff buttons
        for button in self.buttons:
            homeassistant_topic = f"homeassistant/button/{self.client_name}_commands/{button.name}/config"
            homeassistant_message = {
                "name": f"{button.name.title()} {self.client_name}",
                "object_id": f"{self.client_name}_{button.name}",
                "command_topic": f"{button.command_topic}",
                "payload_press": PAYLOAD_PRESS,
                "icon": button.icon,
                "device": {"identifiers": [self.client_name], "name": self.client_name, "model": "Linux2MQTT"},
                "unique_id": f"{self.client_name}_{button.name}_button",
                "availability": {"topic": f"{button.availability_topic}"},
            }
            mqtt_client.publish(homeassistant_topic, json.dumps(homeassistant_message), retain=True)
            # Subscribe and set the callback to handle button presses
            mqtt_client.subscribe(button.command_topic)
            mqtt_client.message_callback_add(button.command_topic, self._on_button_press)
            logger.info(f"Registered button {button.name} on topic {button.command_topic}")
            self.register_availability_topic(button.availability_topic)

    def on_disconnect(self, mqtt_client):
        # Set the availability topics of all buttons to offline
        for button in self.buttons:
            mqtt_client.unsubscribe(button.command_topic)
            mqtt_client.message_callback_remove(button.command_topic)
            # Availability topic is set to offline in the MQTTConsumer base class

    def update_mqtt(self, mqtt_client):
        # Nothing to publish, but:
        # Check if we need to suspend or poweroff
        if self.will_suspend:
            self.do_suspend()
            self.will_suspend = False
        if self.will_poweroff:
            self.do_poweroff()
            self.will_poweroff = False

    def _on_button_press(self, client, userdata, message):
        # Callback handler for button presses from MQTT
        logger.info(f"Button press: {message.topic}: {message.payload}")
        if message.payload.decode() != PAYLOAD_PRESS:
            logger.warning(f"Unexpected payload for button press: {message.payload}")
            return
        for button in self.buttons:
            if message.topic == button.command_topic:
                button.callback()
                break

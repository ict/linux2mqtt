import socket
import time
import uuid
import sys
import signal

from paho.mqtt import client as mqtt
from loguru import logger
from typing import List

from mqttconsumer import MQTTConsumer
from settings import Settings
from host_sensors import HostSensors
from commands import LinuxCommands

# The amount of time to sleep between checks if the main loop should exit
# MQTT update time is configured by the user and can be larger
MAIN_LOOP_SLEEP_TIME = 0.5


class Linux2MQTT:
    def __init__(self):
        self.running = False
        self.config = Settings()
        self.mqtt_client: mqtt = None
        head_topic = self.config.get("mqtt", "topic", "linux2mqtt")
        host = self.config.get("client", "name", socket.gethostname())
        self.publish_topic = f"{head_topic}/{host}"
        self.availability_topic = f"{self.publish_topic}/availability"
        signal.signal(signal.SIGHUP, self.on_exit)
        signal.signal(signal.SIGINT, self.on_exit)
        signal.signal(signal.SIGTERM, self.on_exit)

        sleep_time = self.config.get("client", "update_interval", "60")
        try:
            self.sleep_time = int(sleep_time)
        except ValueError:
            logger.error(f"Invalid update interval: {sleep_time}")
            self.sleep_time = 60

        self.consumers: List[MQTTConsumer] = [HostSensors(self.config, self), LinuxCommands(self.config, self)]

    def run(self):
        if self.running:
            return
        self.running = True
        self._mqtt_connect()
        self.mqtt_client.loop_start()
        try:
            slept = 0.0
            while self.running:
                if slept >= self.sleep_time:
                    slept = 0.0
                    for consumer in self.consumers:
                        consumer.update_mqtt(self.mqtt_client)
                time.sleep(MAIN_LOOP_SLEEP_TIME)
                slept += MAIN_LOOP_SLEEP_TIME
        except KeyboardInterrupt:
            logger.info("Exiting")
        self._disconnect()

    def on_suspend(self):
        # Set availablity to offline instead of waiting for the last will
        self._set_offline()

    def on_exit(self, *args):
        logger.info("Exit requested")
        self.running = False

    def on_resume(self):
        # This will most likely fail, but if we are not disconnected we set the availability here
        # If we were disconnected while suspended, we will reconnect and set the availability in the callback
        self._set_online()

    def _on_mqtt_connect(self, client, userdata, flags, result_code):
        if result_code == 0:
            logger.info("Connected to MQTT server")
            for consumer in self.consumers:
                consumer.connected(self.mqtt_client)
            self._set_online()
        else:
            # Find the error message from the result code
            error_message = mqtt.connack_string(result_code)
            logger.error(f"Failed to connect to MQTT server: {error_message}")

    def _mqtt_connect(self):
        # Connect to the MQTT server with the settings from the config file
        client_id = f"linux2mqtt@{socket.gethostname()}_{uuid.uuid4()}"
        self.mqtt_client = mqtt.Client(client_id=client_id, clean_session=True)
        self.mqtt_client.username_pw_set(
            self.config.get("mqtt", "user", None), self.config.get("mqtt", "password", None)
        )
        self.mqtt_client.on_connect = self._on_mqtt_connect
        # Set the last will to set our availability to offline, this needs to be done before connecting
        self.mqtt_client.will_set(self.availability_topic, "offline", retain=True)
        self.mqtt_client.connect(
            self.config.get("mqtt", "server", "localhost"), int(self.config.get("mqtt", "port", 1883)), 60
        )

    def _disconnect(self):
        for consumer in self.consumers:
            consumer.disconnect(self.mqtt_client)
        # Set our availability to offline
        self._set_offline()
        self.mqtt_client.disconnect()  # Do this before loop_stop so DISCONNECT is sent
        self.mqtt_client.loop_stop()

    def _set_offline(self):
        self.mqtt_client.publish(self.availability_topic, "offline", retain=True)

    def _set_online(self):
        self.mqtt_client.publish(self.availability_topic, "online", retain=True)


if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    Linux2MQTT().run()

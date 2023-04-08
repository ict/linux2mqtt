import socket
import time
import uuid
import sys

from paho.mqtt import client as mqtt
from loguru import logger
from typing import List

from mqttconsumer import MQTTConsumer
from settings import Settings
from host_sensors import HostSensors
from commands import LinuxCommands


class Linux2MQTT:
    def __init__(self):
        self.running = False
        self.config = Settings()
        self.mqtt_client: mqtt = None
        head_topic = self.config.get("mqtt", "topic", "linux2mqtt")
        host = self.config.get("client", "name", socket.gethostname())
        self.publish_topic = f"{head_topic}/{host}"

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
        for consumer in self.consumers:
            consumer.connected(self.mqtt_client)
        try:
            while self.running:
                for consumer in self.consumers:
                    consumer.update_mqtt(self.mqtt_client)
                time.sleep(self.sleep_time)
        except KeyboardInterrupt:
            logger.info("Exiting")
        self._disconnect()

    def on_suspend(self):
        for consumer in self.consumers:
            consumer.suspending(self.mqtt_client)

    def on_poweroff(self):
        self.running = False

    def on_resume(self):
        for consumer in self.consumers:
            consumer.resuming(self.mqtt_client)

    def _on_mqtt_connect(self, client, userdata, flags, result_code):
        if result_code == 0:
            logger.info("Connected to MQTT server")
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
        self.mqtt_client.connect(
            self.config.get("mqtt", "server", "localhost"), int(self.config.get("mqtt", "port", 1883)), 60
        )

    def _disconnect(self):
        for consumer in self.consumers:
            consumer.disconnect(self.mqtt_client)
        self.mqtt_client.loop_stop()
        self.mqtt_client.disconnect()


if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    Linux2MQTT().run()

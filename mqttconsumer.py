from __future__ import annotations
from abc import ABC, abstractmethod

from loguru import logger


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from settings import Settings
    from main import Linux2MQTT


class MQTTConsumer(ABC):
    def __init__(self, config: Settings, runtime: Linux2MQTT):
        self.availability_topics = []

    @abstractmethod
    def on_connect(self, mqtt_client):
        """
        Called when the MQTT client connects to the server.
        Use this to subscribe to topics and publish initial values.
        """
        pass

    @abstractmethod
    def on_disconnect(self, mqtt_client):
        """
        Called before the MQTT client disconnects from the server.
        Use this to publish empty values to topics that will become stale.
        """
        pass

    @abstractmethod
    def update_mqtt(self, mqtt_client):
        """
        Called in regular intervals to update the status of managed topics.
        """
        pass

    def connected(self, mqtt_client):
        """
        Called when the MQTT client connects to the server.
        DO NOT OVERRIDE
        """
        self.on_connect(mqtt_client)

    def disconnect(self, mqtt_client):
        """
        Called before the MQTT client disconnects from the server.
        DO NOT OVERRIDE
        """
        self.on_disconnect(mqtt_client)

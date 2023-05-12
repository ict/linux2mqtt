from __future__ import annotations
import socket
import json
import subprocess

from dataclasses import dataclass
from loguru import logger
import psutil
from typing import TYPE_CHECKING, Callable

import sensors
from Xlib import display
from Xlib.X import AnyPropertyType

from mqttconsumer import MQTTConsumer

if TYPE_CHECKING:
    from settings import Settings
    from main import Linux2MQTT


@dataclass
class MQTTSensor:
    name: str
    publish_topic: str
    unit_of_measurement: str
    value_template: str
    value_func: Callable
    friendly_name: str
    device_class: str = None

    @property
    def state_topic(self):
        return f"{self.publish_topic}"


class HostSensors(MQTTConsumer):
    def __init__(self, config: Settings, runtime: Linux2MQTT):
        super().__init__(config, runtime)
        self.config = config
        self.sensors = []
        self.availability_topic = runtime.availability_topic
        head_topic = self.config.get("mqtt", "topic", "linux2mqtt")
        client = self.config.get("client", "name", socket.gethostname())
        subtopic = self.config.get("sensors", "sub_topic", "sensors")
        self.publish_topic = f"{head_topic}/{client}/{subtopic}"
        if self.config.get("sensors", "enable", "false").lower() != "true":
            logger.info("Sensors disabled")
            return
        logger.info(f"Publishing sensor data to {self.publish_topic}")

        if self.config.get("sensors", "cpu_temp", "false").lower() == "true":
            self.sensors.append(
                MQTTSensor(
                    "cpu_temp",
                    f"{self.publish_topic}/cpu_temp",
                    "°C",
                    "{{ value | float | round(1) }}",
                    self._get_cpu_temp,
                    f"{client.title()} CPU Temperature",
                )
            )
        if self.config.get("sensors", "cpu_usage", "false").lower() == "true":
            self.sensors.append(
                MQTTSensor(
                    "cpu_usage",
                    f"{self.publish_topic}/cpu_usage",
                    "%",
                    "{{ value | int }}",
                    self._get_cpu_usage,
                    f"{client.title()} CPU Usage",
                )
            )
        if self.config.get("sensors", "x_idle", "false").lower() == "true" and self._xprintidle_exists():
            self.sensors.append(
                MQTTSensor(
                    "x_idle",
                    f"{self.publish_topic}/x_idle",
                    "s",
                    "{{ value | int }}",
                    self._get_x_idle,
                    f"{client.title()} X Server Idle Time",
                    device_class="duration",
                )
            )
        if self.config.get("sensors", "x_active_window", "false").lower() == "true":
            self.sensors.append(
                MQTTSensor(
                    "active_window",
                    f"{self.publish_topic}/active_window",
                    "",
                    "{{ value }}",
                    self._get_active_window_process_x,
                    f"{client.title()} Active Window",
                    device_class="enum",
                )
            )

        self.first_cpu_percent = True

    def _xprintidle_exists(self):
        try:
            subprocess.check_output(["which", "xprintidle"])
            return True
        except:
            logger.warning("xprintidle not found. Install xprintidle to get X server idle time.")
            return False

    def __del__(self):
        sensors.cleanup()

    def _get_active_window_process_x(self):
        try:
            disp = display.Display()
            root = disp.screen().root
            window_id = root.get_full_property(disp.intern_atom('_NET_ACTIVE_WINDOW'), AnyPropertyType).value[0]
            window = disp.create_resource_object('window', window_id)
            pid = window.get_full_property(disp.intern_atom('_NET_WM_PID'), 0)
            if pid:
                pid = pid.value[0]
                process = psutil.Process(pid)
                process = f"{process.name()} ({process.status()})"
            else:
                process = None
            wm_class = window.get_wm_class()[0]
            if wm_class:
                process = f"{wm_class} - {process}" if process else wm_class
            return process
        except Exception as e:
            logger.warning(f"Error getting active window process: {e}")
        return None

    def _get_cpu_temp(self):
        sensor = self.config.get("sensors", "cpu_temp_sensor", None)
        if not sensor or sensor.count(":") != 2:
            logger.error("Invalid CPU temperature sensor name")
            return
        chip, feature, subfeature = sensor.split(":")
        chip_cls = None
        chips = sensors.get_detected_chips()
        for c in chips:
            if str(c) == chip:
                chip_cls = c
                break
        if chip_cls is None:
            logger.error(f"Chip {chip} not found. Available: {[str(c) for c in chips]}")
            return
        feature_cls = None
        features = chip_cls.get_features()
        for f in features:
            if chip_cls.get_label(f) == feature:
                feature_cls = f
                break
        if feature_cls is None:
            logger.error(
                f"Feature {feature} on chip {chip} not found. Available: {[chip_cls.get_label(f) for f in features]}"
            )
            return
        subfeature_cls = None
        subfeatures = chip_cls.get_all_subfeatures(feature_cls)
        for s in subfeatures:
            if s.name == subfeature:
                subfeature_cls = s
                break
        if subfeature_cls is None:
            logger.error(
                f"Subfeature {subfeature} on feature {feature} on chip {chip} not found. Available: {subfeatures}"
            )
            return
        try:
            value = chip_cls.get_value_or_none(subfeature_cls.number)
        except Exception as e:
            logger.error(f"Error reading value for {feature}: {e}")
            return

        logger.debug(f"CPU temperature of {sensor}: {value} °C")
        return value

    def _get_cpu_usage(self):
        cpu_usage = psutil.cpu_percent(interval=None)
        logger.debug(f"CPU usage: {cpu_usage} %")
        if self.first_cpu_percent:
            self.first_cpu_percent = False
            return None
        return cpu_usage

    def _get_x_idle(self):
        try:
            output = subprocess.check_output(["xprintidle"]).strip()
        except Exception as e:
            logger.error(f"Error reading xprintidle: {e}")
            return
        idle = int(output) / 1000
        logger.debug(f"X server idle: {idle} s")
        return idle

    def on_connect(self, mqtt_client):
        # We do not need to subscribe to any topics, but we need to publish the homeassistant metadata if enabled
        if self.config.get("mqtt", "homeassistant", "false").lower() != "true":
            logger.info("Homeassistant integration disabled")
            return
        if self.config.get("sensors", "enable", "false").lower() != "true":
            return
        client_name = self.config.get("client", "name", socket.gethostname())

        for sensor in self.sensors:
            topic = f"homeassistant/sensor/{client_name}/{sensor.name}/config"
            payload = {
                "name": sensor.friendly_name,
                "state_topic": sensor.state_topic,
                "unit_of_measurement": sensor.unit_of_measurement,
                "value_template": sensor.value_template,
                "unique_id": f"{client_name}_{sensor.name}",
                "device": {"identifiers": [client_name], "name": client_name, "model": "Linux2MQTT"},
                "availability_topic": self.availability_topic,
            }
            if sensor.device_class:
                payload["device_class"] = sensor.device_class
            mqtt_client.publish(topic, json.dumps(payload), retain=True)

    def on_disconnect(self, mqtt_client):
        # Delete the data we have written as it will become stale very quickly
        # Availability will be set to offline globally
        for sensor in self.sensors:
            mqtt_client.publish(sensor.state_topic, "")

    def update_mqtt(self, mqtt_client):
        if self.config.get("sensors", "enable", "false").lower() != "true":
            return

        for sensor in self.sensors:
            try:
                value = sensor.value_func()
                if value is not None:
                    mqtt_client.publish(sensor.state_topic, value)
            except Exception as e:
                logger.error(f"Error publishing sensor {sensor.name}: {e}")

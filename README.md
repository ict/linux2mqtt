# Linux2MQTT client

This is a simple client that connects to a MQTT broker and publishes basic system information to a topic.
It can also be used to control the system's power state (suspend, shutdown) via MQTT.

The tool was written with the intention to be used with Home Assistant and it will publish the necessary
metadata to be used with the MQTT Discovery feature.

## Sensors
Currently there are two sensors:

### CPU temperature
This sensor publishes the current CPU temperature as reported by the `sensors` command. The sensor to use
needs to be specified in the configuration file as `chip:feature:subfeature` (e.g. `coretemp-isa-0000:Core 0:Tdie`).
You can reference the output of the example code from `pysensors`
(linked [here](https://github.com/bastienleonard/pysensors/blob/master/examples/dump.py)) to find the correct values.

### CPU usage
This sensor publishes the current CPU usage as reported by the `psutil` library.

## Commands

The possibility to suspend or power off the system is provided by a command topic.
The actions are also exposed as `button` entities in Home Assistant.

# Caveat

Much of the code was written with the help of GitHub Copilot within a single day, so it's not perfect.
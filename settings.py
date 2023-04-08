import os
import sys
import argparse
from configparser import ConfigParser, NoSectionError, NoOptionError


class Settings:
    def __init__(self):
        self.parser = argparse.ArgumentParser()
        # self.parser.add_argument("--config", help="configuration file", default="/etc/linux2mqtt.conf")
        self.parser.add_argument("--config", help="configuration file", default="linux2mqtt.conf")
        self.args = self.parser.parse_args()
        if not os.path.exists(self.args.config):
            sys.stderr.write(f"Configuration file {self.args.config} not found.\n")
            exit(1)
        self.config = ConfigParser()
        try:
            self.config.read(self.args.config)
        except Exception as e:
            sys.stderr.write(f"Error reading configuration file at {self.args.config}: {e}\n")
            exit(1)

    def get(self, section, key, default=None):
        try:
            return self.config.get(section, key)
        except (NoSectionError, NoOptionError):
            return default

    def get_section(self, section):
        return self.config.items(section)

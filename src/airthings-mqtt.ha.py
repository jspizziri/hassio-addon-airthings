#!/usr/bin/python3
#
# Copyright (c) 2021 Mark McCans
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import logging, time, json, sys, os, argparse, re
import paho.mqtt.publish as publish
from paho.mqtt import MQTTException
from airthings import AirthingsWaveDetect

_LOGGER = logging.getLogger("airthings-mqtt-ha")

CONFIG = {}     # Variable to store configuration
DEVICES = {}    # Variable to store devices

# Sensor detail deafults (for MQTT discovery)
SENSORS = {
    "radon_1day_avg": {"name": "Radon (1 day avg.)", "device_class": None, "unit_of_measurement": "Bq/m3", "icon": "mdi:radioactive", "state_class": "measurement"},
    "radon_longterm_avg": {"name": "Radon (longterm avg.)", "device_class": None, "unit_of_measurement": "Bq/m3", "icon": "mdi:radioactive", "state_class": "measurement"},
    "co2": {"name": "CO2", "device_class": "carbon_dioxide", "unit_of_measurement": "ppm", "icon": "mdi:molecule-co2", "state_class": "measurement"},
    "voc": {"name": "VOC", "device_class": None, "unit_of_measurement": "ppb", "icon": "mdi:cloud", "state_class": "measurement"},
    "temperature": {"name": "Temperature", "device_class": "temperature", "unit_of_measurement": "°C", "icon": None, "state_class": "measurement"},
    "humidity": {"name": "Humidity", "device_class": "humidity", "unit_of_measurement": "%", "icon": None, "state_class": "measurement"},
    "rel_atm_pressure": {"name": "Pressure", "device_class": "pressure", "unit_of_measurement": "mbar", "icon": None, "state_class": "measurement"}
}

class ATSensors:

    sensors_list = []

    def __init__(self, scan_interval, devices=None):
        _LOGGER.info("Setting up Airthings sensors...")
        self.airthingsdetect = AirthingsWaveDetect(scan_interval, None)

        # Note: Doing this so multiple mac addresses can be sent in instead of just one.
        if devices is not None and devices != {}:
            self.airthingsdetect.airthing_devices = list(devices)
        else:
            _LOGGER.info("No devices provided, so searching for Airthings sensors...")
            self.find_devices()
        
        # Get info about the devices
        if not self.get_device_info():
            # Exit if setup fails
            _LOGGER.error("\033[31mFailed to set up Airthings sensors. If the watchdog option is enabled, this addon will restart and try again.\033[0m")
            sys.exit(1)

        _LOGGER.info("Done Airthings setup.")

    def find_devices(self):
        try:
            _LOGGER.info("Starting search for Airthings sensors...")
            num_devices_found = self.airthingsdetect.find_devices()
            _LOGGER.info("Found {} airthings device(s).".format(num_devices_found))
            if num_devices_found != 0:
                # Display suggested config file entry
                print("")
                print("\033[36m---------------------------------")
                print("Suggested configuration is below:")
                print(" ")
                print("\033[32mdevices:")
                for d in self.airthingsdetect.airthing_devices:
                    print("  - mac: "+d)
                    print("    name: Insert Device Name")
                print("refresh_interval: 150")
                print("retry_count: 10")
                print("retry_wait: 3")
                print("log_level: INFO")
                print("mqtt_discovery: 'true'")
                print(" ")
                print("\033[96m---------------------------------\033[0m")
                sys.exit(0)

                # # Put found devices into DEVICES variable
                # for d in self.airthingsdetect.airthing_devices:
                #     DEVICES[d] = {}
            else:
                # Exit if no devices found
                _LOGGER.warning("\033[31mNo airthings devices found. If the watchdog option is enabled, this addon will restart and try again.\033[0m")
                sys.exit(1)
        except SystemExit as e:
            sys.exit(e)
        except:
            _LOGGER.exception("\033[31mFailed while searching for devices. Is a bluetooth adapter available? If the watchdog option is enabled, this addon will restart and try again.\033[0m")
            sys.exit(1)

    def get_device_info(self):
        _LOGGER.debug("Getting info about device(s)...")
        for attempt in range(CONFIG["retry_count"]):
            try:
                devices_info = self.airthingsdetect.get_info()
            except:
                _LOGGER.warning("Unexpected exception while getting device information on attempt {}. Retrying in {} seconds.".format(attempt+1, CONFIG["retry_wait"]))
                time.sleep(CONFIG["retry_wait"])
            else:
                # Success!
                break
        else:
            # We failed all attempts
            _LOGGER.exception("Failed to get info from devices after {} attempts.".format(CONFIG["retry_count"]))
            return False

        # Collect device details
        for mac, dev in devices_info.items():
            _LOGGER.info("{}: {}".format(mac, dev))
            DEVICES[mac]["manufacturer"] = dev.manufacturer
            DEVICES[mac]["serial_nr"] = dev.serial_nr
            DEVICES[mac]["model_nr"] = dev.model_nr
            DEVICES[mac]["device_name"] = dev.device_name

        _LOGGER.debug("Getting sensors...")
        for attempt in range(CONFIG["retry_count"]):
            try:
                devices_sensors = self.airthingsdetect.get_sensors()
            except:
                _LOGGER.warning("Unexpected exception while getting sensors information on attempt {}. Retrying in {} seconds.".format(attempt+1, CONFIG["retry_wait"]))
                time.sleep(CONFIG["retry_wait"])
            else:
                # Success!
                break
        else:
            # We failed all attempts
            _LOGGER.exception("Failed to get info from sensors after {} attempts.".format(CONFIG["retry_count"]))
            return False

        # Collect sensor details
        for mac, sensors in devices_sensors.items():
            for sensor in sensors:
                self.sensors_list.append([mac, sensor.uuid, sensor.handle])
                _LOGGER.debug("{}: Found sensor UUID: {} Handle: {}".format(mac, sensor.uuid, sensor.handle))
        
        return True
    
    def get_sensor_data(self):
        _LOGGER.debug("Getting sensor data...")
        for attempt in range(CONFIG["retry_count"]):
            try:
                sensordata = self.airthingsdetect.get_sensor_data()
                return sensordata
            except:
                _LOGGER.warning("Unexpected exception while getting sensor data on attempt {}. Retrying in {} seconds.".format(attempt+1, CONFIG["retry_wait"]))
                time.sleep(CONFIG["retry_wait"])
            else:
                # Success!
                break
        else:
            # We failed all attempts
            _LOGGER.exception("Failed to get sensor data after {} attempts.".format(CONFIG["retry_count"]))
            return False
        
        return True

def mqtt_publish(msgs):
    # Publish the sensor data to mqtt broker
    try:
        _LOGGER.info("Sending messages to mqtt broker...")
        if "username" in CONFIG["mqtt"] and CONFIG["mqtt"]["username"] != "" and "password" in CONFIG["mqtt"] and CONFIG["mqtt"]["password"] != "":
            auth = {'username':CONFIG["mqtt"]["username"], 'password':CONFIG["mqtt"]["password"]}
        else:
            auth = None
        publish.multiple(msgs, hostname=CONFIG["mqtt"]["host"], port=CONFIG["mqtt"]["port"], client_id="airthings-mqtt", auth=auth)
        _LOGGER.info("Done sending messages to mqtt broker.")
    except MQTTException as e:
        _LOGGER.error("Failed while sending messages to mqtt broker: {}".format(e))
    except:
        _LOGGER.exception("Unexpected exception while sending messages to mqtt broker.")

if __name__ == "__main__":
    logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s', datefmt='[%Y-%m-%d %H:%M:%S]')
    _LOGGER.setLevel(logging.INFO)

    # Parse command line arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', type=str, required=True, help='mqtt server host name or ip address')
    parser.add_argument('--port', type=int, default=1883, help='mqtt server host port')
    parser.add_argument('--username', type=str, required=True, help='mqtt server username')
    parser.add_argument('--password', type=str, required=True, help='mqtt server password')
    parser.add_argument('--config', type=str, required=True, help='location of options.json file')
    args = parser.parse_args()
    
    # Load configuration from file
    try:
        with open(vars(args)['config']) as f:
            CONFIG = json.load(f)
    except:
        # Exit if there is an error reading config file
        _LOGGER.exception("\033[31mError reading options.json file. If the watchdog option is enabled, this addon will restart and try again.\033[0m")
        sys.exit(1)

    # Fill in the remainder of the config values
    CONFIG["mqtt"] = {}
    CONFIG["mqtt"]["host"] = vars(args)['host']
    CONFIG["mqtt"]["port"] = vars(args)['port']
    CONFIG["mqtt"]["username"] = vars(args)['username']
    CONFIG["mqtt"]["password"] = vars(args)['password']    

    # Set logging level (defaults to INFO)
    if CONFIG["log_level"] in ["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"]:
        _LOGGER.setLevel(CONFIG["log_level"])

    # Pull out devices configured and insert them if a valid mac address has been provided
    if "devices" in CONFIG:
        for d in CONFIG["devices"]:
            if "mac" in d:
                if re.match("[0-9a-f]{2}([-:]?)[0-9a-f]{2}(\\1[0-9a-f]{2}){4}$", d["mac"].lower()):                    
                    # Ensure consistent formatting for the mac address
                    d["mac"] = d["mac"].lower()
                    DEVICES[d["mac"].lower()] = {}
                else:
                    _LOGGER.warning("Invalid mac address provided: {}".format(d["mac"]))

    a = ATSensors(180, DEVICES)

    # Update sensor values in accordance with the REFRESH_INTERVAL set.
    first = True
    while True:
        # Get sensor data
        sensors = a.get_sensor_data()
        # Only connect to mqtt broker if we have data  
        if sensors is not None and sensors != {}:
            # Variable to store mqtt messages
            msgs = []
            
            # Send HA mqtt discovery messages to broker on first run
            if first and CONFIG["mqtt_discovery"] != False:
                _LOGGER.info("Sending HA mqtt discovery configuration messages...")
                for mac, data in sensors.items():
                    # Consistent mac formatting
                    mac = mac.lower()

                    # Create device details for this device
                    device = {}
                    device["connections"] = [["mac", mac]]
                    if "serial_nr" in DEVICES[mac]: device["identifiers"] = [DEVICES[mac]["serial_nr"]]
                    if "manufacturer" in DEVICES[mac]: device["manufacturer"] = DEVICES[mac]["manufacturer"]
                    if "device_name" in DEVICES[mac]: device["name"] = DEVICES[mac]["device_name"]
                    if "model_nr" in DEVICES[mac]: device["model"] = DEVICES[mac]["model_nr"]

                    for name, val in data.items():
                        if name != "date_time":                         
                            try:
                                config = {}
                                s = next((item for item in CONFIG["devices"] if item["mac"] == mac), None)
                                if s != None:
                                    if name in SENSORS:
                                        config["name"] = s["name"]+" "+SENSORS[name]["name"]
                                        if SENSORS[name]["device_class"] != None: config["device_class"] = SENSORS[name]["device_class"]
                                        if SENSORS[name]["icon"] != None: config["icon"] = SENSORS[name]["icon"]
                                        if SENSORS[name]["state_class"] != None: config["state_class"] = SENSORS[name]["state_class"]
                                        config["unit_of_measurement"] = SENSORS[name]["unit_of_measurement"]
                                        config["uniq_id"] = mac+"_"+name
                                        config["state_topic"] = "airthings/"+mac+"/"+name
                                        config["device"] = device

                                msgs.append({'topic': "homeassistant/sensor/airthings_"+mac.replace(":","")+"/"+name+"/config", 'payload': json.dumps(config), 'retain': True})
                            except:
                                _LOGGER.exception("Failed while creating HA mqtt discovery messages.")
                
                # Publish the HA mqtt discovery data to mqtt broker
                mqtt_publish(msgs)
                _LOGGER.info("Done sending HA mqtt discovery configuration messages.")
                msgs = []
                time.sleep(5)
                first = False
            
            # Collect all of the sensor data
            _LOGGER.info("Collecting sensor value messages...")
            for mac, data in sensors.items():
                for name, val in data.items():
                    if name != "date_time":
                        # Consistent mac formatting
                        mac = mac.lower()
                        if isinstance(val, str) == False:
                            if name == "temperature":
                                val = round(val,1)
                            else:
                                val = round(val)
                        _LOGGER.info("{} = {}".format("airthings/"+mac+"/"+name, val))
                        msgs.append({'topic': "airthings/"+mac+"/"+name, 'payload': val})
            
            # Publish the sensor data to mqtt broker
            mqtt_publish(msgs)
        else:
            _LOGGER.error("\033[31mNo sensor values collected. Please check your configuration and make sure your bluetooth adapter is available. If the watchdog option is enabled, this addon will restart and try again.\033[0m")
            sys.exit(1)

        # Wait for next refresh cycle
        _LOGGER.info("Waiting {} seconds.".format(CONFIG["refresh_interval"]))
        time.sleep(CONFIG["refresh_interval"])

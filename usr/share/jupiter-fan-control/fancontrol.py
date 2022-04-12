#!/usr/bin/python -u

import time
import math
import yaml
import os
from PID import PID

# quadratic function RPM = AT^2 + BT + X
class Quadratic(object):
    def __init__(self, A, B, C, T_threshold ):
        self.A = A
        self.B = B
        self.C = C
        self.T_threshold = T_threshold
        self.output = 0
    
    def update(self, temp_input):
        if temp_input < self.T_threshold:
            return 0
        self.output = int(self.A * math.pow(temp_input, 2) + self.B * temp_input + self.C)
        return max(0, self.output)

# exponential function RPM = A * exp(B * T) if T > T_threshold
class Exponential(object):
    def __init__(self, A, B, T_threshold):
        self.A = A
        self.B = B
        self.T_threshold = T_threshold
        self.output = 0
    
    def update(self, temp_input):
        if temp_input < self.T_threshold:
            return 0
        self.output = int(self.A * math.exp(self.B * temp_input))
        return max(0, self.output)

# fan object controls all jupiter hwmon parameters
class Fan(object):
    def __init__(self, fan_path, fan_min_speed, fan_threshold_speed, fan_max_speed, debug = False) -> None:
        self.debug = debug
        self.min_speed = fan_min_speed
        self.threshold_speed = fan_threshold_speed
        self.max_speed = fan_max_speed
        self.fan_path = fan_path
        self.fc_speed = 0

        self.set_speed(0)

        # with open(self.fan_path + "ramp_rate", 'w') as f:
        #     f.write(str(1))
        with open(self.fan_path + "gain", 'w') as f:
            f.write(str(0))
        with open(self.fan_path + "recalculate", 'w') as f:
            f.write(str(1))

    def get_speed(self):
        with open(self.fan_path + "fan1_input", 'r') as f:
            return int(f.read().strip())

    def set_speed(self, speed):
        if speed > self.max_speed:
            speed = self.max_speed
        # if speed < self.min_speed:
        if speed < self.threshold_speed:
            speed = self.min_speed

        with open(self.fan_path + "fan1_target", 'w') as f:
            f.write(str(int(speed)))

        self.fc_speed = speed

# devices are sources of heat - CPU, GPU, etc.
class Device(object):
    def __init__(self, base_path, config, debug = False) -> None:
        self.debug = debug
        self.nice_name = config["nice_name"]
        self.file_path = get_full_path(base_path, config["name"]) + config["file"]
        self.max_temp = config["max_temp"]
        self.temp_deadzone = config["temp_deadzone"]
        self.temp = 0
        self.control_temp = 0 
        self.type = config["type"]
        if self.type == "pid":
            self.bandwidth = config["bandwidth"]
            # testing out scaling PID coefficiencts down with bandwidth, so we can tune with less dependance on bandwidth
            self.controller = PID(float(config["Kp"] / self.bandwidth), float(config["Ki"]), float(config["Kd"]))  
            self.controller.SetPoint = self.max_temp - self.bandwidth
            self.controller.setWindup(config["windup"]) # windup limits the I term of the output
        elif self.type ==  "exponential":
            self.controller = Exponential(float(config["A"]), float(config["B"]), float(config["T_threshold"]))
        elif self.type ==  "quadratic":
            self.controller = Quadratic(float(config["A"]), float(config["B"]), float(config["C"]), float(config["T_threshold"]))
        else:
            print("error loading device controller \n", exc)
            exit(1)

    # updates temperatures
    def get_temp(self) -> None:
        with open(self.file_path, 'r') as f:
            self.temp = int(f.read().strip()) / 1000
            # only update the control temp if it's outside temp_deadzone
            if math.fabs(self.temp - self.control_temp) >= self.temp_deadzone:
                self.control_temp = self.temp

    # returns PID control output, or MAX
    def get_output(self, temp_input):
        output = self.controller.update(temp_input)
        if(temp_input > self.max_temp):
            return "max"
        else:
            return max(output, 0)

# helper function to find correct hwmon* path for a given device name
def get_full_path(base_path, name):
    for directory in os.listdir(base_path):
        full_path = base_path + directory + '/'
        test_name = open(full_path + "name").read().strip()
        if test_name == name:
            return full_path
    print("failed to find device {}".format(name))

# main FanController class
class FanController(object):
    def __init__(self, debug, config_file):
        self.debug = debug

        # read in config yaml file
        if debug: print("reading config file")
        with open(config_file, "r") as f:
            try:
                self.config = yaml.safe_load(f)
            except yaml.YAMLError as exc:
                print("error loading config file \n", exc)
                exit(1)

        # store global parameters
        self.base_hwmon_path = self.config["base_hwmon_path"]
        self.loop_interval = self.config["loop_interval"]

        # initialize list of devices
        self.devices = [ Device(self.base_hwmon_path, device_config, self.debug) for device_config in self.config["devices"] ]

        # initialize fan
        fan_path = get_full_path(self.base_hwmon_path, self.config["fan_name"])
        self.fan = Fan(fan_path, self.config["fan_min_speed"], self.config["fan_threshold_speed"], self.config["fan_max_speed"], self.debug)

    # pretty print all device values, temp source, and output
    def print_single(self, source_name):
        for device in self.devices:
            if self.debug:
                print("{}: {}/{}/{}    PID:{:.0f} {:.0f} {:.0f}   ".format(device.nice_name, device.temp, device.pid.SetPoint, device.max_temp, device.pid.PTerm, device.pid.Ki * device.pid.ITerm, device.pid.Kd * device.pid.DTerm), end = '')
            else:
                print("{}: {:.1f}/{:.0f}  ".format(device.nice_name, device.temp, device.controller.output), end = '')
                #print("{}: {}  ".format(device.nice_name, device.temp), end = '')
        print("Fan[{}]: {}/{}".format(source_name, self.fan.fc_speed, self.fan.get_speed()))

    # automatic control loop
    def loop_control(self):
        while True:
            start_time = time.time()
            outputs = []
            names = []

            # names = ( [device.nice_name for device in self.devices] ) if want to move to tuples for perf

            # check temperatures
            for device in self.devices:
                device.get_temp()
                outputs.append(device.get_output(device.control_temp))
                names.append(device.nice_name)

            if "max" in outputs: # check if any devices were overtemp
                source_index = outputs.index("max")
                # set fan speed to max_speed
                self.fan.set_speed(self.fan.max_speed)
            else:
                # returns the index of the _highest output_, which is used to command the fan
                source_index = max(range(len(outputs)), key=outputs.__getitem__) 
                # set fan speed to output
                self.fan.set_speed(outputs[source_index])

            # record the name of the device that gave the highest output
            source_name = names[source_index]

            # print all values
            self.print_single(source_name)

            # sleep until interval is complete
            sleep_time = self.loop_interval - (time.time() - start_time)
            if sleep_time > 0:
                time.sleep(sleep_time)
            else: 
                if self.debug:
                    print("over-ran specified interval, skipping sleep")

# main loop
if __name__ == '__main__':
    print('jupiter-fan-control starting up ...')

    # specify config file path
    # config_file_path = os.getcwd() + "/config.yaml"
    config_file_path = "/usr/share/jupiter-fan-control/jupiter-fan-control-config.yaml"

    # initialize controller
    controller = FanController(debug = False, config_file = config_file_path)

    # start main loop
    controller.loop_control()
    
    print('jupiter-fan-control startup complete')
from __future__ import absolute_import
from __future__ import print_function, unicode_literals

import argparse
import codecs
import os
import sys
import subprocess
import threading
import glob
import shutil

import esptool

import serial

from serial.tools.list_ports import comports
from serial.tools import hexlify_codec


from pprint import pprint
import urllib.request

dev = False
spiffs = True
sota = False
cli_port = None
cli_firmware_id = None
target_port = None


def serial_ports():
    """ Lists serial port names
        :raises EnvironmentError:
            On unsupported or unknown platforms
        :returns:
            A list of the serial ports available on the system
    """
    if sys.platform.startswith('win'):
        ports = ['COM%s' % (i + 1) for i in range(256)]
    elif sys.platform.startswith('linux') or sys.platform.startswith('cygwin'):
        # this excludes your current terminal "/dev/tty"
        ports = glob.glob('/dev/cu[A-Za-z]*')
    elif sys.platform.startswith('darwin'):
        ports = glob.glob('/dev/cu.*')
    else:
        raise EnvironmentError('Unsupported platform')

    result = []
    for port in ports:
        try:
            s = serial.Serial(port)
            s.close()
            result.append(port)
        except (OSError, serial.SerialException):
            pass
    return result



def flashFirmware(answers):
    print("Port: "+answers['port'])
    print("Firmware: "+answers['firmware'])


def build_spiffs_from_project(project_dir, out_path):
    """Run PlatformIO buildfs in project_dir and copy the built SPIFFS image to out_path."""
    project_dir = os.path.abspath(project_dir)
    if not os.path.isdir(project_dir):
        raise SystemExit(1)
    try:
        subprocess.run(
            ['pio', 'run', '-t', 'buildfs'],
            cwd=project_dir,
            check=True,
            capture_output=True,
            timeout=120,
        )
    except subprocess.CalledProcessError as e:
        print('PlatformIO buildfs failed. Ensure the project has a data/ folder and board supports SPIFFS.')
        if e.stderr:
            print(e.stderr.decode('utf-8', errors='replace'))
        raise SystemExit(1)
    except FileNotFoundError:
        print('PlatformIO (pio) not found. Install it or use --no-spiffs and run "pio run -t uploadfs" from the project.')
        raise SystemExit(1)
    build_dir = os.path.join(project_dir, '.pio', 'build')
    if not os.path.isdir(build_dir):
        print('Build directory not found after buildfs.')
        raise SystemExit(1)
    # Find spiffs.bin under .pio/build/<env>/
    candidates = []
    for env_dir in os.listdir(build_dir):
        p = os.path.join(build_dir, env_dir, 'spiffs.bin')
        if os.path.isfile(p):
            candidates.append(p)
    if not candidates:
        candidates = []
        for env_dir in os.listdir(build_dir):
            for name in os.listdir(os.path.join(build_dir, env_dir)):
                if name.endswith('.bin') and 'spiffs' in name.lower():
                    candidates.append(os.path.join(build_dir, env_dir, name))
    if not candidates:
        print('No spiffs.bin found in .pio/build after buildfs.')
        raise SystemExit(1)
    src = candidates[0]
    shutil.copy2(src, out_path)
    print('Using SPIFFS image from project: ' + src)


def parse_args():
    """Parse command-line arguments for serial port, firmware ID, and options."""
    parser = argparse.ArgumentParser(
        description='Flash NCD ESP32 firmware to a device via serial port.'
    )
    parser.add_argument(
        '-p', '--port',
        dest='port',
        metavar='PORT',
        help='Serial port (e.g. /dev/cu.usbserial-0001 or COM3). If omitted, port is selected interactively.'
    )
    parser.add_argument(
        '-f', '--firmware',
        dest='firmware_id',
        metavar='ID',
        help='Firmware ID (1-30). If omitted, firmware is selected interactively. See API.md for IDs.'
    )
    parser.add_argument('-dev', '--dev', action='store_true', help='Use development firmware builds')
    parser.add_argument('-ns', '--no-spiffs', action='store_true', dest='no_spiffs', help='Do not flash SPIFFS')
    parser.add_argument('-sota', '--sota', action='store_true', help='Flash SOTA Relay firmware')
    parser.add_argument(
        '--spiffs-project-dir',
        dest='spiffs_project_dir',
        metavar='PATH',
        help='Build SPIFFS from this PlatformIO project (data/) and flash it instead of S3 image. Run: pio run -t buildfs in PATH.'
    )
    return parser.parse_args()


# Parse CLI arguments
_args = parse_args()
if _args.port:
    cli_port = _args.port
    print('Using serial port from args: ' + cli_port)
if _args.firmware_id:
    cli_firmware_id = _args.firmware_id
    print('Using firmware ID from args: ' + cli_firmware_id)
if _args.dev:
    dev = True
    print('Running dev')
if _args.no_spiffs:
    spiffs = False
    print('Not flashing spiffs')
if _args.sota:
    sota = True
    print('Sota Firmware')

cli_spiffs_project_dir = getattr(_args, 'spiffs_project_dir', None) or None
if cli_spiffs_project_dir:
    cli_spiffs_project_dir = os.path.abspath(cli_spiffs_project_dir)
    print('Using SPIFFS from project: ' + cli_spiffs_project_dir)

port_array = {}

if cli_port:
    target_port = cli_port
else:
    print('Scanning for Serial Ports')
    print('Please wait for the scan to complete')
    print('Serial Port Options:')
    for serial_port in serial_ports():
        sp_key = len(port_array)+1
        port_array.update({str(sp_key): serial_port})

    for serial_port in port_array:
        print('[' + serial_port + ']: ' + port_array.get(serial_port))
    print('')
    target_port_key = input('Please enter the number of the desired Serial Port above: ')
    target_port = port_array.get(target_port_key)

firmware_choices = {
    '1': {
        'name': 'WiFi AWS Gateway',
        'firmware': 'https://ncd-esp32.s3.us-east-1.amazonaws.com/Production_AWS/bootloader.bin',
        'spiffs': 'https://ncd-esp32.s3.us-east-1.amazonaws.com/Production_AWS/spiffs.bin',
        'bootloader': 'https://ncd-esp32.s3.us-east-1.amazonaws.com/Production_AWS/bootloader.bin',
        'partitions': 'https://ncd-esp32.s3.us-east-1.amazonaws.com/Production_AWS/partitions.bin'
    },
    '2': {
        'name': 'WiFi Azure Gateway',
        'firmware': 'https://ncd-esp32.s3.amazonaws.com/WiFi_Azure/firmware.bin',
        'spiffs': 'https://ncd-esp32.s3.amazonaws.com/WiFi_Azure/spiffs.bin',
        'bootloader': 'https://ncd-esp32.s3.amazonaws.com/WiFi_Azure/bootloader.bin',
        'partitions': 'https://ncd-esp32.s3.amazonaws.com/WiFi_Azure/partitions.bin'
    },
    '3': {
        'name': 'WiFi MQTT Gateway',
        'firmware': 'https://ncd-esp32.s3.amazonaws.com/WiFi_MQTT/firmware.bin',
        'spiffs': 'https://ncd-esp32.s3.amazonaws.com/WiFi_MQTT/spiffs.bin',
        'bootloader': 'https://ncd-esp32.s3.amazonaws.com/WiFi_MQTT/bootloader.bin',
        'partitions': 'https://ncd-esp32.s3.amazonaws.com/WiFi_MQTT/partitions.bin'
    },
    '4': {
        'name': 'WiFi Google IoT Gateway',
        'firmware': 'https://ncd-esp32.s3.amazonaws.com/WiFi_Google/firmware.bin',
        'spiffs': 'https://ncd-esp32.s3.amazonaws.com/WiFi_Google/spiffs.bin',
        'bootloader': 'https://ncd-esp32.s3.amazonaws.com/WiFi_Google/bootloader.bin',
        'partitions': 'https://ncd-esp32.s3.amazonaws.com/WiFi_Google/partitions.bin'
    },
    '5': {
        'name': 'Mega Modem',
        'firmware': 'https://ncd-esp32.s3.amazonaws.com/Mega_Modem/firmware.bin',
        'spiffs': 'https://ncd-esp32.s3.amazonaws.com/Mega_Modem/spiffs.bin',
        'bootloader': 'https://ncd-esp32.s3.amazonaws.com/Mega_Modem/bootloader.bin',
        'partitions': 'https://ncd-esp32.s3.amazonaws.com/Mega_Modem/partitions.bin'
    },
    '6': {
        'name': 'Cellular MQTT Gateway',
        'firmware': 'https://ncd-esp32.s3.amazonaws.com/Cellular_MQTT/firmware.bin',
        'spiffs': 'https://ncd-esp32.s3.amazonaws.com/Cellular_MQTT/spiffs.bin',
        'bootloader': 'https://ncd-esp32.s3.amazonaws.com/Cellular_MQTT/bootloader.bin',
        'partitions': 'https://ncd-esp32.s3.amazonaws.com/Cellular_MQTT/partitions.bin'
    },
    '7': {
        'name': 'Losant Gateway',
        'firmware': 'https://ncd-esp32.s3.amazonaws.com/WiFi_Losant/firmware.bin',
        'spiffs': 'https://ncd-esp32.s3.amazonaws.com/WiFi_Losant/spiffs.bin',
        'bootloader': 'https://ncd-esp32.s3.amazonaws.com/WiFi_Losant/bootloader.bin',
        'partitions': 'https://ncd-esp32.s3.amazonaws.com/WiFi_Losant/partitions.bin'
    },
    '8': {
        'name': '4 Relay MirPro',
        'firmware': 'https://ncd-esp32.s3.amazonaws.com/4_Relay_MirPro/firmware.bin',
        'spiffs': 'https://ncd-esp32.s3.amazonaws.com/4_Relay_MirPro/spiffs.bin',
        'bootloader': 'https://ncd-esp32.s3.amazonaws.com/4_Relay_MirPro/bootloader.bin',
        'partitions': 'https://ncd-esp32.s3.amazonaws.com/4_Relay_MirPro/partitions.bin'
    },
    '9': {
        'name': 'AWS WiFi Sensor',
        'firmware': 'https://ncd-esp32.s3.amazonaws.com/AWS_Sensor/firmware.bin',
        'spiffs': 'https://ncd-esp32.s3.amazonaws.com/AWS_Sensor/spiffs.bin',
        'bootloader': 'https://ncd-esp32.s3.amazonaws.com/AWS_Sensor/bootloader.bin',
        'partitions': 'https://ncd-esp32.s3.amazonaws.com/AWS_Sensor/partitions.bin'
    },
    '10': {
        'name': 'MQTT WiFi Sensor',
        'firmware': 'https://ncd-esp32.s3.amazonaws.com/MQTT_Sensor/firmware.bin',
        'spiffs': 'https://ncd-esp32.s3.amazonaws.com/MQTT_Sensor/spiffs.bin',
        'bootloader': 'https://ncd-esp32.s3.amazonaws.com/MQTT_Sensor/bootloader.bin',
        'partitions': 'https://ncd-esp32.s3.amazonaws.com/MQTT_Sensor/partitions.bin'
    },
    '11': {
        'name': 'Mirror PR53-4',
        'firmware': 'https://ncd-esp32.s3.amazonaws.com/Mirror_PR53-4/firmware.bin',
        'spiffs': 'https://ncd-esp32.s3.amazonaws.com/Mirror_PR53-4/spiffs.bin',
        'bootloader': 'https://ncd-esp32.s3.amazonaws.com/Mirror_PR53-4/bootloader-dev.bin',
        'partitions': 'https://ncd-esp32.s3.amazonaws.com/Mirror_PR53-4/partitions.bin'
    },
    '12': {
        'name': 'Azure WiFi Sensor',
        'firmware': 'https://ncd-esp32.s3.amazonaws.com/Azure_Sensor/firmware.bin',
        'spiffs': 'https://ncd-esp32.s3.amazonaws.com/Azure_Sensor/spiffs.bin',
        'bootloader': 'https://ncd-esp32.s3.amazonaws.com/Azure_Sensor/bootloader.bin',
        'partitions': 'https://ncd-esp32.s3.amazonaws.com/Azure_Sensor/partitions.bin'
    },
    '13': {
        'name': 'Contact Closure Email Generator',
        'firmware': 'https://ncd-esp32.s3.amazonaws.com/Email_Generator/firmware.bin',
        'spiffs': 'https://ncd-esp32.s3.amazonaws.com/Email_Generator/spiffs.bin',
        'bootloader': 'https://ncd-esp32.s3.amazonaws.com/Email_Generator/bootloader.bin',
        'partitions': 'https://ncd-esp32.s3.amazonaws.com/Email_Generator/partitions.bin'
    },
    '14': {
        'name': 'ESP XBee',
        'firmware': 'https://ncd-esp32.s3.amazonaws.com/ESP_XBee/firmware.bin',
        'spiffs': 'https://ncd-esp32.s3.amazonaws.com/ESP_XBee/spiffs.bin',
        'bootloader': 'https://ncd-esp32.s3.amazonaws.com/ESP_XBee/bootloader.bin',
        'partitions': 'https://ncd-esp32.s3.amazonaws.com/ESP_XBee/partitions.bin'
    },
    '15':{
        'name': 'WiFi Azure Gateway Custom',
        'firmware': 'https://ncd-esp32.s3.amazonaws.com/WiFi_Azure_Custom/firmware.bin',
        'spiffs': 'https://ncd-esp32.s3.amazonaws.com/WiFi_Azure_Custom/spiffs.bin',
        'bootloader': 'https://ncd-esp32.s3.amazonaws.com/WiFi_Azure_Custom/bootloader.bin',
        'partitions': 'https://ncd-esp32.s3.amazonaws.com/WiFi_Azure_Custom/partitions.bin'
    },
    '16':{
        'name': '4-20mA Input Transmitter 4 channel',
        'firmware': 'https://ncd-esp32.s3.amazonaws.com/4-20_Input_Mirror_Transmitter_4_Channel/firmware.bin',
        'spiffs': 'https://ncd-esp32.s3.amazonaws.com/4-20_Input_Mirror_Transmitter_4_Channel/spiffs.bin',
        'bootloader': 'https://ncd-esp32.s3.amazonaws.com/4-20_Input_Mirror_Transmitter_4_Channel/bootloader.bin',
        'partitions': 'https://ncd-esp32.s3.amazonaws.com/4-20_Input_Mirror_Transmitter_4_Channel/partitions.bin'
    },
    '17':{
        'name': 'Radon MN',
        'firmware': 'https://ncd-esp32.s3.amazonaws.com/radonmn_mqtt/firmware.bin',
        'spiffs': 'https://ncd-esp32.s3.amazonaws.com/radonmn_mqtt/spiffs.bin',
        'bootloader': 'https://ncd-esp32.s3.amazonaws.com/radonmn_mqtt/bootloader.bin',
        'partitions': 'https://ncd-esp32.s3.amazonaws.com/radonmn_mqtt/partitions.bin'
    },
    '18':{
        'name': '0-10VDC Input Transmitter 4 channel',
        'firmware': 'https://ncd-esp32.s3.amazonaws.com/0-10V_Input_Mirror_Transmitter_4_Channel/firmware.bin',
        'spiffs': 'https://ncd-esp32.s3.amazonaws.com/0-10V_Input_Mirror_Transmitter_4_Channel/spiffs.bin',
        'bootloader': 'https://ncd-esp32.s3.amazonaws.com/0-10V_Input_Mirror_Transmitter_4_Channel/bootloader.bin',
        'partitions': 'https://ncd-esp32.s3.amazonaws.com/0-10V_Input_Mirror_Transmitter_4_Channel/partitions.bin'
    },
    '19':{
        'name': 'Goodtech 4 channel',
        'firmware': 'https://ncd-esp32.s3.amazonaws.com/Goodtech_4_Relay/firmware.bin',
        'bootloader': 'https://ncd-esp32.s3.amazonaws.com/Goodtech_4_Relay/bootloader.bin',
        'partitions': 'https://ncd-esp32.s3.amazonaws.com/Goodtech_4_Relay/partitions.bin'
    },
    '20':{
        'name': 'SOTA Relay',
        'firmware': 'https://ncd-esp32.s3.amazonaws.com/SOTA_Relay/firmware.bin',
        'bootloader': 'https://ncd-esp32.s3.amazonaws.com/SOTA_Relay/bootloader.bin',
        'partitions': 'https://ncd-esp32.s3.amazonaws.com/SOTA_Relay/partitions.bin'
    },
    '21':{
        'name': 'Goodtech 2 relay 2 dac',
        'firmware': 'https://ncd-esp32.s3.amazonaws.com/Goodtech_2_Relay_2_Dac/firmware.bin',
        'bootloader': 'https://ncd-esp32.s3.amazonaws.com/Goodtech_2_Relay_2_Dac/bootloader.bin',
        'partitions': 'https://ncd-esp32.s3.amazonaws.com/Goodtech_2_Relay_2_Dac/partitions.bin',
        'spiffs': 'https://ncd-esp32.s3.amazonaws.com/Goodtech_2_Relay_2_Dac/spiffs.bin'
    },
    '22':{
        'name': 'RFID'
    },
    '23': {
        'name': 'MQTT V2 Temperature/Humidity Sensor',
        'firmware': 'https://ncd-esp32.s3.amazonaws.com/ESP32_V2_Sensor_Temperature_Humidity/firmware.bin',
        'spiffs': 'https://ncd-esp32.s3.amazonaws.com/ESP32_V2_Sensor_Temperature_Humidity/spiffs.bin',
        'bootloader': 'https://ncd-esp32.s3.amazonaws.com/ESP32_V2_Sensor_Temperature_Humidity/bootloader.bin',
        'partitions': 'https://ncd-esp32.s3.amazonaws.com/ESP32_V2_Sensor_Temperature_Humidity/partitions.bin'
    },
    '24':{
        'name': 'SOTA PWM',
        'firmware': 'https://ncd-esp32.s3.amazonaws.com/SOTA_PWM/firmware.bin',
        'bootloader': 'https://ncd-esp32.s3.amazonaws.com/SOTA_PWM/bootloader.bin',
        'partitions': 'https://ncd-esp32.s3.amazonaws.com/SOTA_PWM/partitions.bin'
    },
    '25':{
        'name': '8 Input Mirror Transmitter',
        'firmware': 'https://ncd-esp32.s3.amazonaws.com/eight_input_seme_mirror/firmware.bin',
        'spiffs': 'https://ncd-esp32.s3.amazonaws.com/eight_input_seme_mirror/spiffs.bin',
        'bootloader': 'https://ncd-esp32.s3.amazonaws.com/eight_input_seme_mirror/bootloader.bin',
        'partitions': 'https://ncd-esp32.s3.amazonaws.com/eight_input_seme_mirror/partitions.bin'
    },
    '26':{
        'name': 'Firmware Flasher',
        'firmware': 'https://ncd-esp32.s3.amazonaws.com/firmware_flasher/firmware.bin',
        'spiffs': 'https://ncd-esp32.s3.amazonaws.com/firmware_flasher/spiffs.bin',
        'bootloader': 'https://ncd-esp32.s3.amazonaws.com/firmware_flasher/bootloader.bin',
        'partitions': 'https://ncd-esp32.s3.amazonaws.com/firmware_flasher/partitions.bin'
    },
    '27':{
        'name': 'Stmart Repeater 2',
        'firmware': 'https://ncd-esp32.s3.amazonaws.com/Smart_Repeater_2/firmware.bin',
        'spiffs': 'https://ncd-esp32.s3.amazonaws.com/Smart_Repeater_2/spiffs.bin',
        'bootloader': 'https://ncd-esp32.s3.amazonaws.com/Smart_Repeater_2/bootloader.bin',
        'partitions': 'https://ncd-esp32.s3.amazonaws.com/Smart_Repeater_2/partitions.bin'
    },
    '28': {
        'name': 'MQTT V2 Current Monitor Sensor',
        'firmware': 'https://ncd-esp32.s3.amazonaws.com/ESP32_V2_Sensor_Current_Monitor/firmware.bin',
        'spiffs': 'https://ncd-esp32.s3.amazonaws.com/ESP32_V2_Sensor_Current_Monitor/spiffs.bin',
        'bootloader': 'https://ncd-esp32.s3.amazonaws.com/ESP32_V2_Sensor_Current_Monitor/bootloader.bin',
        'partitions': 'https://ncd-esp32.s3.amazonaws.com/ESP32_V2_Sensor_Current_Monitor/partitions.bin'
    },
    '29': {
        'name': '4-20mA 4 Channel Output Receiver',
        'firmware': 'https://ncd-esp32.s3.amazonaws.com/4-20_Output_Mirror_Transmitter_4_Channel/bootloader.bin',
        'spiffs': 'https://ncd-esp32.s3.amazonaws.com/4-20_Output_Mirror_Transmitter_4_Channel/spiffs.bin',
        'bootloader': 'https://ncd-esp32.s3.amazonaws.com/4-20_Output_Mirror_Transmitter_4_Channel/bootloader.bin',
        'partitions': 'https://ncd-esp32.s3.amazonaws.com/4-20_Output_Mirror_Transmitter_4_Channel/partitions.bin'
    },
    '30': {
        'name': 'MQTT V2 Push Notification',
        'firmware': 'https://ncd-esp32.s3.amazonaws.com/ESP32_V2_Push_Notification/firmware.bin',
        'spiffs': 'https://ncd-esp32.s3.amazonaws.com/ESP32_V2_Push_Notification/spiffs.bin',
        'bootloader': 'https://ncd-esp32.s3.amazonaws.com/ESP32_V2_Push_Notification/bootloader.bin',
        'partitions': 'https://ncd-esp32.s3.amazonaws.com/ESP32_V2_Push_Notification/partitions.bin'
    }
}

firmware_choices_dev = {
    '1': {
        'name': 'WiFi AWS Gateway',
        'firmware': 'https://ncd-esp32.s3.amazonaws.com/WiFi_AWS/firmware-dev.bin',
        'spiffs': 'https://ncd-esp32.s3.amazonaws.com/WiFi_AWS/spiffs-dev.bin',
        'bootloader': 'https://ncd-esp32.s3.amazonaws.com/WiFi_AWS/bootloader-dev.bin',
        'partitions': 'https://ncd-esp32.s3.amazonaws.com/WiFi_AWS/partitions-dev.bin'
    },
    '2': {
        'name': 'WiFi Azure Gateway',
        'firmware': 'https://ncd-esp32.s3.amazonaws.com/WiFi_Azure/firmware-dev.bin',
        'spiffs': 'https://ncd-esp32.s3.amazonaws.com/WiFi_Azure/spiffs-dev.bin',
        'bootloader': 'https://ncd-esp32.s3.amazonaws.com/WiFi_Azure/bootloader-dev.bin',
        'partitions': 'https://ncd-esp32.s3.amazonaws.com/WiFi_Azure/partitions-dev.bin'
    },
    '3': {
        'name': 'WiFi MQTT Gateway',
        'firmware': 'https://ncd-esp32.s3.amazonaws.com/WiFi_MQTT/firmware-dev.bin',
        'spiffs': 'https://ncd-esp32.s3.amazonaws.com/WiFi_MQTT/spiffs-dev.bin',
        'bootloader': 'https://ncd-esp32.s3.amazonaws.com/WiFi_MQTT/bootloader-dev.bin',
        'partitions': 'https://ncd-esp32.s3.amazonaws.com/WiFi_MQTT/partitions-dev.bin'
    },
    '4': {
        'name': 'WiFi Google IoT Gateway',
        'firmware': 'https://ncd-esp32.s3.amazonaws.com/WiFi_Google/firmware-dev.bin',
        'spiffs': 'https://ncd-esp32.s3.amazonaws.com/WiFi_Google/spiffs-dev.bin',
        'bootloader': 'https://ncd-esp32.s3.amazonaws.com/WiFi_Google/bootloader-dev.bin',
        'partitions': 'https://ncd-esp32.s3.amazonaws.com/WiFi_Google/partitions-dev.bin'
    },
    '5': {
        'name': 'Mega Modem',
        'firmware': 'https://ncd-esp32.s3.amazonaws.com/Mega_Modem/firmware-dev.bin',
        'spiffs': 'https://ncd-esp32.s3.amazonaws.com/Mega_Modem/spiffs-dev.bin',
        'bootloader': 'https://ncd-esp32.s3.amazonaws.com/Mega_Modem/bootloader-dev.bin',
        'partitions': 'https://ncd-esp32.s3.amazonaws.com/Mega_Modem/partitions-dev.bin'
    },
    '6': {
        'name': 'Cellular MQTT Gateway',
        'firmware': 'https://ncd-esp32.s3.amazonaws.com/Cellular_MQTT/firmware-dev.bin',
        'spiffs': 'https://ncd-esp32.s3.amazonaws.com/Cellular_MQTT/spiffs-dev.bin',
        'bootloader': 'https://ncd-esp32.s3.amazonaws.com/Cellular_MQTT/bootloader-dev.bin',
        'partitions': 'https://ncd-esp32.s3.amazonaws.com/Cellular_MQTT/partitions-dev.bin'
    }
}

status_code = 1  # default to failure; set to 0 on success
try:
    if sota:
        firmware_file = urllib.request.urlretrieve('https://ncd-esp32.s3.amazonaws.com/SOTA_Relay/firmware.bin', './firmware.bin')
        partitions_file = urllib.request.urlretrieve('https://ncd-esp32.s3.amazonaws.com/SOTA_Relay/partitions.bin', './partitions.bin')
        bootloader_file = urllib.request.urlretrieve('https://ncd-esp32.s3.amazonaws.com/SOTA_Relay/bootloader.bin', './bootloader.bin')
        espmodule = esptool.main(['--chip', 'esp32', '--port', target_port, '--baud', '921600', '--before', 'default_reset', '--after', 'hard_reset', 'write_flash', '-z', '--flash_mode', 'dio', '--flash_freq', '40m', '--flash_size', 'detect', '0x1000', 'bootloader.bin', '0x8000', 'partitions.bin', '0x10000', 'firmware.bin'])
        status_code = 0
        raise SystemExit(0)

    if cli_firmware_id is not None:
        firmware_choice = cli_firmware_id
        choices = firmware_choices_dev if dev else firmware_choices
        if firmware_choice not in choices:
            print('Error: Invalid firmware ID "{}". Must be 1-30 (or 1-6 for -dev).'.format(firmware_choice))
            raise SystemExit(1)
    else:
        print('Firmware Choices:')
        for firmware in firmware_choices:
            print('['+firmware+']: ' + firmware_choices.get(firmware).get('name'))
        print('')
        firmware_choice = input('Please enter the number of the desired firmware: ')

    if firmware_choice == '19' or firmware_choice == '20':
        spiffs = False;

    # if firmware_choice == '22':
    #     __location__ = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))
    #     firmware_file = open(os.path.join(__location__, 'firmware.bin'))
    #     spiffs_file = open(os.path.join(__location__, 'spiffs.bin'))
    #     bootloader_file = open(os.path.join(__location__, 'bootloader.bin'))
    #     partitions_file = open(os.path.join(__location__, 'partitions.bin'))
    #     espmodule = esptool.main(['--chip', 'esp32', '--port', port_array.get(target_port_key), '--baud', '921600', '--before', 'default_reset', '--after', 'hard_reset', 'write_flash', '-z', '--flash_mode', 'dio', '--flash_freq', '40m', '--flash_size', 'detect', '0x1000', 'bootloader.bin', '0x8000', 'partitions.bin', '0x00290000', 'spiffs.bin', '0x10000', 'firmware.bin'])

    if(dev):
        firmware = firmware_choices_dev.get(firmware_choice)
    else:
        firmware = firmware_choices.get(firmware_choice)

    # For option 1, use local files from AWS directory instead of downloading
    if firmware_choice == '1':
        print('Using local firmware files for WiFi AWS Gateway from AWS directory')
        __location__ = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))
        aws_dir = os.path.join(__location__, 'AWS')
        
        # Check if local files exist in AWS directory
        local_files = {
            'firmware': os.path.join(aws_dir, 'firmware.bin'),
            'spiffs': os.path.join(aws_dir, 'spiffs.bin'),
            'bootloader': os.path.join(aws_dir, 'bootloader.bin'),
            'partitions': os.path.join(aws_dir, 'partitions.bin'),
            'boot_app0': os.path.join(aws_dir, 'boot_app0.bin')
        }
        
        missing_files = [name for name, path in local_files.items() if not os.path.exists(path)]
        if missing_files:
            print(f'Error: Missing local files in AWS directory: {", ".join(missing_files)}')
            print(f'Looking in: {aws_dir}')
            raise SystemExit(1)
        
        print(f'Found local firmware files in: {aws_dir}')
        # Copy files from AWS directory to current directory for flashing
        import shutil
        for name, src_path in local_files.items():
            dest_path = os.path.join(__location__, f'{name}.bin')
            shutil.copy2(src_path, dest_path)
            print(f'Copied {name}.bin from AWS directory')

    if firmware_choice != '22' and firmware_choice != '1':
        print('[PROGRESS] Downloading firmware...')
        sys.stdout.flush()
        firmware_file = urllib.request.urlretrieve(str(firmware.get('firmware')), './firmware.bin')
        print('[PROGRESS] Firmware downloaded')

        if spiffs:
            spiffs_dest = os.path.join(os.getcwd(), 'spiffs.bin')
            if cli_spiffs_project_dir:
                print('[PROGRESS] Building SPIFFS from project...')
                sys.stdout.flush()
                build_spiffs_from_project(cli_spiffs_project_dir, spiffs_dest)
                print('[PROGRESS] SPIFFS built')
            else:
                print('[PROGRESS] Downloading SPIFFS...')
                sys.stdout.flush()
                spiffs_file = urllib.request.urlretrieve(str(firmware.get('spiffs')), spiffs_dest)
                print('[PROGRESS] SPIFFS downloaded')

            print('[PROGRESS] Downloading bootloader...')
            sys.stdout.flush()
            bootloader_file = urllib.request.urlretrieve(str(firmware.get('bootloader')), './bootloader.bin')
            print('[PROGRESS] Bootloader downloaded')

            print('[PROGRESS] Downloading partitions...')
            sys.stdout.flush()
            partitions_file = urllib.request.urlretrieve(str(firmware.get('partitions')), './partitions.bin')
            print('[PROGRESS] Partitions downloaded')

            # Copy boot_app0.bin from AWS directory (standard ESP32 file needed for flashing)
            __location__ = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))
            aws_boot_app0 = os.path.join(__location__, 'AWS', 'boot_app0.bin')
            if os.path.exists(aws_boot_app0):
                import shutil
                shutil.copy2(aws_boot_app0, './boot_app0.bin')
                print('[PROGRESS] Copied boot_app0.bin')
            else:
                print(f'Warning: boot_app0.bin not found in AWS directory: {aws_boot_app0}')

            print('')
            print('[PROGRESS] Starting upload to device...')
            sys.stdout.flush()

    if firmware_choice == '1':
        espmodule = esptool.main(['--chip', 'esp32', '--port', target_port, '--baud', '460800', '--before', 'default_reset', '--after', 'hard_reset', 'write_flash', '-z', '--flash_mode', 'dio', '--flash_freq', '80m', '--flash_size', '4MB', '0x1000', 'bootloader.bin', '0x8000', 'partitions.bin', '0xe000', 'boot_app0.bin', '0x10000', 'firmware.bin'])
        espmodule = esptool.main(['--chip', 'esp32', '--port', target_port, '--baud', '460800', 'write_flash', '0x290000', 'spiffs.bin'])
    else:
        if spiffs:
            # Only 5 and 14 use custom layout (spiffs at 0x383000). Others use default: spiffs at 0x290000.
            if firmware_choice in ('5', '14'):
                espmodule = esptool.main(['--chip', 'esp32', '--port', target_port, '--baud', '921600', '--before', 'default_reset', '--after', 'hard_reset', 'write_flash', '-z', '--flash_mode', 'dio', '--flash_freq', '40m', '--flash_size', 'detect', '0x1000', 'bootloader.bin', '0x8000', 'partitions.bin', '0x00383000', 'spiffs.bin', '0x10000', 'firmware.bin'])
            else:
                # Flash all required files: bootloader, partitions, boot_app0, firmware, and spiffs
                espmodule = esptool.main(['--chip', 'esp32', '--port', target_port, '--baud', '460800', '--before', 'default_reset', '--after', 'hard_reset', 'write_flash', '-z', '--flash_mode', 'dio', '--flash_freq', '80m', '--flash_size', '4MB', '0x1000', 'bootloader.bin', '0x8000', 'partitions.bin', '0xe000', 'boot_app0.bin', '0x10000', 'firmware.bin', '0x290000', 'spiffs.bin'])
        else:
            print('no spiffs')
            espmodule = esptool.main(['--chip', 'esp32', '--port', target_port, '--baud', '921600', '--before', 'default_reset', '--after', 'hard_reset', 'write_flash', '-z', '--flash_mode', 'dio', '--flash_freq', '40m', '--flash_size', 'detect', '0x1000', 'bootloader.bin', '0x10000', 'firmware.bin'])
except SystemExit as e:
    status_code = e.code if e.code is not None else 1
except Exception as e:
    print('Status: Failure')
    print(str(e))
    status_code = 1
else:
    status_code = 0

if status_code == 0:
    print('Status: Success')
else:
    print('Status: Failure')
sys.exit(status_code)

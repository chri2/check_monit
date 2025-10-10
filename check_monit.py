#!/usr/bin/env python3

# monit.h Reference
# typedef enum {
#         Monitor_Not     = 0x0,
#         Monitor_Yes     = 0x1,
#         Monitor_Init    = 0x2,
#         Monitor_Waiting = 0x4
# } Monitor_State;

# typedef enum {
#         State_Succeeded  = 0x0,
#         State_Failed     = 0x1,
#         State_Changed    = 0x2,
#         State_ChangedNot = 0x4,
#         State_Init       = 0x8,
#         State_None       = State_Init // Alias
# } State_Type;

# typedef enum {
#         Service_Filesystem = 0,
#         Service_Directory,
#         Service_File,
#         Service_Process,
#         Service_Host,
#         Service_System,
#         Service_Fifo,
#         Service_Program,
#         Service_Net,
#         Service_Last = Service_Net
# } Service_Type;

import sys
import argparse
from xml.etree import ElementTree

import requests


__version__ = '0.1.0'

icinga_status = {
    0: 'OK',
    1: 'WARNING',
    2: 'CRITICAL',
    3: 'UNKNOWN'
}

def commandline(args):

    parser = argparse.ArgumentParser(prog="check_monit.py")

    parser.add_argument('-V', '--version', action='version', version=__version__)
    parser.add_argument('-H', '--host', dest='host', default='http://localhost', type=str,
                        help='Hostname of the Monit instance (default: http://localhost)')
    parser.add_argument('-p', '--port', dest='port', default=2812, type=int,
                        help='Port of the Monit instance')
    parser.add_argument('-U', '--user', dest='user', required=True, type=str,
                        help='HTTP username')
    parser.add_argument('-P', '--pass', dest='password', required=True, type=str,
                        help='HTTP password')

    return parser.parse_args(args)


def print_output(status, count_ok, count_all, items):
    s = icinga_status[status]

    print(f"[{s}]: Monit Service Status {count_ok}/{count_all}")

    if len(items):
        for item in items:
            s = "OK" if item['status'] == 0 else "CRITICAL"
            print(' \\_ [{0}]: {1}'.format(s, item['name']))
            print('  ' + item['output'])


def get_service_output(service_type, element):
    # Service Type Filesystem
    if service_type == 0:
        block = float(element.findall('block/percent')[0].text)
        inode = float(element.findall('inode/percent')[0].text)
        return 'user={0}%;inodes={1}%'.format(block, inode)

    # Service Type Process
    if service_type == 3:
        status = element.find('status').text
        return status

    # Service Type Host
    if service_type == 5:
        output = []

        load1 = float(element.findall('system/load/avg01')[0].text)
        load5 = float(element.findall('system/load/avg05')[0].text)
        load15 = float(element.findall('system/load/avg15')[0].text)
        output.append('load={0},{1},{2}'.format(load1, load5, load15))

        user = float(element.findall('system/cpu/user')[0].text)
        system = float(element.findall('system/cpu/system')[0].text)
        nice = float(element.findall('system/cpu/nice')[0].text)
        hardirq = float(element.findall('system/cpu/hardirq')[0].text)
        output.append('user={0}%;system={1}%;nice={2}%;hardirq={3}%'.format(user, system, nice, hardirq))

        memory = float(element.findall('system/memory/percent')[0].text)
        output.append('memory={0}%'.format(memory))

        return ';'.join(output)

    # Service Type Program
    if service_type == 7:
        return_value = None
        for output_item in element.findall('program/output'):
            # type( output_item ) is <class 'xml.etree.ElementTree.Element'>
            return_value = output_item.text if return_value is None else f"{return_value}; {output_item.text}"
        if return_value is None:
            return_value = 'no command output available'

        return return_value

    return 'Service (type={0}) not implemented'.format(service_type)

def get_service_states(services):
    items = []
    count_all = 0
    count_ok = 0

    for service in services:
        # Get the monitor state for the service (0: Not, 1: Yes, 2: Init, 4: Waiting)
        monitor = int(service.find('monitor').text)
        # ignore 'Monitor_not' (0)
        if monitor != 0:
            status = int(service.find('status').text)
            if status == 0:
                count_ok += 1

            count_all += 1

            items.append({
                "name": service.find('name').text,
                "status": status,
                "output": get_service_output(int(service.get('type')), service)
            })

    return items, count_all, count_ok

def main(args):
    url = '{0}:{1}/_status?format=xml'.format(args.host, args.port)

    try:
        r = requests.get(url, auth=(args.user, args.password), timeout=5)
    except Exception as e: # pylint: disable=broad-except
        print('[UNKNOWN]: Could not connect to Monit. error={0}'.format(str(e)))
        return 3

    status_code = r.status_code

    if status_code != 200:
        print('[UNKNOWN]: No valid response from Monit HTTP Server. error={0}'.format(status_code))
        return 3

    try:
        tree = ElementTree.fromstring(r.content)
    except Exception as e: # pylint: disable=broad-except
        print('[UNKNOWN]: Unable to parse XML response from Monit HTTP Server. error={0}'.format(str(e)))
        return 3

    services = tree.findall('service')
    items, count_all, count_ok = get_service_states(services)

    exit_status = 0
    if count_ok < count_all:
        exit_status = 2

    if count_ok == 0:
        exit_status = 2

    print_output(exit_status, count_ok, count_all, items)

    return exit_status


if __package__ == '__main__' or __package__ is None: # pragma: no cover
    try:
        ARGS = commandline(sys.argv[1:])
        sys.exit(main(ARGS))
    except Exception: # pylint: disable=broad-except
        exception = sys.exc_info()
        print("[UNKNOWN] Unexpected Python error: %s %s" % (exception[0], exception[1]))
        sys.exit(3)

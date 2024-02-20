#!/usr/bin/env python3

# https://github.com/prtzb/epdu-tools.git

import socket
from time import sleep
import argparse
import re
import sys
import paramiko
import socket

class ePDUException(Exception):
    def __init__(self, *args, **kwargs):
        super(ePDUException, self).__init__(*args)
        self.error = kwargs.get("error", None)

class ePDU():

    def __init__(self, host='machine', user='admin', password='admin'):
        self._host = host
        self._user = user
        self._pass = password
        self._channel = None
        self._client = None
        self._logged_in = False
        self._prompt = None
        self._info = None

    @staticmethod
    def _is_part_number_ok(pn):
        supported = [
            'EILB13',
            'EILB14',
            'EILB15',
            'EMIH28',
            'EMAB04'
        ]

        if pn in supported:
            return True
        return False

    @staticmethod
    def _is_serial_ok(serial):
        try:
            return bool(re.match('[A-Z0-9]{10}', serial))
        except TypeError:
            return False

    @staticmethod
    def _is_version_ok(version):
        try:
            return bool(re.match('[0-9]{2}.[0-9]{2}.[0-9]{4}', version))
        except TypeError:
            return False

    def login(self):

        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.load_system_host_keys()
            client.connect(self._host, username=self._user,
                           password=self._pass, allow_agent=False,
                           look_for_keys=False)
        except socket.timeout:
            print("%s time out" % (self._host))
            return False
        except 	paramiko.BadHostKeyException as exc:
            print("Server host key could not be verified: %s" % (exc))
            return False
        except paramiko.AuthenticationException:
            print("Authentication failed: %s" % (self._host))
            return False
        except paramiko.SSHException as exc:
            print("Unable to establish SSH connection: %s" % (exc))
            return False

        channel = client.invoke_shell()
        while channel.recv_ready() is False:
            sleep(1)

        self._client = client
        self._channel = channel
        self._prompt = channel.recv(4096)
        self._info = self._get_info()
        self._logged_in = True

        return True

    def logout(self):
        if self._logged_in:
            self._logged_in = False
            self._send_command('quit')
            self._channel.close()
            self._client.close()
        else:
            print('Not logged in.')

    def _send_command(self, cmd):

        send = str(cmd + '\r').encode('utf-8')

        channel = self._channel
        channel.send(send)
        while channel.recv_ready() is False:
            sleep(0.5)

        stdout = channel.recv(1024)
        response = stdout.strip(self._prompt).strip(send)
        reply = response.decode('utf-8').replace('\r', '').replace('\n', '')

        return reply

    def _get_info(self):
        objects = [
            'PDU.PowerSummary.iSerialNumber',
            'PDU.PowerSummary.iPartNumber',
            'PDU.PowerSummary.iVersion',
            'PDU.OutletSystem.Outlet.Count'
        ]
        params = {}
        for option in objects:
            params[option] = self.get_object(option)

        # Validations
        if not self._is_version_ok(params['PDU.PowerSummary.iVersion']):
            raise ePDUException(
                'Validation Error: FW version ' + str(objects['PDU.PowerSummary.iVersion']))

        if not self._is_serial_ok(params['PDU.PowerSummary.iSerialNumber']):
            raise ePDUException('Validation Error: Serial Number ' +
                                str(objects['PDU.PowerSummary.iSerialNumber']))

        if not self._is_part_number_ok(params['PDU.PowerSummary.iPartNumber']):
            raise ePDUException('Validation Error: Part Number ' +
                                str(objects['PDU.PowerSummary.iPartNumber']))

        return params

    def get_object(self, option):
        option = 'get ' + option
        return self._send_command(option)

    def set_object(self, option, val):
        cmd = 'set ' + option + ' ' + val
        return self._send_command(cmd)

    def number_of_outlets(self):
        cnt = self._info['PDU.OutletSystem.Outlet.Count']
        return int(cnt)

    def show_information(self):
        for key in self._info:
            print('{}: {}'.format(key, self._info[key]));

    def turn_on_outlet(self, outlet):
        # https://superuser.com/questions/1425481/how-to-toggle-outlet-power-to-eaton-epdu-g3-from-shell-script
        option = 'PDU.OutletSystem.Outlet[{}].DelayBeforeStartup'.format(
            outlet)
        self.set_object(option, '0')

    def turn_off_outlet(self, outlet):
        option = 'PDU.OutletSystem.Outlet[{}].DelayBeforeShutdown'.format(
            outlet)
        self.set_object(option, '0')


def main():
    args = argparse.ArgumentParser()
    args.add_argument('--ip', dest='address', type=str, required=True,
                      help='IP address of the Eaton ePDU')
    args.add_argument('--password', dest='password', type=str, required=True,
                      help='eDPU user password')
    args.add_argument('--user', dest='username', type=str, required=True,
                      help='eDPU user name')
    args.add_argument('--on', dest='on', action='append', type=int,
                      help='Turn ON relay <number>')
    args.add_argument('--off', dest='off', action='append', type=int,
                      help='Turn OFF relay <number>')
    args.add_argument('--info', dest='info', action='store_true',
                      help='Show Eaton ePDU information')

    args = args.parse_args()

    if not args.on and not args.off and not args.info:
        sys.exit(0)

    pdu = ePDU(args.address, args.username, args.password)

    if not pdu.login():
         sys.exit(1)

    if args.info:
        pdu.show_information()

    if args.on:
        for num in args.on:
            if num < 1 or num > pdu.number_of_outlets():
                print('No such outlet: {}', num)
                continue
            pdu.turn_on_outlet(num)

    if args.off:
        for num in args.off:
            if num < 1 or num > pdu.number_of_outlets():
                print('No such outlet: {}', num)
                continue
            pdu.turn_off_outlet(num)

    pdu.logout()

    sys.exit(0)




if __name__ == '__main__':

    try:
        main()
    except KeyboardInterrupt:
        pass

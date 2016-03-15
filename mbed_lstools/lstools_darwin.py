"""
mbed SDK
Copyright (c) 2011-2015 ARM Limited

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import sys
import re
import subprocess
import plistlib
import logging

from lstools_base import MbedLsToolsBase
from term_formats import fixedWidthFormat, treeLogger


class MbedLsToolsDarwin(MbedLsToolsBase):
    """ MbedLsToolsDarwin supports mbed-enabled platforms detection on Mac OS X
    """

    mbed_volume_name_match = re.compile(r'(\bmbed\b|\bSEGGER MSD\b)', re.I)

    def __init__(self, debug=False):
        MbedLsToolsBase.__init__(self)
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.CRITICAL)
        if debug:
            logger.setLevel(logging.DEBUG)

        # set the logging format
        ww = 18
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(fixedWidthFormat(width=ww))
        logger.addHandler(ch)
        # pass the logging module into the treeLogger class
        # that it will use
        self.treeShow = treeLogger(log_module=logger, log_prefix_width=ww)

    def list_mbeds(self):
        """ returns mbed list with platform names if possible
        """
        result = []

        # {volume_id: {serial:, vendor_id:, product_id:, tty:}}
        volumes = self.get_mbed_volumes()

        # {volume_id: mount_point}
        mounts = self.get_mount_points()

        volumes_keys = set(volumes.keys())
        mounts_keys = set(mounts.keys())
        intersection = volumes_keys & mounts_keys

        valid_volumes = {}

        for key in intersection:
            valid_volumes[key] = volumes[key]

        # put together all of that info into the expected format:
        result =  [
            {
                 'mount_point': mounts[v],
                 'serial_port': volumes[v]['tty'],
                   'target_id': self.target_id(volumes[v]),
               'platform_name': self.platform_name(self.target_id(volumes[v]))
            } for v in valid_volumes
        ]

        self.ERRORLEVEL_FLAG = 0

        # if we're missing any platform names, try to fill those in by reading
        # mbed.htm:
        for i, _ in enumerate(result):
            if None in result[i]:
                self.ERRORLEVEL_FLAG = -1
                continue

            if result[i]['mount_point']:
                # Deducing mbed-enabled TargetID based on available targetID definition DB.
                # If TargetID from USBID is not recognized we will try to check URL in mbed.htm
                htm_target_id = self.get_mbed_htm_target_id(result[i]['mount_point'])
                if htm_target_id:
                    result[i]['target_id_usb_id'] = result[i]['target_id']
                    result[i]['target_id'] = htm_target_id
                    result[i]['platform_name'] = self.platform_name(htm_target_id[:4])
                result[i]['target_id_mbed_htm'] = htm_target_id

        return result

    def get_mount_points(self):
        ''' Returns map {volume_id: mount_point} '''

        # list disks, this gives us disk name, and volume name + mount point:
        diskutil_ls = subprocess.Popen(['diskutil', 'list', '-plist'], stdout=subprocess.PIPE)
        disks = plistlib.readPlist(diskutil_ls.stdout)
        diskutil_ls.wait()

        r = {}

        for disk in disks['AllDisksAndPartitions']:
            mount_point = None
            if 'MountPoint' in disk:
                mount_point = disk['MountPoint']
            r[disk['DeviceIdentifier']] = mount_point

        return r

    def get_mbed_volumes(self):
        ''' returns a map {volume_id: {serial:, vendor_id:, product_id:, tty:}
        '''

        def has_children(obj, child_key='IORegistryEntryChildren'):
            if obj is not None and 'IORegistryEntryChildren' in obj:
                return True
            return False

        def get_children(obj, child_key='IORegistryEntryChildren'):
            if has_children(obj, child_key=child_key):
                return obj[child_key]
            return None

        def is_mbed_root(obj):
            if 'sessionID' in obj and 'bcdDevice' in obj:
                return True
            return False

        def get_drive_info():
            ''' finds and returns a list of connected usb drives. '''
            res = None
            q = subprocess.Popen(
                ['system_profiler', 'SPUSBDataType', '-detailLevel', 'full', '-xml'], stdout=subprocess.PIPE)
            try:
                res = plistlib.readPlist(q.stdout)
            except:
                pass
            finally:
                q.wait()

            return res[0]['_items']

        def filter_io_reg(obj):
            ''' filters the queried data and returns an array containing
                all of the mbed entry trees.
            '''
            r = []
            for i in obj:
                for j in i:
                    if j == 'IORegistryEntryName' and i[j] == 'Root':
                        c = i
                        while has_children(c):
                            c = get_children(c)
                            if is_mbed_root(c):
                                r.append(c)
                                break
            return r

        def filter_system_profiler(obj):
            ''' filters the data from the system_profiler call. '''
            r = []
            if not isinstance(obj, list):
                obj = [obj]

            for o in obj:
                for x in filter(lambda k: k == '_items', o.keys()):
                    try:
                        for i in o['_items']:
                            # recurse through all of the child nodes
                            if '_items' in i:
                                r.extend(filter_system_profiler(i))

                            search_term = i['_name']
                            if 'manufacturer' in i:
                                search_term += ' ' + i['manufacturer']

                            if self.mbed_volume_name_match.search(search_term) and 'bsd_name' in i:
                                r.append(i)
                    except:
                        continue
            return r

        def get_disk_id(obj, sn):
            ''' returns the bsd name when given a mbed serial number. '''
            try:
                for dev in obj:
                    if 'serial_num' in dev and 'bsd_name' in dev and dev['serial_num'] == sn:
                        return dev['bsd_name']
            except:
                return None

        # Now we query for a tree leading to all BSD client entries of the registry - we
        # can parse the rest of things from this
        res = None
        ioreg_query = subprocess.Popen(
            ['ioreg', '-a', '-t', '-l', '-r', '-c', 'IOSerialBSDClient'], stdout=subprocess.PIPE)
        try:
            res = plistlib.readPlist(ioreg_query.stdout)
        except:
            # Catch when no output is returned from ioreg command
            pass
        finally:
            # wait for the results
            ioreg_query.wait()

        # select each found mbed root tree
        serial_devs = None
        mbed_drives = None
        try:
            serial_devs = filter_io_reg(res)
            mbed_drives = filter_system_profiler(get_drive_info())
        except:
            pass
        finally:
            self.treeShow.show(serial_devs)
            self.treeShow.show(mbed_drives)

        r = {}

        def set_mbed_devs(obj):
            """ sets the return value for the parent function, get_mbed_volumes()
            """

            def find_tty(obj):
                """ return the first tty (AKA IODialinDevice) that we can find in the
                    children of the specified object, or None if no tty is present.
                """
                if isinstance(obj, dict) and 'IODialinDevice' in obj:
                    return obj['IODialinDevice']
                if has_children(obj):
                    return find_tty(get_children(obj))
                return None

            # select the entries that have mbed in their name
            for k, v in obj.items():
                if isinstance(v, dict):
                    set_mbed_devs(v)
                elif (k == 'IORegistryEntryName' or k == 'kUSBVendorString' or k == 'USB Vendor Name') and self.mbed_volume_name_match.search(v):
                    usb_info = {
                        'serial': None, 'vendor_id': None, 'product_id': None, 'tty': None, }
                    if 'idVendor' in obj:
                        usb_info['vendor_id'] = obj['idVendor']
                    if 'idProduct' in obj:
                        usb_info['product_id'] = obj['idProduct']
                    if 'USB Serial Number' in obj:
                        usb_info['serial'] = obj['USB Serial Number']
                        # stop at the first one we find (or we'll pick up hubs,
                        # etc.), but first check for a tty that's also a child of
                        # this device:
                        usb_info['tty'] = find_tty(obj)
                        # set the bsd name that lines up with the serial
                        # number
                        disk_id = get_disk_id(mbed_drives, usb_info['serial'])
                        r[disk_id] = usb_info

        if serial_devs:
            for obj in serial_devs:
                set_mbed_devs(obj)

        return r

    def target_id(self, usb_info):
        if usb_info['serial'] is not None:
            return usb_info['serial']
        else:
            return None

    def platform_name(self, target_id):
        if target_id[:4] in self.manufacture_ids:
            return self.manufacture_ids[target_id[:4]]

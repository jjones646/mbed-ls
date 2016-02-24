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

import os
import logging


class fixedWidthFormat(logging.Formatter):
    """ Class that defines a fixed-width format for log message prefixes that
        are shown before the log message itself.
    """
    def __init__(self, width=15):
        self.width = width

    def format(self, record):
        max_chars = self.width - len(str(record.lineno))
        fn = record.filename[:max_chars]
        if len(record.filename) > self.width:
            fn = fn[:-3] + '..'
        a = '{}:{}'.format(fn, record.lineno)
        return '[{}] {}'.format(a.ljust(self.width), record.msg)


class treeLogger:
    ''' Use the treeLogger class to recursively show large
        data trees that are an assortment of dicts/lists.
    '''
    TAB_PREFIX = 4 * ' '
    DEPTH = 0

    def __init__(self, log_module, prefix=None, log_prefix_width=0):
        if prefix is not None:
            self.tabPrefix = prefix
        else:
            self.tabPrefix = self.TAB_PREFIX

        if log_module is None:
            self.logger = logging.basicConfig(level=logging.INFO)
            self.logger.setLevel(logging.CRITICAL)
        else:
            self.logger = log_module

        self.log_prefix_width = log_prefix_width + 3

    def show_dict(self, d, depth=0):
        ''' recursively print a dictionary
        '''
        # find the max number of characters in all of the keys
        max_key_width = reduce(lambda a, b: a if (a > b) else b, [len(k) for k in d.keys()])

        for k in filter(lambda k: isinstance(d[k], basestring) or isinstance(d[k], int), d.keys()):
            self.logger.info('{}{}{}  =>  {}'.format((self.tabPrefix * depth), k, (max_key_width - len(k)) * ' ', d[k]))

        for k in sorted(filter(lambda k: isinstance(d[k], dict), d.keys()), key=lambda fk: len(d[fk])):
            self.logger.info('{}{}{}'.format(((len(self.tabPrefix) * depth) - 2) * '=', '> ', k))
            self.show_dict(d[k], depth + 1)

    def show(self, t, depth=0):
        ''' recursively print an intertangled list/dictionary structure
            to a given depth within each dictionary
        '''
        if isinstance(t, list):
            for tree in t:
                self.show(tree, depth=depth)
                self.logger.info(80 * '~')
        if isinstance(t, dict):
            self.show_dict(t, depth=depth)

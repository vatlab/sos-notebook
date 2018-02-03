#!/usr/bin/env python
#
# This file is part of Script of Scripts (sos), a workflow system
# for the execution of commands and scripts in different languages.
# Please visit https://github.com/vatlab/SOS for more information.
#
# Copyright (C) 2016 Bo Peng (bpeng@mdanderson.org)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#


import json
import os
import sys
import argparse
import shutil
import logging

from jupyter_client.kernelspec import KernelSpecManager
from IPython.utils.tempdir import TemporaryDirectory

kernel_json = {
    "argv":         [sys.executable, "-m", "sos_notebook.kernel", "-f", "{connection_file}"],
    "display_name": "SoS",
    "language":     "sos",
}

def _is_root():
    try:
        return os.geteuid() == 0
    except AttributeError:
        return False # assume not an admin on non-Unix platforms

def get_install_sos_kernel_spec_parser():
    parser = argparse.ArgumentParser(description='Install KernelSpec for sos Kernel')
    prefix_locations = parser.add_mutually_exclusive_group()
    prefix_locations.add_argument('--user',
        help='Install KernelSpec in user homedirectory',
        action='store_true')
    prefix_locations.add_argument('--sys-prefix',
        help='Install KernelSpec in sys.prefix. Useful in conda / virtualenv',
        action='store_true',
        dest='sys_prefix')
    prefix_locations.add_argument('--prefix',
        help='Install KernelSpec in this prefix',
        default=None) 
    return parser

def install_sos_kernel_spec(args):
    user = False
    prefix = None
    if args.sys_prefix:
        prefix = sys.prefix
    elif args.prefix:
        prefix = args.prefix
    elif args.user or not _is_root():
        user = True

    with TemporaryDirectory() as td:
        os.chmod(td, 0o755) # Starts off as 700, not user readable
        with open(os.path.join(td, 'kernel.json'), 'w') as f:
            json.dump(kernel_json, f, sort_keys=True)
        # Copy resources once they're specified
        shutil.copy(os.path.join(os.path.split(__file__)[0], 'kernel.js'), os.path.join(td, 'kernel.js'))
        shutil.copy(os.path.join(os.path.split(__file__)[0], 'logo-64x64.png'), os.path.join(td, 'logo-64x64.png'))

        KS = KernelSpecManager()
        KS.log.setLevel(logging.ERROR)
        KS.install_kernel_spec(td, 'sos', user=user, replace=True, prefix=prefix)
        print('sos jupyter kernel spec is installed')


if __name__ == '__main__':
    parser = get_install_sos_kernel_spec_parser()
    args = parser.parse_args()
    install_sos_kernel_spec(args)

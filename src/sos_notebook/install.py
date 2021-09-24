#!/usr/bin/env python
#
# Copyright (c) Bo Peng and the University of Texas MD Anderson Cancer Center
# Distributed under the terms of the 3-clause BSD License.

import argparse
import json
import os
import shutil
import sys

from IPython.utils.tempdir import TemporaryDirectory
from jupyter_client.kernelspec import KernelSpecManager
from jupyter_contrib_core.notebook_compat import nbextensions
from traitlets.config.manager import BaseJSONConfigManager

_py_ver = sys.version_info
if _py_ver.major == 2 or (_py_ver.major == 3 and
                          (_py_ver.minor, _py_ver.micro) < (6, 0)):
    raise SystemError(
        'sos requires Python 3.6 or higher. Please upgrade your Python {}.{}.{}.'
        .format(_py_ver.major, _py_ver.minor, _py_ver.micro))

kernel_json = {
    "argv": [
        sys.executable, "-m", "sos_notebook.kernel", "-f", "{connection_file}"
    ],
    "display_name": "SoS",
    "language": "sos",
}


def _is_root():
    try:
        return os.geteuid() == 0
    except AttributeError:
        return False  # assume not an admin on non-Unix platforms


def get_install_sos_kernel_spec_parser():
    parser = argparse.ArgumentParser(
        description='Install KernelSpec for sos Kernel')
    prefix_locations = parser.add_mutually_exclusive_group()
    prefix_locations.add_argument(
        '--user',
        help='Install KernelSpec in user homedirectory',
        action='store_true')
    prefix_locations.add_argument(
        '--sys-prefix',
        help='Install KernelSpec in sys.prefix. Useful in conda / virtualenv',
        action='store_true',
        dest='sys_prefix')
    prefix_locations.add_argument(
        '--prefix', help='Install KernelSpec in this prefix', default=None)
    return parser


def install_sos_kernel_spec(user, prefix):

    with TemporaryDirectory() as td:
        os.chmod(td, 0o755)  # Starts off as 700, not user readable
        with open(os.path.join(td, 'kernel.json'), 'w') as f:
            json.dump(kernel_json, f, sort_keys=True)
        # Copy resources once they're specified
        shutil.copy(
            os.path.join(os.path.split(__file__)[0], 'kernel.js'),
            os.path.join(td, 'kernel.js'))
        shutil.copy(
            os.path.join(os.path.split(__file__)[0], 'logo-64x64.png'),
            os.path.join(td, 'logo-64x64.png'))

        KS = KernelSpecManager()
        KS.install_kernel_spec(td, 'sos', user=user, prefix=prefix)
        destination = KS._get_destination_dir('sos', user=user, prefix=prefix)
        print(f'sos jupyter kernel spec is installed to {destination}')


def install_config(user, prefix):
    config_dir = nbextensions._get_config_dir(user=user, sys_prefix=prefix)

    # Set extra template path
    cm = BaseJSONConfigManager(config_dir=os.path.join(config_dir, 'nbconfig'))
    default_config = {
        'notebook_console_panel': 'auto',
        'kernel_codemirror_mode': {
            'python': {
                'name': "python",
                'version': 3
            },
            'python2': {
                'name': "python",
                'version': 2
            },
            'python3': {
                'name': "python",
                'version': 3
            },
            'r': "r",
            'report': "report",
            'pandoc': "markdown",
            'download': "markdown",
            'markdown': "markdown",
            'ruby': "ruby",
            'sas': "sas",
            'bash': "shell",
            'sh': "shell",
            'julia': "julia",
            'run': "shell",
            'javascript': "javascript",
            'typescript': {
                'name': "javascript",
                'typescript': True
            },
            'octave': "octave",
            'matlab': "octave",
            'mllike': "mllike",
            'clike': "clike",
            'html': "htmlembedded",
            'xml': "xml",
            'yaml': "yaml",
            'json': {
                'name': "javascript",
                'jsonMode': True
            },
            'stex': "stex",
        }
    }
    config = cm.get('notebook')
    if 'sos' not in config:
        config['sos'] = default_config
    else:
        sos_config = config['sos']
        if 'notebook_console_panel' not in sos_config:
            sos_config['notebook_console_panel'] = default_config[
                'notebook_console_panel']
        if 'kernel_codemirror_mode' not in sos_config:
            sos_config['kernel_codemirror_mode'] = default_config[
                'kernel_codemirror_mode']
        else:
            for key in default_config['kernel_codemirror_mode']:
                if key not in sos_config['kernel_codemirror_mode']:
                    sos_config['kernel_codemirror_mode'][key] = default_config[
                        'kernel_codemirror_mode'][key]
        config['sos'] = sos_config
    # avoid warnings about unset version
    cm.set('notebook', config)
    print(f'Settings added or updated in {config_dir}/nbconfig/notebook.json')
    print(
        'If you notice problems with the kernel, you will need to use AsyncMappingKernelManager as kernel manager'
    )
    print(
        'Please see https://github.com/jupyter/notebook/issues/6164 for details.'
    )


if __name__ == '__main__':
    parser = get_install_sos_kernel_spec_parser()
    args = parser.parse_args()
    user = False
    prefix = None
    if args.sys_prefix:
        prefix = sys.prefix
    elif args.prefix:
        prefix = args.prefix
    elif args.user or not _is_root():
        user = True

    install_sos_kernel_spec(user, prefix)
    install_config(user, prefix)

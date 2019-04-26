#!/usr/bin/env python3
#
# Copyright (c) Bo Peng and the University of Texas MD Anderson Cancer Center
# Distributed under the terms of the 3-clause BSD License.

import pydoc

from sos.syntax import SOS_USAGES
from sos.utils import env
from .magics import SoS_Magics


class SoS_VariableInspector(object):

    def __init__(self, kernel):
        self.kernel = kernel
        self.preview_magic = kernel.magics.get('preview')

    def inspect(self, name, line, pos):
        try:
            obj_desc, preview = self.preview_magic.preview_var(name, style=None)
            if preview is None:
                return {}
            else:
                format_dict, md_dict = preview
                if 'text/plain' in format_dict:
                    return format_dict
                else:
                    return {
                        'text/plain':
                            f'{repr(env.sos_dict["name"])} ({obj_desc})'
                    }
        except Exception:
            return {}


class SoS_SyntaxInspector(object):

    def __init__(self, kernel):
        self.kernel = kernel

    def inspect(self, name, line, pos):
        if line.startswith(
                '%') and name in SoS_Magics.names and pos <= len(name) + 1:
            try:
                magic = SoS_Magics(self.kernel).get(name)
                parser = magic.get_parser()
                return {'text/plain': parser.format_help()}
            except Exception as e:
                return {'text/plain': f'Magic %{name}: {e}'}
        elif line.startswith(name + ':') and pos <= len(name):
            if self.kernel.original_keys is None:
                self.kernel._reset_dict()
            # input: etc
            if name in SOS_USAGES:
                return {'text/plain': SOS_USAGES[name]}
            elif name in env.sos_dict:
                # action?
                return {
                    'text/plain':
                        pydoc.render_doc(
                            env.sos_dict[name],
                            title='%s',
                            renderer=pydoc.plaintext),
                    'text/html':
                        pydoc.render_doc(
                            env.sos_dict[name], title='%s', renderer=pydoc.html)
                }
            else:
                return {}
        else:
            return {}


class SoS_Inspector(object):

    def __init__(self, kernel):
        self.inspectors = [
            SoS_SyntaxInspector(kernel),
            SoS_VariableInspector(kernel),
        ]

    def inspect(self, name, line, pos):
        for c in self.inspectors:
            try:
                data = c.inspect(name, line, pos)
                if data:
                    return data
            except Exception:
                continue
        # No match
        return {}

#!/usr/bin/env python3
#
# Copyright (c) Bo Peng and the University of Texas MD Anderson Cancer Center
# Distributed under the terms of the 3-clause BSD License.

import glob
import os
import rlcompleter

from sos.utils import env
from .magics import SoS_Magics

def last_valid(line):
    text = line
    for char in (' ', '\t', '"', "'", '=', '('):
        if text.endswith(char):
            text = ''
        elif char in text:
            text = text.rsplit(char, 1)[-1]
    return text


class SoS_MagicsCompleter:
    def __init__(self, kernel):
        self.kernel = kernel

    def get_completions(self, line):
        text = last_valid(line)

        if not text.strip():
            if line.startswith('%get'):
                return text, [x for x in env.sos_dict.keys() if x not in
                              self.kernel.original_keys and not x.startswith('_')]
            elif any(line.startswith(x) for x in ('%use', '%with', '%shutdown')):
                return text, ['SoS'] + list(self.kernel.supported_languages.keys())
            else:
                return None
        elif text.startswith('%') and line.startswith(text):
            return text, ['%' + x + ' ' for x in SoS_Magics.names if x.startswith(text[1:])]
        elif any(line.startswith(x) for x in ('%use', '%with', '%shutdown')):
            return text, [x for x in self.kernel.supported_languages.keys() if x.startswith(text)]
        elif line.startswith('%get '):
            return text, [x for x in env.sos_dict.keys() if x.startswith(text)
                          and x not in self.kernel.original_keys and not x.startswith('_')]
        else:
            return None


class SoS_PathCompleter:
    '''PathCompleter.. The problem with ptpython's path completor is that
    it only matched 'text_before_cursor', which would not match cases such
    as %cd ~/, which we will need.'''

    def __init__(self):
        pass

    def get_completions(self, line):
        text = last_valid(line)

        if not text.strip():
            return text, glob.glob('*')
        else:
            matches = glob.glob(os.path.expanduser(text) + '*')
            if len(matches) == 1 and matches[0] == os.path.expanduser(text) \
                    and os.path.isdir(os.path.expanduser(text)):
                return text, glob.glob(os.path.expanduser(text) + '/*')
            else:
                return text, matches


class PythonCompleter:
    def __init__(self):
        pass

    def get_completions(self, line):
        text = last_valid(line)

        completer = rlcompleter.Completer(env.sos_dict._dict)
        return text, completer.global_matches(text)


class SoS_Completer(object):
    def __init__(self, kernel):
        self.completers = [
            SoS_MagicsCompleter(kernel),
            SoS_PathCompleter(),
            PythonCompleter(),
        ]

    def complete_text(self, code, cursor_pos=None):
        if cursor_pos is None:
            cursor_pos = len(code)

        # get current line before cursor
        doc = code[:cursor_pos].rpartition('\n')[2]

        for c in self.completers:
            matched = c.get_completions(doc)
            if matched is None:
                continue
            elif isinstance(matched, tuple):
                if matched[1]:
                    return matched
            else:
                raise RuntimeError(f'Unrecognized completer return type {matched}')
        # No match
        return '', []

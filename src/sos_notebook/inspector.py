#!/usr/bin/env python3
#
# Copyright (c) Bo Peng and the University of Texas MD Anderson Cancer Center
# Distributed under the terms of the 3-clause BSD License.

import pydoc
from typing import Dict, List, Union

from sos.syntax import SOS_USAGES
from sos.utils import env

from .magics import SoS_Magics


class SoS_VariableInspector:
    def __init__(self, kernel) -> None:
        self.kernel = kernel
        self.preview_magic = kernel.magics.get("preview")

    def inspect(self, name: str, line: str, pos: int) -> Dict[str, str]:
        try:
            obj_desc, preview = self.preview_magic.preview_var(name, style=None)
            if preview is None:
                return {}
            format_dict, _ = preview
            if "text/plain" in format_dict:
                return format_dict
            return {"text/plain": f"{repr(env.sos_dict['name'])} ({obj_desc})"}
        except Exception:
            return {}


class SoS_SyntaxInspector:
    def __init__(self, kernel) -> None:
        self.kernel = kernel

    def inspect(self, name: str, line: str, pos: int) -> Dict[str, str]:
        if line.startswith("%") and name in SoS_Magics.names and pos <= len(name) + 1:
            try:
                magic = SoS_Magics(self.kernel).get(name)
                parser = magic.get_parser()
                return {"text/plain": parser.format_help()}
            except Exception as e:
                return {"text/plain": f"Magic %{name}: {e}"}
        if line.startswith(name + ":") and pos <= len(name):
            if self.kernel.original_keys is None:
                self.kernel._reset_dict()
            # input: etc
            if name in SOS_USAGES:
                return {"text/plain": SOS_USAGES[name]}
            if name in env.sos_dict:
                # action?
                return {
                    "text/plain": pydoc.render_doc(
                        env.sos_dict[name], title="%s", renderer=pydoc.plaintext
                    ),
                    "text/html": pydoc.render_doc(
                        env.sos_dict[name], title="%s", renderer=pydoc.html
                    ),
                }
        return {}


class SoS_Inspector:
    def __init__(self, kernel) -> None:
        self.inspectors: List[Union[SoS_SyntaxInspector, SoS_VariableInspector]] = [
            SoS_SyntaxInspector(kernel),
            SoS_VariableInspector(kernel),
        ]

    def inspect(self, name: str, line: str, pos: int) -> Dict[str, str]:
        for c in self.inspectors:
            try:
                data = c.inspect(name, line, pos)
                if data:
                    return data
            except Exception:
                continue
        # No match
        return {}

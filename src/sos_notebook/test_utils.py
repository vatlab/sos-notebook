#!/usr/bin/env python3
#
# Copyright (c) Bo Peng and the University of Texas MD Anderson Cancer Center
# Distributed under the terms of the 3-clause BSD License.

import asyncio
import atexit
import os
import re
import time
from contextlib import contextmanager
from queue import Empty
from textwrap import dedent

import pytest
from jupyter_client import KernelManager

pjoin = os.path.join

TIMEOUT = 60

KM = None
KC = None


def start_new_kernel(kernel_name="python3"):
    """Start a new kernel and return the manager and client."""
    km = KernelManager(kernel_name=kernel_name)
    km.start_kernel()
    kc = km.client()
    kc.start_channels()
    try:
        kc.wait_for_ready(timeout=TIMEOUT)
    except RuntimeError:
        kc.stop_channels()
        km.shutdown_kernel()
        raise
    return km, kc


@contextmanager
def sos_kernel():
    """Context manager for the global kernel instance

    Returns
    -------
    kernel_client: connected KernelClient instance
    """
    yield start_sos_kernel()


def flush_channels(kc=None):
    """flush any messages waiting on the queue"""
    if kc is None:
        kc = KC
    for channel in (kc.shell_channel, kc.iopub_channel):
        while True:
            try:
                channel.get_msg(timeout=0.1)
            except Empty:
                break


def start_sos_kernel():
    """start the global kernel (if it isn't running) and return its client"""
    global KM, KC
    if KM is None:
        KM, KC = start_new_kernel(kernel_name="sos")
        atexit.register(stop_sos_kernel)
    else:
        flush_channels(KC)
    return KC


def stop_sos_kernel():
    """Stop the global shared kernel instance, if it exists"""
    global KM, KC
    KC.stop_channels()
    KC = None
    if KM is None:
        return
    KM.shutdown_kernel(now=False)
    KM = None


def get_result(iopub):
    """retrieve result from an execution"""
    return asyncio.run(_async_get_result(iopub))


async def _async_get_result(iopub):
    result = None
    while True:
        msg = await iopub.get_msg(timeout=1)
        msg_type = msg["msg_type"]
        content = msg["content"]
        if msg_type == "status" and content["execution_state"] == "idle":
            break
        if msg["msg_type"] == "execute_result":
            result = content["data"]
        elif msg["msg_type"] == "display_data":
            result = content["data"]
    from numpy import array, matrix, uint8

    _ = array
    _ = matrix
    _ = uint8

    def dict_keys(args):
        return args

    if result is None:
        return None
    return eval(result["text/plain"])


def get_display_data(iopub, data_type="text/plain"):
    """retrieve display_data from an execution from subkernel"""
    return asyncio.run(_async_get_display_data(iopub, data_type))


async def _async_get_display_data(iopub, data_type):
    result = None
    while True:
        msg = await iopub.get_msg(timeout=1)
        msg_type = msg["msg_type"]
        content = msg["content"]
        if msg_type == "status" and content["execution_state"] == "idle":
            break
        if msg["msg_type"] == "display_data":
            if isinstance(data_type, str):
                if data_type in content["data"]:
                    result = content["data"][data_type]
            else:
                for dt in data_type:
                    if dt in content["data"]:
                        result = content["data"][dt]
        elif msg["msg_type"] == "execute_result":
            result = content["data"]["text/plain"]
    return result


def clear_channels(iopub):
    """assemble stdout/err from an execution"""
    return asyncio.run(_async_clear_channels(iopub))


async def _async_clear_channels(iopub):
    while True:
        msg = await iopub.get_msg(timeout=1)
        msg_type = msg["msg_type"]
        content = msg["content"]
        if msg_type == "status" and content["execution_state"] == "idle":
            break


def get_std_output(iopub):
    """Obtain stderr and remove some unnecessary warning from
    https://github.com/jupyter/jupyter_client/pull/201#issuecomment-314269710"""
    stdout = []
    stderr = []
    while True:
        try:
            msg = iopub.get_msg(timeout=1)
        except Empty:
            break
        msg_type = msg["msg_type"]
        content = msg["content"]
        if msg_type == "status" and content["execution_state"] == "idle":
            break
        if msg_type == "stream":
            if content["name"] == "stdout":
                stdout.append(content["text"])
            elif content["name"] == "stderr":
                stderr.append(content["text"])
        elif msg_type == "error":
            stderr.append("\n".join(content["traceback"]))
    return "".join(stdout), "\n".join(
        x
        for x in "".join(stderr).splitlines()
        if "sticky" not in x
        and "RuntimeWarning" not in x
        and "communicator" not in x
    )


class NotebookTest:
    """Base test class for kernel tests"""


class Notebook:
    """Notebook interface for kernel testing.

    Executes code in the SoS kernel and supports switching between
    subkernels (R, Python3, etc.) using the %use magic.
    """

    def __init__(self, kernel_client=None):
        self.kc = kernel_client or start_sos_kernel()
        self.current_kernel = "SoS"

    def _execute_and_collect(self, code):
        """Execute code and collect all iopub messages until idle.

        Returns (stdout, stderr, result, all_messages) where result is
        the text/plain from execute_result or display_data if any.
        """
        self.kc.execute(code)
        self.kc.get_shell_msg(timeout=TIMEOUT)

        stdout = []
        stderr = []
        result = None
        messages = []

        while True:
            try:
                msg = self.kc.get_iopub_msg(timeout=5)
            except Empty:
                break
            messages.append(msg)
            msg_type = msg["msg_type"]
            content = msg["content"]
            if msg_type == "status" and content["execution_state"] == "idle":
                break
            if msg_type == "stream":
                if content["name"] == "stdout":
                    stdout.append(content["text"])
                elif content["name"] == "stderr":
                    stderr.append(content["text"])
            elif msg_type == "execute_result":
                if "text/plain" in content.get("data", {}):
                    result = content["data"]["text/plain"]
            elif msg_type == "display_data":
                if "text/plain" in content.get("data", {}):
                    result = content["data"]["text/plain"]
            elif msg_type == "error":
                stderr.append("\n".join(content["traceback"]))

        return "".join(stdout), "".join(stderr), result, messages

    def _switch_kernel(self, kernel):
        """Switch to a different kernel using %use magic."""
        if kernel != self.current_kernel:
            self._execute_and_collect(f"%use {kernel}")
            self.current_kernel = kernel

    def check_output(self, code, kernel="SoS"):
        """Execute code in the specified kernel and return output as string."""
        self._switch_kernel(kernel)
        code = dedent(code).strip()
        stdout, stderr, result, _ = self._execute_and_collect(code)
        if result is not None:
            return result
        return stdout

    def call(self, code, kernel="SoS"):
        """Execute code in the specified kernel without returning output."""
        self._switch_kernel(kernel)
        code = dedent(code).strip()
        self._execute_and_collect(code)

    def save(self):
        """No-op: save is a frontend concept, not applicable in kernel testing."""

    def get_input_backgroundColor(self, idx=0):
        """Not available without frontend. Returns None."""
        return None

    def get_cell_output(self, idx=0):
        """Drain any pending iopub messages and return accumulated output.

        This is used to poll for output from background tasks (%run &).
        """
        output = []
        while True:
            try:
                msg = self.kc.get_iopub_msg(timeout=1)
                if msg["msg_type"] == "stream":
                    output.append(msg["content"]["text"])
                elif msg["msg_type"] == "status" and msg["content"]["execution_state"] == "idle":
                    break
            except Empty:
                break
        return "".join(output)

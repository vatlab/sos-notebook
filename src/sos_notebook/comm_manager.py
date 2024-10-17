"""Base class to manage comms"""

# Copyright (c) IPython Development Team.
# Distributed under the terms of the Modified BSD License.

import logging
import time

import traitlets
import traitlets.config
from ipykernel.comm.manager import CommManager

logger = logging.getLogger("soskernel.comm")


class CommProxyHandler(object):

    def __init__(self, KC, sos_kernel):
        self._KC = KC
        self._sos_kernel = sos_kernel

    def handle_msg(self, msg):
        self._KC.shell_channel.send(msg)
        # wait for subkernel to handle
        comm_msg_started = False
        comm_msg_ended = False
        while not (comm_msg_started and comm_msg_ended):
            while self._KC.iopub_channel.msg_ready():
                sub_msg = self._KC.iopub_channel.get_msg()
                if sub_msg['header']['msg_type'] == 'status':
                    if sub_msg["content"]["execution_state"] == 'busy':
                        comm_msg_started = True
                    elif comm_msg_started and sub_msg["content"]["execution_state"] == 'idle':
                        comm_msg_ended = True
                    continue
                self._sos_kernel.session.send(self._sos_kernel.iopub_socket, sub_msg)
            time.sleep(0.001)


class SoSCommManager(CommManager):
    '''This comm manager will replace the system default comm manager.
    When a comm is requested, it will return a `CommProxyHandler` instead
    of a real comm if the comm is created by the subkerel.
    '''
    kernel = traitlets.Instance("sos_notebook.kernel.SoS_Kernel")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._forwarders = {}

    def register_subcomm(self, comm_id, KC, sos_kernel):
        self._forwarders[comm_id] = CommProxyHandler(KC, sos_kernel)

    def get_comm(self, comm_id):
        try:
            return self.comms[comm_id]
        except Exception:
            if comm_id in self._forwarders:
                # self._sos_kernel.start_forwarding_ioPub()
                return self._forwarders[comm_id]
            self.log.warning("No such comm: %s", comm_id)
            if self.log.isEnabledFor(logging.DEBUG):
                # don't create the list of keys if debug messages aren't enabled
                self.log.debug("Current comms: %s", list(self.comms.keys()))

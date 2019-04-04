import unittest

from ipykernel.tests.utils import execute, wait_for_idle, assemble_output
from sos_notebook.test_utils import sos_kernel

class TestSoSKernel(unittest.TestCase):
    def testKernel(self):
        with sos_kernel() as kc:
            execute(kc=kc, code='a = 1\nprint(a)')
            stdout, stderr = assemble_output(kc.iopub_channel)
            self.assertEqual(stderr, '')
            self.assertEqual(stdout.strip(), '1')

if __name__ == '__main__':
    unittest.main()

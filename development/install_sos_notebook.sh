#!/usr/bin/bash
pip install . -U
python -m sos_notebook.install

# Install test dependencies
pip install pytest selenium webdriver-manager testpath

# jupyter notebook

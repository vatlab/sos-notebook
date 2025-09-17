#!/usr/bin/bash
pip install . -U
python -m sos_notebook.install

# Install test dependencies
pip install pytest pytest-playwright testpath

# Install playwright browsers
python -m playwright install chromium

# jupyter notebook

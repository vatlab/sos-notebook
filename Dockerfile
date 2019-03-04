# Copyright (c) Bo Peng and the University of Texas MD Anderson Cancer Center
# Distributed under the terms of the 3-clause BSD License.

# SoS official docker image for latest version of SoS. Use command
#
#     docker build -t mdabioinfo/sos-notebook:latest docker-notebook
#
# to build it.
#

# tag created in Fev 2019
FROM jupyter/datascience-notebook:83ed2c63671f

MAINTAINER Bo Peng <bpeng@mdanderson.org>

USER    root

#       Tools
RUN     apt-get update
RUN     apt-get install -y graphviz
RUN     apt-get install -y texlive-xetex texlive-latex-recommended texlive-latex-extra texlive-fonts-recommended


RUN     apt-get install -y libgmp3-dev
RUN     apt-get install -y software-properties-common



USER    jovyan

#       Bash
RUN     pip install bash_kernel
RUN     python -m bash_kernel.install --user

# SOS
RUN     pip install  markdown wand graphviz imageio pillow nbformat coverage codacy-coverage pytest pytest-cov python-coveralls

RUN     conda install -y feather-format -c conda-forge

## trigger rerun for sos updates
ARG	    DUMMY=unknown
RUN     DUMMY=${DUMMY} pip install sos  sos-r sos-python sos-bash --upgrade


RUN pip install selenium

USER    root
RUN apt-get -y update && apt-get install -y  libssl1.0.0 libssl-dev

RUN curl https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb -o /chrome.deb
RUN dpkg -i /chrome.deb || apt-get install -yf
RUN rm /chrome.deb

RUN wget -q "https://chromedriver.storage.googleapis.com/73.0.3683.20/chromedriver_linux64.zip" -O /tmp/chromedriver.zip \
    && unzip /tmp/chromedriver.zip -d /usr/bin/ \
    && rm /tmp/chromedriver.zip
ENV DISPLAY=:99


RUN ln -s /usr/bin/chromedriver && chmod 777 /usr/bin/chromedriver 

COPY . sos_notebook
RUN cd ./sos_notebook/ && pip install . -U
RUN python -m sos_notebook.install
RUN chmod 777 /home/jovyan/.local/share/jupyter/
USER    jovyan

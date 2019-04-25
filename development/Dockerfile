# Copyright (c) Bo Peng and the University of Texas MD Anderson Cancer Center
# Distributed under the terms of the 3-clause BSD License.

# tag created in March 2019

FROM jupyter/r-notebook:83ed2c63671f

MAINTAINER Bo Peng <bpeng@mdanderson.org>

USER    root


#       Tools
RUN     apt-get update && apt-get install -y graphviz texlive-xetex texlive-latex-recommended texlive-latex-extra texlive-fonts-recommended libssl1.0.0 libssl-dev libappindicator3-1  libxtst6 libgmp3-dev software-properties-common rsync ssh

USER    jovyan

RUN     pip install bash_kernel selenium nose
RUN     python -m bash_kernel.install --user

RUN     pip install  markdown wand graphviz imageio pillow nbformat coverage codacy-coverage pytest pytest-cov python-coveralls
RUN     conda install -y feather-format -c conda-forge
RUN 	conda install -c r r-feather

## trigger rerun for sos updates
ARG	    DUMMY=unknown
RUN     DUMMY=${DUMMY} pip install sos  sos-r sos-python sos-bash --upgrade

USER    root
RUN curl https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb -o /chrome.deb
RUN dpkg -i /chrome.deb || apt-get install -yf
RUN rm /chrome.deb

RUN wget -q "https://chromedriver.storage.googleapis.com/73.0.3683.20/chromedriver_linux64.zip" -O /tmp/chromedriver.zip \
    && unzip /tmp/chromedriver.zip -d /usr/bin/ \
    && rm /tmp/chromedriver.zip
ENV DISPLAY=:99

RUN ln -s /usr/bin/chromedriver && chmod 777 /usr/bin/chromedriver
RUN chmod 777 /home/jovyan/.local/share/jupyter/


COPY ./development/.ssh /root/.ssh
RUN chmod 700 /root/.ssh
RUN chmod 600 /root/.ssh/*

COPY ./development/.ssh /home/jovyan/.ssh
RUN chmod 700 /home/jovyan/.ssh
RUN chmod 600 /home/jovyan/.ssh/*

USER    jovyan

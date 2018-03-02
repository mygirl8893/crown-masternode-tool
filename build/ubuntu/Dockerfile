FROM ubuntu:17.10
MAINTAINER \
[TheSin- <thesin@southofheaven.org>]
RUN apt-get update \
 && apt-get -y upgrade \
 && apt-get -y install libudev-dev libusb-1.0-0-dev libfox-1.6-dev autotools-dev autoconf automake libtool libpython3-all-dev python3-pip git \
 && pip3 install virtualenv \
 && cd ~ \
 && mkdir tmt \
 && cd tmt \
 && virtualenv -p python3 venv \
 && . venv/bin/activate \
 && pip install --upgrade setuptools \
 && git clone https://github.com/TheSin-/terracoin-masternode-tool \
 && cd terracoin-masternode-tool/ \
 && pip install -r requirements.txt \
 && cd ~/tmt \
 && echo "#!/bin/sh" | tee build-tmt.sh \
 && echo "cd ~/tmt" | tee -a build-tmt.sh \
 && echo ". venv/bin/activate" | tee -a build-tmt.sh \
 && echo "cd terracoin-masternode-tool" | tee -a build-tmt.sh \
 && echo "git fetch --all" | tee -a build-tmt.sh \
 && echo "git reset --hard origin/master" | tee -a build-tmt.sh \
 && echo "pip install -r requirements.txt" | tee -a build-tmt.sh \
 && echo "pyinstaller --distpath=../dist/linux --workpath=../dist/linux/build terracoin_masternode_tool.spec" | tee -a build-tmt.sh \
 && echo "cd .." | tee -a build-tmt.sh \
 && chmod +x build-tmt.sh

CMD ~/tmt/build-tmt.sh

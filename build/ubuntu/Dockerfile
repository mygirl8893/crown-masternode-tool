FROM ubuntu:17.10
MAINTAINER \
[walkjivefly <mark@walkjivefly.com>]
RUN apt-get update \
 && apt-get -y upgrade \
 && apt-get -y install libudev-dev libusb-1.0-0-dev libfox-1.6-dev autotools-dev autoconf automake libtool libpython3-all-dev python3.6-dev python3-pip git cmake \
 && pip3 install virtualenv \
 && cd ~ \
 && mkdir cmt \
 && cd cmt \
 && virtualenv -p python3 venv \
 && . venv/bin/activate \
 && pip install --upgrade setuptools \
 && git clone https://github.com/walkjivefly/crown-masternode-tool \
 && cd crown-masternode-tool/ \
 && pip install -r requirements.txt \
 && cd ~/cmt \
 && echo "#!/bin/sh" | tee build-cmt.sh \
 && echo "cd ~/cmt" | tee -a build-cmt.sh \
 && echo ". venv/bin/activate" | tee -a build-cmt.sh \
 && echo "cd crown-masternode-tool" | tee -a build-cmt.sh \
 && echo "git fetch --all" | tee -a build-cmt.sh \
 && echo "git reset --hard origin/master" | tee -a build-cmt.sh \
 && echo "pip install -r requirements.txt" | tee -a build-cmt.sh \
 && echo "pyinstaller --distpath=../dist/linux --workpath=../dist/linux/build crown_masternode_tool.spec" | tee -a build-cmt.sh \
 && echo "cd .." | tee -a build-cmt.sh \
 && chmod +x build-cmt.sh

CMD ~/cmt/build-cmt.sh

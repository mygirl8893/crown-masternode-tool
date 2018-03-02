FROM fedora
MAINTAINER \
[TheSin- <thesin@southofheaven.org>]
RUN yum update -y \
 && yum group install -y "Development Tools" "Development Libraries" \
 && yum install -y redhat-rpm-config python3-devel libusbx-devel libudev-devel \
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
 && set +H \
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

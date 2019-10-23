FROM fedora
MAINTAINER \
[defunctec <defuncteconomics@gmail.com>>]
RUN yum update -y \
 && yum group install -y "Development Tools" "Development Libraries" \
 && yum install -y redhat-rpm-config python3-devel libusbx-devel libudev-devel cmake gcc-c++ \
 && yum remove -y gmp-devel \
 && pip3 install virtualenv \
 && cd ~ \
 && mkdir cmt \
 && cd cmt \
 && virtualenv -p python3 venv \
 && . venv/bin/activate \
 && pip install --upgrade setuptools \
 && git clone https://github.com/defunctec/crown-masternode-tool \
 && cd crown-masternode-tool/ \
 && pip install -r requirements.txt \
 && cd ~/cmt \
 && set +H \
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

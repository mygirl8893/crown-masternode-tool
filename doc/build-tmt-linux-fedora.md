## Building the Terracoin Masternode Tool executable on Fedora Linux

### Method based on physical or virtual linux machine

Execute the following commands from the terminal:

```
[tmt@fedora /]# sudo yum update -y
[tmt@fedora /]# sudo yum group install -y "Development Tools" "Development Libraries"
[tmt@fedora /]# sudo yum install -y redhat-rpm-config python3-devel libusbx-devel libudev-devel
[tmt@fedora /]# sudo pip3 install virtualenv
[tmt@fedora /]# cd ~
[tmt@fedora /]# mkdir tmt && cd tmt
[tmt@fedora /]# virtualenv -p python3 venv
[tmt@fedora /]# . venv/bin/activate
[tmt@fedora /]# pip install --upgrade setuptools
[tmt@fedora /]# git clone https://github.com/TheSin-/terracoin-masternode-tool
[tmt@fedora /]# cd terracoin-masternode-tool/
[tmt@fedora /]# pip install -r requirements.txt
[tmt@fedora /]# pyinstaller --distpath=../dist/linux --workpath=../dist/linux/build terracoin_masternode_tool.spec
```

The following files will be created once the build has completed successfully:
* Executable: `~/tmt/dist/linux/TerracoinMasternodeTool`
* Compressed executable: `~/tmt/dist/all/TerracoinMasternodeTool_<verion_string>.linux.tar.gz`


### Method based on Docker

This method uses a dedicated **docker image** configured to carry out an automated build process for *Terracoin Masternode Tool*. The advantage of this method is its simplicity and the fact that it does not make any changes in the list of installed apps/libraries on your physical/virtual machine. All necessary dependencies are installed inside the Docker container. The second important advantage is that compilation can also be carried out on Windows or macOS (if Docker is installed), but keep in mind that the result of the build will be a Linux executable.

> **Note: Skip steps 3 and 4 if you are not performing this procedure for the first time (building a newer version of TMT, for example)**

#### 1. Create a new directory
We will refer to this as the *working directory* in the remainder of this documentation.

#### 2. Open the terminal app and `cd` to the *working directory*

```
cd <working_directory>
```

#### 3. Install the *TheSin-/build-tmt* Docker image

Skip this step if you have done this before. At any time, you can check whether the required image exists in your local machine by issuing following command:

```
docker images TheSin-/build-tmt
```

The required image can be obtained in one of two ways:

**Download from Docker Hub**

Execute the following command:

```
docker pull TheSin-/build-tmt
```

**Build the image yourself, using the Dockerfile file from the TMT project repository.** 

* Download the https://github.com/TheSin-/terracoin-masternode-tool/blob/master/build/fedora/Dockerfile file and place it in the *working directory*
* Execute the following command:
```
docker build -t TheSin-/build-tmt .
```

#### 4. Create a Docker container

A Docker container is an instance of an image (similar to how an object is an instance of a class in the software development world), and it exists until you delete it. You can therefore skip this step if you have created the container before. To easily identify the container, we give it a specific name (tmtbuild) when it is created so you can easily check if it exists in your system.

```
docker ps -a --filter name=tmtbuild --filter ancestor=TheSin-/build-tmt
```
Create the container:

``` 
docker create --name tmtbuild -it TheSin-/build-tmt
```

#### 5. Build the Terracoin Masternode Tool executable

```
docker start -ai tmtbuild
```

#### 6. Copy the build result to your *working directory*

```
docker cp tmtbuild:/root/tmt/dist/all tmt-executable
```

This command completes the procedure. The `tmt-executable` directory inside your *working directory* will contain a compressed Terracoin Masternode Tool executable.

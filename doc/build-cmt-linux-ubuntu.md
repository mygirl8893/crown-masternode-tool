## Building the Crown Masternode Tool executable on Ubuntu Linux

### Method based on physical or virtual linux machine

An Ubuntu distribution with Python 3.6 is required to build CMT. This example uses Ubuntu 18.04, which comes with an appropriate version installed by default. You can verify the Python version by typing:

```
python3 --version
```

You should see a response similar to the following:

  `Python 3.6.8`

After making sure that you have the correct Python version, execute the following commands from the terminal:

```
[cmt@ubuntu /]# sudo apt-get update
[cmt@ubuntu /]# sudo apt-get -y upgrade
[cmt@ubuntu /]# sudo apt-get -y install libcurl4 libudev-dev libusb-1.0-0-dev libfox-1.6-dev autotools-dev autoconf automake libtool libpython3-all-dev python3.6-dev python3-pip git cmake
[cmt@ubuntu /]# sudo pip3 install virtualenv
[cmt@ubuntu /]# sudo pip3 install --upgrade pip
[cmt@ubuntu /]# cd ~
[cmt@ubuntu /]# mkdir cmt && cd cmt
[cmt@ubuntu /]# virtualenv -p python3.6 venv
[cmt@ubuntu /]# . venv/bin/activate
[cmt@ubuntu /]# pip install --upgrade setuptools
[cmt@ubuntu /]# git clone https://github.com/defunctec/crown-masternode-tool
[cmt@ubuntu /]# cd crown-masternode-tool/
[cmt@ubuntu /]# pip install -r requirements.txt
[cmt@ubuntu /]# pyinstaller --distpath=../dist/linux --workpath=../dist/linux/build crown_masternode_tool.spec
```

The following files will be created once the build has completed successfully:

* Executable: `~/cmt/dist/linux/CrownMasternodeTool`
* Compressed executable: `~/cmt/dist/all/CrownMasternodeTool_<verion_string>.linux.tar.gz`


### TODO: Method based on Docker

This method uses a dedicated **docker image** configured to carry out an automated build process for *Crown Masternode Tool*. The advantage of this method is its simplicity and the fact that it does not make any changes in the list of installed apps/libraries on your physical/virtual machine. All necessary dependencies are installed inside the Docker container. The second important advantage is that compilation can also be carried out on Windows or macOS (if Docker is installed), but keep in mind that the result of the build will be a Linux executable.

> **Note: Skip steps 3 and 4 if you are not performing this procedure for the first time (building a newer version of DMT, for example)**

#### 1. Create a new directory
We will refer to this as the *working directory* in the remainder of this documentation.

#### 2. Open the terminal app and `cd` to the *working directory*

```
cd <working_directory>
```

#### 3. Install the *bertrand256/build-dmt:ubuntu* Docker image

Skip this step if you have done this before. At any time, you can check whether the required image exists in your local machine by issuing following command:

```
docker images bertrand256/build-dmt:ubuntu
```

The required image can be obtained in one of two ways:

**Download from Docker Hub**

Execute the following command:

```
docker pull bertrand256/build-dmt:ubuntu
```

**Build the image yourself, using the Dockerfile file from the DMT project repository.** 

* Download the https://github.com/Bertrand256/dash-masternode-tool/blob/master/build/ubuntu/Dockerfile file and place it in the *working directory*
* Execute the following command:
```
docker build -t bertrand256/build-dmt:ubuntu .
```

#### 4. Create a Docker container

A Docker container is an instance of an image (similar to how an object is an instance of a class in the software development world), and it exists until you delete it. You can therefore skip this step if you have created the container before. To easily identify the container, we give it a specific name (dmtbuild) when it is created so you can easily check if it exists in your system.

```
docker ps -a --filter name=dmtbuild --filter ancestor=bertrand256/build-dmt:ubuntu
```
Create the container:

``` 
mkdir -p build
docker create --name dmtbuild -v $(pwd)/build:/root/dmt/dist -it bertrand256/build-dmt:ubuntu
```

#### 5. Build the Crown Masternode Tool executable

```
docker start -ai dmtbuild
```

When the command completes, compiled binary can be found in the 'build' subdirectory of your current directory.

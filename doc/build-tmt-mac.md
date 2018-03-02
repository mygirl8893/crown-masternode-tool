## Building the Terracoin Masternode Tool executable on macOS

You can build Terracoin Masternode Tool for macOS by opening the Terminal app and running the following commands:

* Install *Homebrew*:

  ```
  /usr/bin/ruby -e "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install)"
  ```

  Installation takes about 5 minutes to complete.

* Install *Python 3*:

  ```
  brew install python3
  ```

* After the installation process completes, make sure that the Python version installed is 3.6 or newer. TMT won't compile on older versions of Python, or even older versions of Python 3:

  ```
  python3 --version
  ```

  You should see a response similar to the following:

  `Python 3.6.4`

* Install *virtualenv*:

  ```
  pip3 install virtualenv
  ```

* Create a Python virtual environment for TMT:

  ```
  cd ~
  mkdir projects
  mkdir projects/virtualenvs
  cd projects/virtualenvs
  virtualenv -p python3 tmt
  ```

* Activate the new virtual environment:

  ```
  source tmt/bin/activate
  ```

* Download the TMT source from GitHub:

  ```
  cd ~/projects
  git clone https://github.com/TheSin-/terracoin-masternode-tool
  ```

* Install the TMT Python requirements:

  ```
  cd terracoin-masternode-tool
  pip install -r requirements.txt
  ```

* Build the TMT executable:

  ```
  pyinstaller --distpath=../dist/mac --workpath=../build/mac terracoin_masternode_tool.spec
  ```


Once the build has completed successfully, a compressed macOS executable file will be created in the ***~/projects/dist/all*** directory. An uncompressed app package (*TerracoinMasternodeTool.app*) can be found in the ***~/projects/dist/mac*** directory.

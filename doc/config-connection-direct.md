## Connection to a local Terracoin daemon
In this scenario, you will use your own Terracoin daemon configured to serve JSON-RPC requests on your local network or any network you can access directly. The most convenient way to achieve this is to run a daemon on the same computer as the TMT application itself.

### Install the Terracoin Core wallet
We will use the official Terracoin Core client as the Terracoin daemon for this configuration. Install it now if not already installed. Binary installers for macOS, Linux and Windows can be downloaded from the [official site](https://www.terracoin.io/#downloads), while documentation on the installation process is available on the [Terracoin Wiki](https://wiki.terracoin.io/index.php/How_to_install_Terracoin_Core).

### Enable JSON-RPC and "indexing" in Terracoin Core
####  Set the required parameters in the `terracoin.conf` file
The default Terracoin Core configuration does not include all of the required settings, so some changes to the `terracoin.conf` file are necessary. The location of this file varies depending on the operating system you are using and may be changed during installation, so paths will not be specified here due to possible confusion. Instead, select `Tools -> Open Wallet Configuration File` from the Terracoin Core menu. The `terracoin.conf` file will open in your default text editor.

Copy and paste the following parameters/values into the file, changing the `rpcuser` and `rpcpassword` values to your own unique values:
```ini
rpcuser=any_alphanumeric_string_as_a_username
rpcpassword=any_alphanumeric_string_as_a_password
rpcport=13332
rpcallowip=127.0.0.1
server=1
addressindex=1
spentindex=1
timestampindex=1
txindex=1
```

#### Restart Terracoin Core

Close Terracoin Core by selecting `File -> Exit` from the menu, then open it again.

#### Rebuild index
Setting parameters related to indexing and even restarting the application is not enough for Terracoin Core to entirely update its internal database to support indexing, so it is necessary to force the operation. Follow the following steps to do so:

 * Select the `Tools -> Wallet Repair` menu item.
 * Click the `Rebuild index` button in the Wallet Repair dialog box.  
    ![Wallet repair rebuild index](img/terracoinqt-rebuild-index.png)
 * Wait until the operation is complete. This step may take several hours.

### Configure connection in the TMT
 * Open TMT and click the `Configure` button.
 * Select the `Terracoin network` tab.
 * Click the `+` (plus) button on the left side of the dialog.
 * Check the `Enabled` box.
 * Enter the following values:
   * `RPC host`: 127.0.0.1
   * `port`: 13332
   * `RPC username`: enter the value you specified for the `rpcuser` parameter in the `terracoin.conf` file.
   * `RPC password`: enter the value you specified for the `rpcpassword` parameter in the `terracoin.conf` file.
 * Make sure the `Use SSH tunnel` and `SSL` checkboxes remain unchecked. Also, if you decide to use only this connection, deactivate all other connections by unchecking the corresponding `Enabled` checkboxes.  
    ![Direct connection configuration window](img/tmt-config-dlg-conn-direct.png)
 * Click the `Test connection` button. If successful, TMT will return the following message:  
    ![Connection successful](img/tmt-conn-success.png)

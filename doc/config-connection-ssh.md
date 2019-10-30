# Connection through an SSH tunnel

## SSH tunnels

If you - like many masternode owners - have your masternode running on a VPS with access via SSH, then using it as a JSON-RPC gateway will probably be the best option for you.

For security reasons, the TCP port used for JSON-RPC communication (`9341` by default) should be blocked by the firewall on Crown masternodes, and the Crown daemon itself will only accept connections from localhost. For this reason, you will not be able to connect to your Crown daemon and use the JSON-RPC service directly over the Internet. However, if you have SSH access to this server, you can create a secure tunnel that connects the local machine to the remote JSON-RPC service so that the CMT application sees the remote service as if it was working locally.

The communication is set up as follows:
 * an SSH session with the remote server is established over its public IP and SSH port
 * a random port is selected from the pool of unused ports on your computer to play the role of the local channel's endpoint
 * within the established SSH session, a secure channel is created that connects the local endpoint with the listening JSON-RPC service port on the remote server (`127.0.0.1:9341`)
 * CMT connects to the local endpoint and performs JSON-RPC requests as if the Crown daemon was working locally

```
 Local computer ━━━━━━━━━━━━━━━━> SSH session ━━━━━━━━━━━━━━━━> remote_server:22
           ┃- connecting to 127.0.0.1:random local port           ┃ - listenning on 127.0.0.1:9341
 CMT app ━━┛                                                      ┗━━━ Crown daemon JSON-RPC
```

## Configuration

### Enable JSON-RPC and "indexing" in the Crown daemon configuration

The procedure is similar to the RPC/indexing [procedure](config-connection-direct.md#2-enable-json-rpc-and-indexing-in-the-crown-core) for a local RPC node scenario.
 * Log in to the server running the Crown daemon (*crownd*) with a SSH terminal.
 * Change to the *crownd* configuration directory: `cd ~/.crowncore`
 * Open the `crown.conf` file with your preferred text editor: `nano crown.conf`
 * Enter the configuration parameters listed [here](config-connection-direct.md#set-the-required-parameters-in-the-crownconf-file).
 * Stop the *crownd* process: `./crown-cli stop`
 * Start *crownd* with the `-reindex` parameter: `./crownd -reindex`

Keep in mind that the last step can take several hours to complete. If running on a live masternode, it may be best to wait until immediately after a payment was received to carry out the reindexing.

### Configure connection in CMT

 * In CMT and click the `Configure` button.
 * Select the `Crown network` tab.
 * Click the `+` (plus) button on the left side of the dialog.
 * Check the `Use SSH tunnel` box.
 * Check the `Enabled` box.
 * Enter the following values:
   * `SSH host`: IP address (hostname) of your remote server
   * `port`: SSH listening port number of the server (usually `22`)
   * `SSH username`: username you are using to establish a connection
   * `RPC host`: IP address of the network interface where *crownd* listens for JSON-RPC calls (`127.0.0.1` by default)
   * `port`: TCP port number on which *crownd* listens for JSON-RPC calls (`9341` by default)
   * `RPC username`: enter the value you specified for the `rpcuser` parameter in the `crown.conf` file.
   * `RPC password`: enter the value you specified for the `rpcpassword` parameter in the `crown.conf` file

Instead of entering parameters related to the RPC configuration, you can click `Read RPC configuration from SSH host` to try to read the values directly from the remote `crown.conf` file.
  * Make sure the `SSL` checkbox remains unchecked. Also, if you decide to use only this connection, deactivate all other connections by unchecking the corresponding `Enabled` checkboxes.  
    ![SSH configuration window](img/tmt-config-dlg-conn-ssh.png)
  * Click the `Test connection` button. If successful, CMT will return the following message:  
    ![Connection successful](img/tmt-conn-success.png)

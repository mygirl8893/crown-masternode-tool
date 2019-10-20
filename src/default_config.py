
# default "public" connections for RPC proxy
dashd_default_connections = [
    {
        "use_ssh_tunnel": False,
        "host": "alice.dash-masternode-tool.org",
        "port": "443",
        "username": "dmtuser",
        "password": "67414141414142617879305a6e76344e664b444d5746314242582d3367453749526865656b7076616d6959594c574a7158796a7756572d4d39774852774c51414e4348356f72626e596e6c5957783833486b76394b7479384c78757a3579794f4e673d3d",
        "use_ssl": True,
        "rpc_encryption_pubkey": "30820122300d06092a864886f70d01010105000382010f003082010a0282010100d8338321c24a6ea567ba3e670c1e93f75b61f05c3dce37641e078ad58e8f44dc3c29fb2b78b9e9d5162fe604eb73622f922e2ed05f9087be773db88d90115c47e27b5d8fee1dc6f9cb18a9f53b9c5cb9ba5a3578ee4a26265ef4e3b13eb661dd1a08f138405a41fcd7e377f1cfc47a481dac6b55390cfd29b81f0accc06430c1ab5258458a1d6a961d0b12770ef4202e87493af2e476da32fac59a53be326a0ad7c45bbc624b997fccf898cb7e1ea9e0dbcac9db2956318ce25bd1f80785df299abea8061ab9eacd5d3de718d221c7683d16b1ee5f5637d1b121b04c13cdf2ac5f7682d902549c2786e527228517c0e360529140acaa6a8e405d4f1be55112890203010001"
    },
    {
        "use_ssh_tunnel": False,
        "host": "suzy.dash-masternode-tool.org",
        "port": "443",
        "username": "dmtuser",
        "password": "67414141414142617879305a4c744250614d625a4c59366b386b427879706d53634239484d78734f565f634c5a634531664c646f3359696e62637255705973704e69794271795a7745516531525a5f7a6a454f556d644969376567537279365662673d3d",
        "use_ssl": True,
        "rpc_encryption_pubkey": "30820122300d06092a864886f70d01010105000382010f003082010a0282010100ae6a142ee209fe3458b495bbba0e99f42e774850d2926c42a132890f58653da32dcb8c11ed28fa67a3bca02c3345ff921457dc5d81ebfacaec7c0aa1ec3367513111e79730787f666870e8c976c0c3a6d1294cfc4eb74915ff37b5180fce3738976f2f92e658c81890984ca81a72571f1dab7f68ba159c5e5652e08383b0e764da680e7b06fc4f64e4f2565844b2a1a14d92db4047f2f0e1d83c87a364afca459c8cc5d1b97b5a57ce028c2e2b372e04ab757bf1b6079c7619d1e5b4bb56658c99ce17dd941d6d205b8a3c6d3c976b14829e31377f7594933f4eafbb00f421fd22c8a8940a80c705bb7631fbbb91183ea37c2a72ce8867d4158f3645d6670fc70203010001"
    },
    {
        "use_ssh_tunnel": False,
        "host": "testnet1.dash-masternode-tool.org",
        "port": "8443",
        "username": "dmtuser",
        "password": "6741414141414261787979534533344d53554870596d494a4b334a434b4559535a714669312d486e6f42517a6479517737495676786c764a3333336c42397766484d673249346b6d376863634e56344c45736131366e6554756a4e705961725f51673d3d",
        "use_ssl": True,
        "testnet": True,
        "rpc_encryption_pubkey": "30820122300d06092a864886f70d01010105000382010f003082010a0282010100bc6443aa2c9ef54d4094c103ae26a7bfb3e2e40f23c75f81ccda82b8ecc02108167cc7b710ae65e4dfb120fef67862b4ed9037228f3b36860faf8399aa09a9648465a348f17ddd2e847bfb6e68423e51bb9f8a4a7f0146c265c3d354fd460487f4982fd1e4e02598aa3710da0118305a11f49b0e83e07485a56680afdeeeab9ebd55ac6e399276f3f120e2b46579c1a5ce37e4ad2899453379839a140fcb7f3bd74ea772ef0b3f530eef60f992795fcc17b5f8469516462a0221d9aa2bd425c996e1bdf5805f1d30e980391d323e6a237caafa433e2a03375974d4685a480651cac460d6694e2405710b97e44e7a728b129e12351c6c62db4a50c61005d9bafb0203010001"
    },
    {
        "use_ssh_tunnel": False,
        "host": "testnet2.dash-masternode-tool.org",
        "port": "8443",
        "username": "dmtuser",
        "password": "6741414141414261315a655555796a79485f4d342d696c725968316e4d4a7a6d38505a624d684a6e475f786772367a747175647763664468357270513977326a41307a374f7a534f5145623577495550767768507546676d70706f415f642d4a57413d3d",
        "use_ssl": True,
        "testnet": True,
        "rpc_encryption_pubkey": "30820122300d06092a864886f70d01010105000382010f003082010a0282010100cb66bbc41d1788d7e229bffb1393a4f2a5478950fa9f2c398463798eb87c790cbcf6d1e6778382fe9b2295fcb2edd8a512b8fdebe727f807e7564a5d479da07961ca586e21c6ec2f641628b195acddccd2ad06dc9b03e404acf2230d7b3ff518c04c2b345ff7889419c8297e4fae6e0471447b128cb88fe7deb7c75900c965d5f04c9811f02ca9db7982ce709108f3a34beb91b494372f1a7ec45e725c243bc0eee6e4660da8ceebf0ae1fd617d87f4a46239e04c9120097afa677d8dd55052b201b5bda3c5d215553204bc2f178d7f22f97867d7b0952ea7e447eae03fa63081285730bc04928f64077c1a07e47271566e2337aff177a39b02b1d299482d49f0203010001"
    }
]

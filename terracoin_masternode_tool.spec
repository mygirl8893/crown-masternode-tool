# -*- mode: python -*-
import sys
import os
import os.path
import platform

block_cipher = None

os_type = sys.platform
no_bits = platform.architecture()[0].replace('bit','')
version_str = ''
base_dir = os.path.dirname(os.path.realpath('__file__'))

# look for version string
with open(os.path.join(base_dir, 'version.txt')) as fptr:
    for line in fptr:
        parts = [elem.strip() for elem in line.split('=')]
        if len(parts) == 2 and parts[0].lower() == 'version_str':
            version_str = parts[1].strip("'")
            break

add_files = [
 ('img/cmt.png','/img'),
 ('img/terracoin.ico','/img'),
 ('img/cmt.ico','/img'),
 ('img/arrow-right.ico','/img'),
 ('img/hw-lock.ico','/img'),
 ('img/hw-test.ico','/img'),
 ('img/terracoin-transfer.png','/img'),
 ('img/check.png','/img'),
 ('img/dollar.png','/img'),
 ('img/gear.png','/img'),
 ('img/hw.png','/img'),
 ('img/info.png','/img'),
 ('img/money-bag.png','/img'),
 ('img/sign.png','/img'),
 ('img/tools.png','/img'),
 ('img/uncheck.png','/img'),
 ('img/wallet.png','/img'),
 ('img/thumb-up.png','/img'),
 ('img/recover.png','/img'),
 ('version.txt', '/')
]

lib_path = next(p for p in sys.path if 'site-packages' in p)
#if os_type == 'win32':
#
#    qt5_path = os.path.join(lib_path, 'PyQt5\\Qt\\bin')
#    sys.path.append(qt5_path)
#
#    # add file vcruntime140.dll manually, due to not including by pyinstaller
#    found = False
#    for p in os.environ["PATH"].split(os.pathsep):
#        file_name = os.path.join(p, "vcruntime140.dll")
#        if os.path.exists(file_name):
#            found = True
#            add_files.append((file_name, ''))
#            print('Adding file ' + file_name)
#            break
#    if not found:
#        raise Exception('File vcruntime140.dll not found in the system path.')

# add bitcoin library data file
add_files.append( (os.path.join(lib_path, 'bitcoin/english.txt'),'/bitcoin') )
add_files.append( (os.path.join(lib_path, 'mnemonic/wordlist/english.txt'),'/mnemonic/wordlist') )

a = Analysis(['src/terracoin_masternode_tool.py'],
             pathex=[base_dir],
             binaries=[],
             datas=add_files,
             hiddenimports=[],
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher)

pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)

exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          name='TerracoinMasternodeTool',
          debug=False,
          strip=False,
          upx=False,
          console=False,
		  icon=os.path.join('img',('tmt.%s' % ('icns' if os_type=='darwin' else 'ico'))))

if os_type == 'darwin':
    app = BUNDLE(exe,
                 name='TerracoinMasternodeTool.app',
                 icon='img/cmt.icns',
                 bundle_identifier=None,
                     info_plist={
                        'NSHighResolutionCapable': 'True'
                     }
                 )

dist_path = os.path.join(base_dir, DISTPATH)
all_bin_dir = os.path.join(dist_path, '..', 'all')
if not os.path.exists(all_bin_dir):
    os.makedirs(all_bin_dir)

# zip archives
print(dist_path)
print(all_bin_dir)
os.chdir(dist_path)

if os_type == 'win32':
    print('Compressing Windows executable')
    os.system('"7z.exe" a %s %s -mx0' % (os.path.join(all_bin_dir, 'TerracoinMasternodeTool_' + version_str + '.win' + no_bits + '.zip'),  'TerracoinMasternodeTool.exe'))
elif os_type == 'darwin':
    print('Compressing Mac executable')
    os.system('zip -r "%s" "%s"' % (os.path.join(all_bin_dir, 'TerracoinMasternodeTool_' + version_str + '.mac.zip'),  'TerracoinMasternodeTool.app'))
elif os_type == 'linux':
    print('Compressing Linux executable')
    os.system('tar -zcvf %s %s' % (os.path.join(all_bin_dir, 'TerracoinMasternodeTool_' + version_str + '.linux.tar.gz'),  'TerracoinMasternodeTool'))

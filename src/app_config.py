#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Author: Bertrand256
# Created on: 2017-03
import argparse
import datetime
import json
import os
import re
import copy
from configparser import ConfigParser
from os.path import expanduser
from random import randint
from shutil import copyfile
import logging
import bitcoin
from logging.handlers import RotatingFileHandler
from PyQt5.QtCore import QLocale
from app_utils import encrypt, decrypt
import app_cache as cache
import default_config
import app_utils
from db_intf import DBCache
from wnd_utils import WndUtils

APP_NAME_SHORT = 'CrownMasternodeTool'
APP_NAME_LONG = 'Crown Masternode Tool'
PROJECT_URL = 'https://github.com/walkjivefly/crown-masternode-tool'
FEE_SAT_PER_BYTE = 11
MIN_TX_FEE = 2000
APP_CFG_CUR_VERSION = 2  # current version of configuration file format
SCREENSHOT_MODE = False


class HWType:
    trezor = 'TREZOR'
    keepkey = 'KEEPKEY'
    ledger_nano_s = 'LEDGERNANOS'

    @staticmethod
    def get_desc(hw_type):
        if hw_type == HWType.trezor:
            return 'Trezor'
        elif hw_type == HWType.keepkey:
            return 'KeepKey'
        elif hw_type == HWType.ledger_nano_s:
            return 'Ledger Nano S'
        else:
            return '???'


class AppConfig(object):
    def __init__(self):
        self.initialized = False
        self.app_path = ''  # will be passed in the init method
        self.log_level_str = 'WARNING'
        self.app_version = ''
        QLocale.setDefault(self.get_default_locale())
        self.date_format = self.get_default_locale().dateFormat(QLocale.ShortFormat)
        self.date_time_format = self.get_default_locale().dateTimeFormat(QLocale.ShortFormat)

        # List of Crown network configurations. Multiple conn configs advantage is to give the possibility to use
        # another config if particular one is not functioning (when using "public" RPC service, it could be node's
        # maintanance)
        self.crown_net_configs = []

        # to distribute the load evenly over "public" RPC services, we choose radom connection (from enabled ones)
        # if it is set to False, connections will be used accoording to its order in crown_net_configs list
        self.random_crown_net_config = True

        # list of all enabled crownd configurations (CrownNetworkConnectionCfg) - they will be used accourding to
        # the order in list
        self.active_crown_net_configs = []

        # list of misbehaving crown network configurations - they will have the lowest priority during next
        # connections
        self.defective_net_configs = []

        self.hw_type = HWType.trezor  # TREZOR, KEEPKEY, LEDGERNANOS
        self.hw_keepkey_psw_encoding = 'NFC'  # Keepkey passphrase UTF8 chars encoding:
                                              #  NFC: compatible with official Keepkey client app
                                              #  NFKD: compatible with Trezor

        self.block_explorer_tx = 'https://insight-01.crownplatform.com/tx/%TXID%'
        self.block_explorer_addr = 'https://insight-01.crownplatform.com/%ADDRESS%'
        self.crown_services_proposal_api = 'https://services.crownplatform.com/api/v1/proposal?hash=%HASH%'

        self.check_for_updates = True
        self.backup_config_file = True
        self.read_proposals_external_attributes = True  # if True, some additional attributes will be downloaded from
                                                        # external sources
        self.dont_use_file_dialogs = False
        self.confirm_when_voting = True
        self.add_random_offset_to_vote_time = True  # To avoid identifying one user's masternodes by vote time
        self.csv_delimiter =';'
        self.masternodes = []
        self.systemnodes = []
        self.last_bip32_base_path = ''
        self.bip32_recursive_search = True
        self.modified = False
        self.cache_dir = ''
        self.app_config_file_name = ''
        self.log_dir = ''
        self.log_file = ''
        self.log_level_str = ''
        self.db_cache_file_name = ''
        self.cfg_backup_dir = ''
        self.app_last_version = ''

    def init(self, app_path):
        """ Initialize configuration after opening the application. """
        self.app_path = app_path

        try:
            with open(os.path.join(app_path, 'version.txt')) as fptr:
                lines = fptr.read().splitlines()
                self.app_version = app_utils.extract_app_version(lines)
        except:
            pass

        parser = argparse.ArgumentParser()
        parser.add_argument('--config', help="Path to a configuration file", dest='config')
        parser.add_argument('--data-dir', help="Root directory for configuration file, cache and log dubdirs",
                            dest='data_dir')
        args = parser.parse_args()

        app_user_dir = ''
        if args.data_dir:
            if os.path.exists(args.data_dir):
                if os.path.isdir(args.data_dir):
                    app_user_dir = args.data_dir
                else:
                    WndUtils.errorMsg('--data-dir parameter doesn\'t point to a directory. Using the default '
                                      'data directory.')
            else:
                WndUtils.errorMsg('--data-dir parameter doesn\'t point to an existing directory. Using the default '
                                  'data directory.')

        if not app_user_dir:
            home_dir = expanduser('~')
            app_user_dir = os.path.join(home_dir, APP_NAME_SHORT)
            if not os.path.exists(app_user_dir):
                os.makedirs(app_user_dir)

        self.cache_dir = os.path.join(app_user_dir, 'cache')
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)
        cache.init(self.cache_dir, self.app_version)
        self.app_last_version = cache.get_value('app_version', '', str)
        self.app_config_file_name = ''

        if args.config is not None:
            self.app_config_file_name = args.config
            if not os.path.exists(self.app_config_file_name):
                msg = 'Config file "%s" does not exist.' % self.app_config_file_name
                print(msg)
                raise Exception(msg)

        if not self.app_config_file_name:
            self.app_config_file_name = os.path.join(app_user_dir, 'config.ini')

        # setup logging
        self.log_dir = os.path.join(app_user_dir, 'logs')
        self.log_file = os.path.join(self.log_dir, 'cmt.log')
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)

        self.log_level_str = 'INFO'
        log_exists = os.path.exists(self.log_file)
        handler = RotatingFileHandler(filename=self.log_file, mode='a', backupCount=30)
        logger = logging.getLogger()
        formatter = logging.Formatter(fmt='%(asctime)s %(levelname)s |%(threadName)s |%(filename)s |%(funcName)s '
                                          '|%(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(self.log_level_str)
        if log_exists:
            handler.doRollover()
        logging.info('App started')

        # database (SQLITE) cache for caching bigger datasets:
        self.db_cache_file_name = os.path.join(self.cache_dir, 'cmt_cache.db')

        try:
            self.db_intf = DBCache(self.db_cache_file_name)
        except Exception as e:
            logging.exception('SQLite initialization error')

        # directory for configuration backups:
        self.cfg_backup_dir = os.path.join(app_user_dir, 'backup')
        if not os.path.exists(self.cfg_backup_dir):
            os.makedirs(self.cfg_backup_dir)

        try:
            # read configuration from a file
            self.read_from_file()
        except:
            pass

        if not self.app_last_version or \
           app_utils.version_str_to_number(self.app_last_version) < app_utils.version_str_to_number(self.app_version):
            cache.save_data()
        self.initialized = True

    def start_cache(self):
        """ Start cache save thread after GUI initializes. """
        cache.start()

    def close(self):
        cache.finish()
        self.db_intf.close()

    def copy_from(self, src_config):
        self.crown_net_configs = copy.deepcopy(src_config.crown_net_configs)
        self.random_crown_net_config = src_config.random_crown_net_config
        self.hw_type = src_config.hw_type
        self.hw_keepkey_psw_encoding = src_config.hw_keepkey_psw_encoding
        self.block_explorer_tx = src_config.block_explorer_tx
        self.block_explorer_addr = src_config.block_explorer_addr
        self.crown_services_proposal_api = src_config.crown_services_proposal_api
        self.check_for_updates = src_config.check_for_updates
        self.backup_config_file = src_config.backup_config_file
        self.read_proposals_external_attributes = src_config.read_proposals_external_attributes
        self.dont_use_file_dialogs = src_config.dont_use_file_dialogs
        self.confirm_when_voting = src_config.confirm_when_voting
        self.add_random_offset_to_vote_time = src_config.add_random_offset_to_vote_time
        self.csv_delimiter = src_config.csv_delimiter
        if self.initialized:
            # self.set_log_level reconfigures the logger configuration so call this function
            # if this object is the main AppConfig object (it's initialized)
            self.set_log_level(src_config.log_level_str)
        else:
            # ... otherwise just copy attribute without reconfiguring logger
            self.log_level_str = src_config.log_level_str

    def get_default_locale(self):
        if SCREENSHOT_MODE:
            return QLocale(QLocale.English)
        else:
            return QLocale.system()

    def to_string(self, data):
        """ Converts date/datetime or number to string using the current locale. """
        if isinstance(data, datetime.datetime):
            return self.get_default_locale().toString(data, self.date_time_format)
        elif isinstance(data, datetime.date):
            return self.get_default_locale().toString(data, self.date_format)
        elif isinstance(data, float):
            # don't use QT float to number conversion due to weird behavior
            dp = self.get_default_locale().decimalPoint()
            ret_str = str(data)
            if dp != '.':
                ret_str.replace('.', dp)
            return ret_str
        elif isinstance(data, str):
            return data
        elif isinstance(data, int):
            return str(data)
        else:
            raise Exception('Argument is not a datetime type')

    def read_from_file(self):
        ini_version = None
        was_default_ssh_in_ini_v1 = False
        was_default_direct_localhost_in_ini_v1 = False
        ini_v1_localhost_rpc_cfg = None

        # from v0.9.15 some public nodes changed its names and port numbers to the official HTTPS port number: 443
        # correct the configuration
        if not self.app_last_version or \
            (app_utils.version_str_to_number(self.app_last_version) < app_utils.version_str_to_number('0.9.16')):
            correct_public_nodes = True
        else:
            correct_public_nodes = False
        configuration_corrected = False

        if os.path.exists(self.app_config_file_name):
            config = ConfigParser()
            try:
                section = 'CONFIG'
                config.read(self.app_config_file_name)
                ini_version = config.get(section, 'CFG_VERSION', fallback=1)  # if CFG_VERSION not set it's old config

                log_level_str = config.get(section, 'log_level', fallback='WARNING')
                if log_level_str not in ('CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG', 'NOTSET'):
                    log_level_str = 'WARNING'
                if self.log_level_str != log_level_str:
                    self.set_log_level(log_level_str)

                if ini_version == 1:
                    # read network config from old file format
                    crownd_connect_method = config.get(section, 'crownd_connect_method', fallback='rpc')
                    rpc_user = config.get(section, 'rpc_user', fallback='')
                    rpc_password = config.get(section, 'rpc_password', fallback='')
                    rpc_ip = config.get(section, 'rpc_ip', fallback='')
                    rpc_port = config.get(section, 'rpc_port', fallback='8889')
                    ros_ssh_host = config.get(section, 'ros_ssh_host', fallback='')
                    ros_ssh_port = config.get(section, 'ros_ssh_port', fallback='22')
                    ros_ssh_username = config.get(section, 'ros_ssh_username', fallback='')
                    ros_rpc_bind_ip = config.get(section, 'ros_rpc_bind_ip', fallback='127.0.0.1')
                    ros_rpc_bind_port = config.get(section, 'ros_rpc_bind_port', fallback='13332')
                    ros_rpc_username = config.get(section, 'ros_rpc_username', fallback='')
                    ros_rpc_password = config.get(section, 'ros_rpc_password', fallback='')

                    # convert crown network config from config version 1
                    if ros_ssh_host and ros_ssh_port and ros_ssh_username and ros_rpc_bind_ip and \
                       ros_rpc_bind_port and ros_rpc_username and ros_rpc_password:

                        # import RPC over SSH configuration
                        cfg = CrownNetworkConnectionCfg('rpc')
                        cfg.enabled = True if crownd_connect_method == 'rpc_ssh' else False
                        cfg.host = ros_rpc_bind_ip
                        cfg.port = ros_rpc_bind_port
                        cfg.use_ssl = False
                        cfg.username = ros_rpc_username
                        cfg.password = ros_rpc_password
                        cfg.use_ssh_tunnel = True
                        cfg.ssh_conn_cfg.host = ros_ssh_host
                        cfg.ssh_conn_cfg.port = ros_ssh_port
                        cfg.ssh_conn_cfg.username = ros_ssh_username
                        self.crown_net_configs.append(cfg)
                        was_default_ssh_in_ini_v1 = cfg.enabled

                    if rpc_user and rpc_password and rpc_ip and rpc_port:
                        cfg = CrownNetworkConnectionCfg('rpc')
                        cfg.enabled = True if crownd_connect_method == 'rpc' else False
                        cfg.host = rpc_ip
                        cfg.port = rpc_port
                        cfg.use_ssl = False
                        cfg.username = rpc_user
                        cfg.password = rpc_password
                        cfg.use_ssh_tunnel = False
                        self.crown_net_configs.append(cfg)
                        was_default_direct_localhost_in_ini_v1 = cfg.enabled and cfg.host == '127.0.0.1'
                        ini_v1_localhost_rpc_cfg = cfg
                        if correct_public_nodes:
                            if cfg.host.lower() == 'alice.dash-dmt.eu':
                                cfg.host = 'alice.dash-masternode-tool.org'
                                cfg.port = '443'
                                configuration_corrected = True
                            elif cfg.host.lower() == 'luna.dash-dmt.eu':
                                cfg.host = 'luna.dash-masternode-tool.org'
                                cfg.port = '443'
                                configuration_corrected = True

                self.last_bip32_base_path = config.get(section, 'bip32_base_path', fallback="44'/83'/0'/0/0")
                if not self.last_bip32_base_path:
                    self.last_bip32_base_path = "44'/83'/0'/0/0"
                self.bip32_recursive_search = config.getboolean(section, 'bip32_recursive', fallback=True)
                self.hw_type = config.get(section, 'hw_type', fallback=HWType.trezor)
                if self.hw_type not in (HWType.trezor, HWType.keepkey, HWType.ledger_nano_s):
                    logging.warning('Invalid hardware wallet type: ' + self.hw_type)
                    self.hw_type = HWType.trezor

                self.hw_keepkey_psw_encoding = config.get(section, 'hw_keepkey_psw_encoding', fallback='NFC')
                if self.hw_keepkey_psw_encoding not in ('NFC', 'NFKD'):
                    logging.warning('Invalid value of the hw_keepkey_psw_encoding config option: ' +
                                    self.hw_keepkey_psw_encoding)
                    self.hw_keepkey_psw_encoding = 'NFC'

                self.random_crown_net_config = self.value_to_bool(config.get(section, 'random_crown_net_config',
                                                                            fallback='1'))
                self.check_for_updates = self.value_to_bool(config.get(section, 'check_for_updates', fallback='1'))
                self.backup_config_file = self.value_to_bool(config.get(section, 'backup_config_file', fallback='1'))
                self.read_proposals_external_attributes = \
                    self.value_to_bool(config.get(section, 'read_external_proposal_attributes', fallback='1'))
                self.dont_use_file_dialogs = self.value_to_bool(config.get(section, 'dont_use_file_dialogs',
                                                                          fallback='0'))
                self.confirm_when_voting = self.value_to_bool(config.get(section, 'confirm_when_voting',
                                                                          fallback='1'))
                self.add_random_offset_to_vote_time = \
                    self.value_to_bool(config.get(section, 'add_random_offset_to_vote_time', fallback='1'))

                for section in config.sections():
                    if re.match('MN\d', section):
                        mn = MasterNodeConfig()
                        mn.name = config.get(section, 'name', fallback='')
                        mn.ip = config.get(section, 'ip', fallback='')
                        mn.port = config.get(section, 'port', fallback='')
                        mn.privateKey = config.get(section, 'private_key', fallback='')
                        mn.collateralBip32Path = config.get(section, 'collateral_bip32_path', fallback='')
                        mn.collateralAddress = config.get(section, 'collateral_address', fallback='')
                        mn.collateralTx = config.get(section, 'collateral_tx', fallback='')
                        mn.collateralTxIndex = config.get(section, 'collateral_tx_index', fallback='')
                        mn.use_default_protocol_version = self.value_to_bool(
                            config.get(section, 'use_default_protocol_version', fallback='1'))
                        mn.protocol_version = config.get(section, 'protocol_version', fallback='')
                        self.masternodes.append(mn)
                    elif re.match('SN\d', section):
                        sn = SystemNodeConfig()
                        sn.name = config.get(section, 'name', fallback='')
                        sn.ip = config.get(section, 'ip', fallback='')
                        sn.port = config.get(section, 'port', fallback='')
                        sn.privateKey = config.get(section, 'private_key', fallback='')
                        sn.collateralBip32Path = config.get(section, 'collateral_bip32_path', fallback='')
                        sn.collateralAddress = config.get(section, 'collateral_address', fallback='')
                        sn.collateralTx = config.get(section, 'collateral_tx', fallback='')
                        sn.collateralTxIndex = config.get(section, 'collateral_tx_index', fallback='')
                        sn.use_default_protocol_version = self.value_to_bool(
                            config.get(section, 'use_default_protocol_version', fallback='1'))
                        sn.protocol_version = config.get(section, 'protocol_version', fallback='')
                        self.systemnodes.append(sn)
                    elif re.match('NETCFG\d', section):
                        # read network configuration from new config file format
                        cfg = CrownNetworkConnectionCfg('rpc')
                        cfg.enabled = self.value_to_bool(config.get(section, 'enabled', fallback='1'))
                        cfg.host = config.get(section, 'host', fallback='')
                        cfg.port = config.get(section, 'port', fallback='')
                        cfg.use_ssl = self.value_to_bool(config.get(section, 'use_ssl', fallback='0'))
                        cfg.username = config.get(section, 'username', fallback='')
                        cfg.set_encrypted_password(config.get(section, 'password', fallback=''))
                        cfg.use_ssh_tunnel = self.value_to_bool(config.get(section, 'use_ssh_tunnel', fallback='0'))
                        cfg.ssh_conn_cfg.host = config.get(section, 'ssh_host', fallback='')
                        cfg.ssh_conn_cfg.port = config.get(section, 'ssh_port', fallback='')
                        cfg.ssh_conn_cfg.username = config.get(section, 'ssh_username', fallback='')
                        self.crown_net_configs.append(cfg)
                        if correct_public_nodes:
                            if cfg.host.lower() == 'alice.dash-dmt.eu':
                                cfg.host = 'alice.dash-masternode-tool.org'
                                cfg.port = '443'
                                configuration_corrected = True
                            elif cfg.host.lower() == 'luna.dash-dmt.eu':
                                cfg.host = 'luna.dash-masternode-tool.org'
                                cfg.port = '443'
                                configuration_corrected = True
            except Exception:
                logging.exception('Read configuration error:')

        try:
            cfgs = self.decode_connections(default_config.crownd_default_connections)
            if cfgs:
                # force import default connections if there is no any in the configuration
                force_import = (len(self.crown_net_configs) == 0) or \
                               (self.app_last_version == '0.9.15') # v0.9.15 imported the connections but not saved the cfg

                added, updated = self.import_connections(cfgs, force_import=force_import)
                if not ini_version or (ini_version == 1 and len(added) > 0):
                    # we are migrating from config.ini version 1
                    if was_default_ssh_in_ini_v1:
                        # in v 1 user used connection to RPC over SSH;
                        # we assume, that he would prefer his previus, trusted server, so we'll deactivate
                        # added default public connections (user will be able to activate them manually)
                        for new in added:
                            new.enabled = False
                    elif was_default_direct_localhost_in_ini_v1:
                        # in the old version user used local crown daemon;
                        # we assume, that user would prefer "public" connections over local, troublesome node
                        # deactivate user's old cfg
                        ini_v1_localhost_rpc_cfg.enabled = False
                if added or updated:
                    configuration_corrected = True

            if not ini_version or ini_version == 1 or configuration_corrected:
                # we are migrating settings from old configuration file - save config file in a new format
                self.save_to_file()

        except Exception:
            pass

    def save_to_file(self):
        # backup old ini file
        if self.backup_config_file:
            if os.path.exists(self.app_config_file_name):
                tm_str = datetime.datetime.now().strftime('%Y-%m-%d %H_%M')
                back_file_name = os.path.join(self.cfg_backup_dir, 'config_' + tm_str + '.ini')
                try:
                    copyfile(self.app_config_file_name, back_file_name)
                except:
                    pass

        section = 'CONFIG'
        config = ConfigParser()
        config.add_section(section)
        config.set(section, 'CFG_VERSION', str(APP_CFG_CUR_VERSION))
        config.set(section, 'log_level', self.log_level_str)
        config.set(section, 'hw_type', self.hw_type)
        config.set(section, 'hw_keepkey_psw_encoding', self.hw_keepkey_psw_encoding)
        config.set(section, 'bip32_base_path', self.last_bip32_base_path)
        config.set(section, 'random_crown_net_config', '1' if self.random_crown_net_config else '0')
        config.set(section, 'check_for_updates', '1' if self.check_for_updates else '0')
        config.set(section, 'backup_config_file', '1' if self.backup_config_file else '0')
        config.set(section, 'dont_use_file_dialogs', '1' if self.dont_use_file_dialogs else '0')
        config.set(section, 'read_external_proposal_attributes',
                   '1' if self.read_proposals_external_attributes else '0')
        config.set(section, 'confirm_when_voting', '1' if self.confirm_when_voting else '0')
        config.set(section, 'add_random_offset_to_vote_time', '1' if self.add_random_offset_to_vote_time else '0')

        # save mn configuration
        for idx, mn in enumerate(self.masternodes):
            section = 'MN' + str(idx+1)
            config.add_section(section)
            config.set(section, 'name', mn.name)
            config.set(section, 'ip', mn.ip)
            config.set(section, 'port', str(mn.port))
            config.set(section, 'private_key', mn.privateKey)
            config.set(section, 'collateral_bip32_path', mn.collateralBip32Path)
            config.set(section, 'collateral_address', mn.collateralAddress)
            config.set(section, 'collateral_tx', mn.collateralTx)
            config.set(section, 'collateral_tx_index', str(mn.collateralTxIndex))
            config.set(section, 'use_default_protocol_version', '1' if mn.use_default_protocol_version else '0')
            config.set(section, 'protocol_version', str(mn.protocol_version))
            mn.modified = False

        # save sn configuration
        for idx, sn in enumerate(self.systemnodes):
            section = 'SN' + str(idx+1)
            config.add_section(section)
            config.set(section, 'name', sn.name)
            config.set(section, 'ip', sn.ip)
            config.set(section, 'port', str(sn.port))
            config.set(section, 'private_key', sn.privateKey)
            config.set(section, 'collateral_bip32_path', sn.collateralBip32Path)
            config.set(section, 'collateral_address', sn.collateralAddress)
            config.set(section, 'collateral_tx', sn.collateralTx)
            config.set(section, 'collateral_tx_index', str(sn.collateralTxIndex))
            config.set(section, 'use_default_protocol_version', '1' if sn.use_default_protocol_version else '0')
            config.set(section, 'protocol_version', str(sn.protocol_version))
            sn.modified = False

        # save crown network connections
        for idx, cfg in enumerate(self.crown_net_configs):
            section = 'NETCFG' + str(idx+1)
            config.add_section(section)
            config.set(section, 'method', cfg.method)
            config.set(section, 'enabled', '1' if cfg.enabled else '0')
            config.set(section, 'host', cfg.host)
            config.set(section, 'port', cfg.port)
            config.set(section, 'username', cfg.username)
            config.set(section, 'password', cfg.get_password_encrypted())
            config.set(section, 'use_ssl', '1' if cfg.use_ssl else '0')
            config.set(section, 'use_ssh_tunnel', '1' if cfg.use_ssh_tunnel else '0')
            if cfg.use_ssh_tunnel:
                config.set(section, 'ssh_host', cfg.ssh_conn_cfg.host)
                config.set(section, 'ssh_port', cfg.ssh_conn_cfg.port)
                config.set(section, 'ssh_username', cfg.ssh_conn_cfg.username)
                # SSH password is not saved until HW encrypting feature will be finished

        with open(self.app_config_file_name, 'w') as f_ptr:
            config.write(f_ptr)
        self.modified = False

    def value_to_bool(self, value, default=None):
        """
        Cast value to bool:
          - if value is int, 1 will return True, 0 will return False, others will be invalid
          - if value is str, '1' will return True, '0' will return False, others will be invalid 
        :param value: 
        :return: 
        """
        if isinstance(value, bool):
            v = value
        elif isinstance(value, int):
            if value == 1:
                v = True
            elif value == 0:
                v = False
            else:
                v = default
        elif isinstance(value, str):
            if value == '1':
                v = True
            elif value == '0':
                v = False
            else:
                v = default
        else:
            v = default
        return v

    def set_log_level(self, new_log_level_str):
        """
        Method called when log level has been changed by the user. New log
        :param new_log_level: new log level (symbol as INFO,WARNING,etc) to be set. 
        """
        if self.log_level_str != new_log_level_str:
            lg = logging.getLogger()
            if lg:
                lg.setLevel(new_log_level_str)
                logging.info('Changed log level to: %s' % new_log_level_str)
            self.log_level_str = new_log_level_str

    def is_config_complete(self):
        for cfg in self.crown_net_configs:
            if cfg.enabled:
                return True
        return False

    def prepare_conn_list(self):
        """
        Prepare list of enabled connections for connecting to crown network. 
        :return: list of CrownNetworkConnectionCfg objects order randomly (random_crown_net_config == True) or according 
            to order in configuration
        """
        tmp_list = []
        for cfg in self.crown_net_configs:
            if cfg.enabled:
                tmp_list.append(cfg)
        if self.random_crown_net_config:
            ordered_list = []
            while len(tmp_list):
                idx = randint(0, len(tmp_list)-1)
                ordered_list.append(tmp_list[idx])
                del tmp_list[idx]
            self.active_crown_net_configs = ordered_list
        else:
            self.active_crown_net_configs = tmp_list

    def get_ordered_conn_list(self):
        if not self.active_crown_net_configs:
            self.prepare_conn_list()
        return self.active_crown_net_configs

    def conn_config_changed(self):
        self.active_crown_net_configs = []
        self.defective_net_configs = []

    def conn_cfg_failure(self, cfg):
        """
        Mark conn configuration as not functioning (node could be shut down in the meantime) - this connection will
        be sent to the end of queue of active connections.
        :param cfg: 
        :return: 
        """
        self.defective_net_configs.append(cfg)

    def decode_connections(self, raw_conn_list):
        """
        Decodes list of dicts describing connection to a list of CrownNetworkConnectionCfg objects.
        :param raw_conn_list: 
        :return: list of connection objects
        """
        connn_list = []
        for conn_raw in raw_conn_list:
            try:
                if 'use_ssh_tunnel' in conn_raw and 'host' in conn_raw and 'port' in conn_raw and \
                   'username' in conn_raw and 'password' in conn_raw and 'use_ssl' in conn_raw:
                    cfg = CrownNetworkConnectionCfg('rpc')
                    cfg.use_ssh_tunnel = conn_raw['use_ssh_tunnel']
                    cfg.host = conn_raw['host']
                    cfg.port = conn_raw['port']
                    cfg.username = conn_raw['username']
                    cfg.set_encrypted_password(conn_raw['password'])
                    cfg.use_ssl = conn_raw['use_ssl']
                    if cfg.use_ssh_tunnel:
                        if 'ssh_host' in conn_raw:
                            cfg.ssh_conn_cfg.host = conn_raw['ssh_host']
                        if 'ssh_port' in conn_raw:
                            cfg.ssh_conn_cfg.port = conn_raw['ssh_port']
                        if 'ssh_user' in conn_raw:
                            cfg.ssh_conn_cfg.port = conn_raw['ssh_user']
                    connn_list.append(cfg)
            except Exception as e:
                logging.exception('Exception while decoding connections.')
        return connn_list

    def decode_connections_json(self, conns_json):
        """
        Decodes connections list from JSON string.
        :param conns_json: list of connections as JSON string in the following form:
         [
            {
                'use_ssh_tunnel': bool,
                'host': str,
                'port': str,
                'username': str,
                'password': str,
                'use_ssl': bool,
                'ssh_host': str, non-mandatory
                'ssh_port': str, non-mandatory
                'ssh_user': str non-mandatory
            },
        ]
        :return: list of CrownNetworkConnectionCfg objects or None if there was an error while importing
        """
        try:
            conns_json = conns_json.strip()
            if conns_json.endswith(','):
                conns_json = conns_json[:-1]
            conns = json.loads(conns_json)

            if isinstance(conns, dict):
                conns = [conns]
            return self.decode_connections(conns)
        except Exception as e:
            return None

    def encode_connections_to_json(self, conns):
        encoded_conns = []

        for conn in conns:
            ec = {
                'use_ssh_tunnel': conn.use_ssh_tunnel,
                'host': conn.host,
                'port': conn.port,
                'username': conn.username,
                'password': conn.get_password_encrypted(),
                'use_ssl': conn.use_ssl
            }
            if conn.use_ssh_tunnel:
                ec['ssh_host'] = conn.ssh_conn_cfg.host
                ec['ssh_port'] = conn.ssh_conn_cfg.port
                ec['ssh_username'] = conn.ssh_conn_cfg.username
            encoded_conns.append(ec)
        return json.dumps(encoded_conns, indent=4)

    def import_connections(self, in_conns, force_import):
        """
        Imports connections from a list. Used at the app's start to process default connections and/or from
          a configuration dialog, when user pastes from a clipboard a string, describing connections he 
          wants to add to the configuration. The latter feature is used for a convenience.
        :param in_conns: list of CrownNetworkConnectionCfg objects.
        :returns: tuple (list_of_added_connections, list_of_updated_connections)
        """

        added_conns = []
        updated_conns = []
        if in_conns:
            for nc in in_conns:
                id = nc.get_conn_id()
                # check if new connection is in existing list
                conn = self.get_conn_cfg_by_id(id)
                if not conn:
                    if force_import or not cache.get_value('imported_default_conn_' + nc.get_conn_id(), False, bool):
                        # this new connection was not automatically imported before
                        self.crown_net_configs.append(nc)
                        added_conns.append(nc)
                        cache.set_value('imported_default_conn_' + nc.get_conn_id(), True)
                elif not conn.identical(nc) and force_import:
                    conn.copy_from(nc)
                    updated_conns.append(conn)
        return added_conns, updated_conns

    def get_conn_cfg_by_id(self, id):
        """
        Returns CrownNetworkConnectionCfg object by its identifier or None if does not exists.
        :param id: Identifier of the sought connection.
        :return: CrownNetworkConnectionCfg object or None if does not exists.
        """
        for conn in self.crown_net_configs:
            if conn.get_conn_id() == id:
                return conn
        return None

    def conn_cfg_success(self, cfg):
        """
        Mark conn configuration as functioning. If it was placed on self.defective_net_configs list before, now
        will be removed from it.
        """
        if cfg in self.defective_net_configs:
            # remove config from list of defective config
            idx = self.defective_net_configs.index(cfg)
            self.defective_net_configs.pop(idx)

    def get_mn_by_name(self, name):
        for mn in self.masternodes:
            if mn.name == name:
                return mn
        return None

    def add_mn(self, mn):
        if mn not in self.masternodes:
            existing_mn = self.get_mn_by_name(mn.name)
            if not existing_mn:
                self.masternodes.append(mn)
            else:
                raise Exception('Masternode with this name: ' + mn.name + ' already exists in configuration')

    def get_sn_by_name(self, name):
        for sn in self.systemnodes:
            if sn.name == name:
                return sn
        return None

    def add_sn(self, sn):
        if sn not in self.systemnodes:
            existing_sn = self.get_sn_by_name(sn.name)
            if not existing_sn:
                self.systemnodes.append(sn)
            else:
                raise Exception('Systemnode with this name: ' + mn.name + ' already exists in configuration')


class MasterNodeConfig:
    def __init__(self):
        self.name = ''
        self.ip = ''
        self.port = '9340'
        self.privateKey = ''
        self.collateralBip32Path = ''
        self.collateralAddress = ''
        self.collateralTx = ''
        self.collateralTxIndex = ''
        self.use_default_protocol_version = True
        self.protocol_version = ''
        self.new = False
        self.modified = False
        self.lock_modified_change = False

    def set_modified(self):
        if not self.lock_modified_change:
            self.modified = True

class SystemNodeConfig:
    def __init__(self):
        self.name = ''
        self.ip = ''
        self.port = '9340'
        self.privateKey = ''
        self.collateralBip32Path = ''
        self.collateralAddress = ''
        self.collateralTx = ''
        self.collateralTxIndex = ''
        self.use_default_protocol_version = True
        self.protocol_version = ''
        self.new = False
        self.modified = False
        self.lock_modified_change = False

    def set_modified(self):
        if not self.lock_modified_change:
            self.modified = True

class SSHConnectionCfg(object):
    def __init__(self):
        self.__host = ''
        self.__port = ''
        self.__username = ''
        self.__password = ''

    @property
    def host(self):
        return self.__host

    @host.setter
    def host(self, host):
        self.__host = host

    @property
    def port(self):
        return self.__port

    @port.setter
    def port(self, port):
        self.__port = port

    @property
    def username(self):
        return self.__username

    @username.setter
    def username(self, username):
        self.__username = username

    @property
    def password(self):
        return self.__password

    @password.setter
    def password(self, password):
        self.__password = password


class CrownNetworkConnectionCfg(object):
    def __init__(self, method):
        self.__enabled = True
        self.method = method    # now only 'rpc'
        self.__host = ''
        self.__port = ''
        self.__username = ''
        self.__password = ''
        self.__use_ssl = False
        self.__use_ssh_tunnel = False
        self.__ssh_conn_cfg = SSHConnectionCfg()

    def get_description(self):
        if self.__use_ssh_tunnel:
            desc, host, port = ('SSH ', self.ssh_conn_cfg.host, self.ssh_conn_cfg.port)
        else:
            if self.__use_ssl:
                desc, host, port = ('https://', self.__host, self.__port)
            else:
                desc, host, port = ('', self.__host, self.__port)
        desc = '%s%s:%s' % (desc, (host if host else '???'), (port if port else '???'))
        return desc

    def get_conn_id(self):
        """
        Returns identifier of this connection, built on attributes that uniquely characteraize the connection. 
        :return: 
        """
        if self.__use_ssh_tunnel:
            id = 'SSH:' + self.ssh_conn_cfg.host + ':' + self.__host + ':' + self.__port
        else:
            id = 'DIRECT:' + self.__host
        id = bitcoin.sha256(id)
        return id

    def identical(self, cfg2):
        """
        Checks if connection object passed as an argument has exactly the same values as self object.
        :param cfg2: CrownNetworkConnectionCfg object to compare
        :return: True, if objects have identical attributes.
        """
        return self.host == cfg2.host and self.port == cfg2.port and self.username == cfg2.username and \
               self.password == cfg2.password and self.use_ssl == cfg2.use_ssl and \
               self.use_ssh_tunnel == cfg2.use_ssh_tunnel and \
               (not self.use_ssh_tunnel or (self.ssh_conn_cfg.host == cfg2.ssh_conn_cfg.host and
                                            self.ssh_conn_cfg.port == cfg2.ssh_conn_cfg.port and
                                            self.ssh_conn_cfg.username == cfg2.ssh_conn_cfg.username))

    def copy_from(self, cfg2):
        """
        Copies alle attributes from another instance of this class.
        :param cfg2: Another instance of this type from which attributes will be copied.
        """
        self.host = cfg2.host
        self.port = cfg2.port
        self.username = cfg2.username
        self.password = cfg2.password
        self.use_ssh_tunnel = cfg2.use_ssh_tunnel
        self.use_ssl = cfg2.use_ssl
        if self.use_ssh_tunnel:
            self.ssh_conn_cfg.host = cfg2.ssh_conn_cfg.host
            self.ssh_conn_cfg.port = cfg2.ssh_conn_cfg.port
            self.ssh_conn_cfg.username = cfg2.ssh_conn_cfg.username

    def is_http_proxy(self):
        """
        Returns if current config is a http proxy. Method is not very brilliant for now: we assume, that 
        proxy uses SSL while normal, "local" crownd does not. 
        """
        if self.__use_ssl:
            return True
        else:
            return False

    @property
    def enabled(self):
        return self.__enabled

    @enabled.setter
    def enabled(self, active):
        if not isinstance(active, bool):
            raise Exception('Invalid type of "enabled" argument')
        else:
            self.__enabled = active

    @property
    def method(self):
        return self.__method

    @method.setter
    def method(self, method):
        if method != 'rpc':
            raise Exception('Not allowed method type: %s' % method)
        self.__method = method

    @property
    def host(self):
        return self.__host

    @host.setter
    def host(self, host):
        self.__host = host

    @property
    def port(self):
        return self.__port

    @port.setter
    def port(self, port):
        if isinstance(port, int):
            port = str(port)
        self.__port = port

    @property
    def username(self):
        return self.__username

    @username.setter
    def username(self, username):
        self.__username = username

    @property
    def password(self):
        return self.__password

    @password.setter
    def password(self, password):
        self.__password = password

    def get_password_encrypted(self):
        try:
            return encrypt(self.__password, APP_NAME_LONG)
        except:
            return self.__password

    def set_encrypted_password(self, password):
        try:
            # check if password is a hexadecimal string - then it probably is an encrypted string with AES
            int(password, 16)
            p = decrypt(password, APP_NAME_LONG)
            password = p
        except Exception as e:
            logging.warning('Password decryption error: ' + str(e))

        self.__password = password

    @property
    def use_ssl(self):
        return self.__use_ssl

    @use_ssl.setter
    def use_ssl(self, use_ssl):
        if not isinstance(use_ssl, bool):
            raise Exception('Ivalid type of "use_ssl" argument')
        self.__use_ssl = use_ssl

    @property
    def use_ssh_tunnel(self):
        return self.__use_ssh_tunnel

    @use_ssh_tunnel.setter
    def use_ssh_tunnel(self, use_ssh_tunnel):
        if not isinstance(use_ssh_tunnel, bool):
            raise Exception('Ivalid type of "use_ssh_tunnel" argument')
        self.__use_ssh_tunnel = use_ssh_tunnel

    @property
    def ssh_conn_cfg(self):
        return self.__ssh_conn_cfg


#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Author: Bertrand256
# Created on: 2017-05

import datetime
import json
import logging
from urllib.error import URLError
import random
import re
import sqlite3
import threading
import time
import codecs
from functools import partial
from PyQt5 import QtWidgets, QtGui, QtChart, QtCore
from PyQt5.QtChart import QChart, QChartView, QLineSeries, QDateTimeAxis, QValueAxis, QBarSet, QBarSeries, \
    QBarCategoryAxis
from PyQt5.QtCore import Qt, pyqtSlot, QVariant, QAbstractTableModel, QSortFilterProxyModel, \
    QDateTime, QLocale
from PyQt5.QtGui import QColor, QPainter, QPen, QBrush
from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QMessageBox, QTableView, QAbstractItemView, QItemDelegate, \
    QStyledItemDelegate
from math import floor
import urllib.request
import ssl
import app_cache
import app_utils
import wnd_utils as wnd_utils
import crown_utils
#import crownd_intf
from columns_cfg_dlg import ColumnsConfigDlg
from common import AttrsProtected
from crownd_intf import CrowndIndexException
from ui import ui_proposals
from wnd_utils import WndUtils, CloseDialogException

# Definition of how long the cached proposals information is valid. If it's valid, dialog
# will display data from cache, instead of requesting them from a crown daemon, which is
# more time consuming.
PROPOSALS_CACHE_VALID_SECONDS = 3600

# Number of seconds after which voting will be reloaded for active proposals:
VOTING_RELOAD_TIME = 3600

# Superblock interval. In mainnet it's 43200 blocks or approximately 30 days
SUPERBLOCK_INTERVAL = 30 * 24 * 60

# Superblock voting deadline. In mainnet it's 2800 blocks or approximately 2 days
SUPERBLOCK_DEADLINE = 2 * 24 * 60

VOTE_CODE_YES = '1'
VOTE_CODE_NO = '2'
VOTE_CODE_ABSTAIN = '3'

# definition of symbols' for DB live configuration (tabel LIVE_CONFIG)
CFG_PROPOSALS_LAST_READ_TIME = 'proposals_last_read_time'
CFG_PROPOSALS_VOTES_MAX_DATE = 'prop_votes_max_date'  # maximum date of vote(s), read last time

COLOR_YES = '#2eb82e'
COLOR_NO = 'red'
COLOR_ABSTAIN = 'orange'
COLOR_UNKNOWN = 'black'
QCOLOR_YES = QColor(COLOR_YES)
QCOLOR_NO = QColor(COLOR_NO)
QCOLOR_ABSTAIN = QColor(COLOR_ABSTAIN)
QCOLOR_UNKNOWN = QColor(COLOR_UNKNOWN)


class ProposalColumn(AttrsProtected):
    def __init__(self, name, caption, visible, column_for_vote=False):
        """
        Constructor.
        :param name: Column name. There are: 1) static columns that display some piece of information about
            the proposal 2) dynamic columns, that display vote made by specified masternodes for each proposal.
            For dynamic column, name attribute equals to masternode identifier.
        :param caption: Column's caption.
        :param visible: True, if column is visible
        :param column_for_vote: True for (dynamic) columns related to mn voting.
        """
        AttrsProtected.__init__(self)
        self.name = name
        self.caption = caption
        self.visible = visible
        self.column_for_vote = column_for_vote
        self.my_masternode = None  # True, if column for masternode vote relates to user's masternode; such columns
        #  can not be removed
        self.initial_order = None  # order by voting-in-progress first, then by payment_start descending
        self.initial_width = None
        self.display_order_no = None
        self.set_attr_protection()


class Vote(AttrsProtected):
    def __init__(self, voting_masternode, voting_time, voting_result, voting_masternode_ident):
        super().__init__()
        self.voting_masternode = voting_masternode

        # use voting_masternode_ident only for non existing masternodes' vote:
        self.voting_masternode_ident = voting_masternode_ident if voting_masternode is None else None
        self.voting_time = voting_time
        self.voting_result = voting_result
        self.set_attr_protection()


class Proposal(AttrsProtected):
    def __init__(self, columns, vote_columns_by_mn_ident, next_superblock_time):
        super().__init__()
        self.visible = True
        self.columns = columns
        self.values = {}  # dictionary of proposal values (key: ProposalColumn)
        self.db_id = None
        self.marker = None
        self.modified = False
        self.next_superblock_time = next_superblock_time
        self.voting_last_read_time = 0
        self.voting_in_progress = True
        self.vote_columns_by_mn_ident = vote_columns_by_mn_ident
        self.votes_by_masternode_ident = {}  # list of tuples: vote_timestamp, vote_result
        self.ext_attributes_loaded = False

        # voting_status:
        #   1: voting in progress, funding
        #   2: voting in progress, no funding
        #   3: voting complete, historical funding status unknown
        self.voting_status = None

        self.name_col_widget = None
        self.title_col_widget = None
        self.url_col_widget = None
        self.initial_order_no = 0  # initial order

        self.set_attr_protection()

    def set_value(self, name, value):
        """
        Sets value for a specified Proposal column.
        :returns True, if new value is different than old value
        """
        for col in self.columns:
            if col.name == name:
                old_value = self.values.get(col)
                if old_value != value:
                    self.modified = True
                    self.values[col] = value
                    return True
                else:
                    return False
        raise AttributeError('Invalid proposal value name: ' + name)

    def get_value(self, column):
        """
        Returns value of for a specified column name.
        """
        if isinstance(column, str):
            if column == 'no':
                return self.initial_order_no + 1
            elif column == 'active':
                return self.voting_in_progress
            else:
                for col in self.columns:
                    if col.name == column:
                        return self.values.get(col)
            raise AttributeError('Invalid proposal column name: ' + column)
        elif isinstance(column, int):
            # column is a column index
            if column >= 0 and column < len(self.columns):
                return self.values.get(self.columns[column])
            raise AttributeError('Invalid proposal column index: ' + str(column))
        raise AttributeError("Invalid 'column' attribute type.")

    def apply_vote(self, mn_ident, vote_timestamp, vote_result):
        """ Apply vote result if a masternode is in the column list or is a user's masternode. """
        modified = False
        if mn_ident in self.votes_by_masternode_ident:
            if vote_timestamp > self.votes_by_masternode_ident[mn_ident][0]:
                self.votes_by_masternode_ident[mn_ident][0] = vote_timestamp
                self.votes_by_masternode_ident[mn_ident][1] = vote_result
                modified = True
        else:
            self.votes_by_masternode_ident[mn_ident] = [vote_timestamp, vote_result]
            modified = True

        if modified and mn_ident in self.vote_columns_by_mn_ident:
            # this vote shoud be shown in the dynamic column for vote results
            self.set_value(mn_ident, vote_result)

    def apply_values(self, masternodes, last_superblock_time, next_superblock_datetime):
        """ Calculate auto-calculated columns (eg. voting_in_progress and voting_status values). """

        payment_start = self.get_value('payment_start')
        if payment_start:
            payment_start = payment_start.timestamp()
        else:
            payment_start = None
        payment_end = self.get_value('payment_end')
        if payment_end:
            payment_end = payment_end.timestamp()
        else:
            payment_end = None

        if payment_start and payment_end and isinstance(last_superblock_time, (int, float)) \
                and isinstance(next_superblock_datetime, (int, float)):
            self.voting_in_progress = (payment_start > last_superblock_time) or \
                                      (payment_end > next_superblock_datetime)
        else:
            self.voting_in_progress = False

        if not self.get_value('title'):
            # if title value is not set (it's an external attribute, from Crown Services) then copy value from the
            # name column
            self.set_value('title', self.get_value('name'))

        abs_yes_count = self.get_value('absolute_yes_count')
        mns_count = 0
        for mn in masternodes:
            if mn.status in ('ENABLED', 'PRE_ENABLED'):
                mns_count += 1
        if self.voting_in_progress:
            if abs_yes_count >= mns_count * 0.1:
                self.voting_status = 1  # eligible to be funded
                self.set_value('voting_status_caption', 'Passing +%d (%d of %d needed)' %
                               (abs_yes_count - int(mns_count * 0.1), abs_yes_count, int(mns_count * 0.1)))
            else:
                self.voting_status = 2  # needs additional votes
                self.set_value('voting_status_caption', 'Needs additional %d votes' % (int(mns_count * 0.1) -
                                                                                       abs_yes_count))
        else:
            self.voting_status = 3  # Historical information is not recorded
            self.set_value('voting_status_caption', 'Unavailable')

class VotingMasternode(AttrsProtected):
    def __init__(self, masternode, masternode_config):
        """ Stores information about masternodes for which user has ability to vote.
        :param masternode: ref to an object storing mn information read from the network (crownd_intf.Masternode)
        :param masternode_config: ref to an object storing mn user's configuration (app_config.MasterNodeConfig)
        """
        super().__init__()
        self.masternode = masternode
        self.masternode_config = masternode_config
        self.btn_vote_yes = None  # dynamically created button for voting YES on behalf of this masternode
        self.btn_vote_no = None  # ... for voting NO
        self.btn_vote_abstain = None  # ... for voting ABSTAIN
        self.lbl_last_vote = None  # label to display last voting results for this masternode and currently focused prop
        self.set_attr_protection()


class ProposalsDlg(QDialog, ui_proposals.Ui_ProposalsDlg, wnd_utils.WndUtils):
    def __init__(self, parent, crownd_intf):
        QDialog.__init__(self, parent=parent)
        wnd_utils.WndUtils.__init__(self, parent.config)
        self.setWindowFlags(Qt.Window)
        self.main_wnd = parent
        self.finishing = False  # True if the dialog is closing (all thread operations will be stopped)
        self.crownd_intf = crownd_intf
        self.db_intf = parent.config.db_intf
        self.columns = [
            ProposalColumn('name', 'Name', False),
            ProposalColumn('url', 'URL', False),
            ProposalColumn('hash', 'Hash', False),
            ProposalColumn('fee_hash', 'Fee Hash', False),
            ProposalColumn('block_start', 'Block Start', True),
            ProposalColumn('block_end', 'Block End', True),
            ProposalColumn('total_payment_count', 'Payments', True),
            ProposalColumn('remaining_payment_count', 'Payments Remaining', True),
            ProposalColumn('payment_address', 'Payment Address', True),
            ProposalColumn('ratio', 'Ratio', False),
            ProposalColumn('yes_count', "Yeas", True),
            ProposalColumn('no_count', 'Nays', True),
            ProposalColumn('abstain_count', 'Abstentions', True),
            ProposalColumn('total_payment', 'Total Payment', True),
            ProposalColumn('monthly_payment', 'Per Payment', True),
            ProposalColumn('is_established', 'IsEstablished', False),
            ProposalColumn('is_valid', 'IsValid', False),
            ProposalColumn('is_valid_reason', 'IsValidReason', False),
            ProposalColumn('f_valid', 'fValid', False),
            ProposalColumn('no', 'No', True),
            ProposalColumn('title', 'Title', True),
            ProposalColumn('owner', 'Owner', False),
            ProposalColumn('voting_status_caption', 'Voting Status', True),
            ProposalColumn('active', 'Active', True),
            ProposalColumn('absolute_yes_count', 'Absolute Yes Count', False),
            ProposalColumn('payment_start', 'Payment Start', True),
            ProposalColumn('payment_end', 'Payment End', True),
            ProposalColumn('creation_time', 'Creation Time', True),
            ProposalColumn('fCachedDelete', 'fCachedDelete', False)
        ]
        self.vote_columns_by_mn_ident = {}
        self.proposals = []
        self.proposals_by_hash = {}  # dict of Proposal object indexed by proposal hash
        self.proposals_by_db_id = {}
        self.masternodes = []
        self.masternodes_by_ident = {}
        self.masternodes_by_db_id = {}

        # masternodes existing in the user's configuration, which can vote - list of VotingMasternode objects
        self.users_masternodes = []
        self.users_masternodes_by_ident = {}

        self.mn_count = None
        self.governanceinfo = None
        self.last_superblock_time = None
        self.next_superblock_time = None
        self.voting_deadline_passed = True  # True when current block number is >= next superblock - (2 * 24 * 60)
        self.proposals_last_read_time = 0
        self.current_proposal = None
        self.propsModel = None
        self.proxyModel = None
        self.votesModel = None
        self.votesProxyModel = None
        self.last_chart_type = None
        self.last_chart_proposal = None
        self.controls_initialized = False
        self.vote_chart = QChart()
        self.vote_chart_view = QChartView(self.vote_chart)
        self.refresh_details_event = threading.Event()
        self.current_chart_type = -1  # converted from UI radio buttons:
                                      #   1: incremental by date, 2: summary, 3: vote change
        self.setupUi()

    def time_of_block(self, height):
        """
        Find or calculate the actual or estimated epoch time of a block.
        :param height: height of the block you want the creation time for
        :return: epoch time of the block
        """
        last_block = self.crownd_intf.getblockcount()
        if height <= last_block:
            hash = self.crownd_intf.getblockhash(height)
            header = self.crownd_intf.getblockheader(hash)
            block_time = header['time']
        else:
            delta_seconds = (height - last_block) * 60
            block_time = int(time.time()) + delta_seconds

        return block_time

    def time_of_block2(self, height, cache_height, cache_time):
        """
        Find or calculate the actual or estimated epoch time of a block.
        :param height: height of the block you want the creation time for
        :param cache_height: cached getblockcount() value
        :param cache_time: time of the cached getblockcount() block
        :return: epoch time of the block
        """
        if height == cache_height:
            block_time = cache_time
        elif height < cache_height:
            hash = self.crownd_intf.getblockhash(height)
            header = self.crownd_intf.getblockheader(hash)
            block_time = header['time']
        else:
            delta_seconds = (height - cache_height) * 60
            block_time = int(time.time()) + delta_seconds

        return block_time

    def setupUi(self):
        try:
            ui_proposals.Ui_ProposalsDlg.setupUi(self, self)

            self.edtProposalFilter.setVisible(True)
            self.lblProposalFilter.setVisible(True)

            self.on_chart_type_change()  # get the self.current_chart_type value from radiobuttons
            self.setWindowTitle('Proposals')

            self.buttonBox.button(QDialogButtonBox.Close).setAutoDefault(False)
            self.resize(self.get_cache_value('WindowWidth', self.size().width(), int),
                        self.get_cache_value('WindowHeight', self.size().height(), int))

            self.detailsSplitter.setStretchFactor(0, 1)
            self.detailsSplitter.setStretchFactor(1, 0)

            self.votesSplitter.setStretchFactor(0, 0)
            self.votesSplitter.setStretchFactor(1, 1)

            # assign a new currentChanged handler; solution not very pretty, but there is no
            # signal for this purpose in QTableView
            self.propsView.currentChanged = self.on_propsView_currentChanged

            # let's define "dynamic" columns that show voting results for user's masternodes
            pkeys = []
            for idx, mn in enumerate(self.main_wnd.config.masternodes):
                mn_ident = mn.collateralTx + '-' + str(mn.collateralTxIndex)
                if mn_ident:
                    if crown_utils.privkey_valid(mn.privateKey):
                        if mn.privateKey not in pkeys:
                            self.add_voting_column(mn_ident, 'Vote (' + mn.name + ')', my_masternode=True,
                                                   insert_before_column=self.column_index_by_name('absolute_yes_count'))
                            pkeys.append(mn.privateKey)
                        else:
                            logging.warning('Masternode %s private key already used. Skipping...' % mn.name)
                    else:
                        logging.warning('Invalid private key for masternode ' + mn.name)

            reset_columns_order = False
            hide_name_column = False

            """ Read configuration of grid columns such as: display order, visibility. Also read configuration
             of dynamic columns: when user decides to display voting results of a masternode, which is not 
             in his configuration (because own mns are shown by defailt).
             Format: list of dicts:
             1. for static columns
                {
                   name:  Column name (str), 
                   visible: (bool)
                },
             2. for dynamic (masternode voting) columns:
                {
                    name: Masternode ident (str),
                    visible: (bool),
                    column_for_vote: True if the column relates to masternode voting (bool),
                    caption: Column's caption (str)
                }
            """
            cfg_cols = self.get_cache_value('ProposalsColumnsCfg', [], list)
            if isinstance(cfg_cols, list):
                for col_saved_index, c in enumerate(cfg_cols):
                    name = c.get('name')
                    visible = c.get('visible', True)
                    column_for_vote = c.get('column_for_vote')
                    caption = c.get('caption')
                    initial_width = c.get('width')
                    if not isinstance(initial_width, int):
                        initial_width = None

                    if isinstance(name, str) and isinstance(visible, bool) and isinstance(column_for_vote, bool):
                        found = False
                        for col in self.columns:
                            if col.name == name:
                                col.visible = visible
                                col.initial_width = initial_width
                                if not reset_columns_order:
                                    col.display_order_no = col_saved_index
                                found = True
                                break
                        # user defined dynamic columns will be implemented in the future:
                        # if not found and column_for_vote and caption:
                        #     # add voting column defined by the user
                        #     self.add_voting_column(name, caption, my_masternode=False,
                        #                            insert_before_column=self.column_index_by_name('payment_start'))
            else:
                logging.warning('Invalid type of cached ProposalsColumnsCfg')

            if hide_name_column:
                self.columns[self.column_index_by_name('name')].visible = False

            # set the visual order of columns with none
            for idx, col in enumerate(self.columns):
                if col.display_order_no is None:
                    col.display_order_no = idx

            self.columns.sort(key = lambda x: x.display_order_no if x.display_order_no is not None else 100)

            self.propsView.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
            self.propsView.setSortingEnabled(True)
            self.propsView.horizontalHeader().setSectionsMovable(True)
            self.propsView.horizontalHeader().sectionMoved.connect(self.on_propsViewColumnMoved)
            self.propsView.focusInEvent = self.focusInEvent
            self.propsView.focusOutEvent = self.focusOutEvent

            # create model serving data to the view
            self.propsModel = ProposalsModel(self, self.columns, self.proposals)
            self.proxyModel = ProposalFilterProxyModel(self, self.proposals, self.columns)
            self.proxyModel.add_filter_column(self.column_index_by_name('title'))
            self.proxyModel.add_filter_column(self.column_index_by_name('name'))
            self.proxyModel.add_filter_column(self.column_index_by_name('owner'))
            self.proxyModel.setSourceModel(self.propsModel)
            self.propsView.setModel(self.proxyModel)

            # set initial column widths
            hdr = self.propsView.horizontalHeader()
            for col_idx, col in enumerate(self.columns):
                if col.initial_width:
                    self.propsView.setColumnWidth(col_idx, col.initial_width)
                if not col.visible:
                    # hide columns with hidden attribute
                    hdr.hideSection(col_idx)

            self.propsView.verticalHeader().setDefaultSectionSize(
                self.propsView.verticalHeader().fontMetrics().height() + 6)

            self.votesView.verticalHeader().setDefaultSectionSize(
                self.votesView.verticalHeader().fontMetrics().height() + 6)

            self.tabsDetails.resize(self.tabsDetails.size().width(),
                                    self.get_cache_value('DetailsHeight', 200, int))

            # setting up a view with voting history
            self.votesView.setSortingEnabled(True)

            # create model serving data to the view
            self.votesModel = VotesModel(self, self.masternodes, self.masternodes_by_db_id,
                                         self.users_masternodes_by_ident,
                                         self.db_intf)
            self.votesProxyModel = VotesFilterProxyModel(self)
            self.votesProxyModel.setSourceModel(self.votesModel)
            self.votesView.setModel(self.votesProxyModel)

            # restore votes grid columns' widths
            cfg_cols = self.get_cache_value('VotesColumnsCfg', [], list)
            if isinstance(cfg_cols, list):
                for col_saved_index, c in enumerate(cfg_cols):
                    initial_width = c.get('width')
                    if not isinstance(initial_width, int):
                        initial_width = None
                    if initial_width and col_saved_index < self.votesModel.columnCount():
                        self.votesView.setColumnWidth(col_saved_index, initial_width)
            else:
                logging.warning('Invalid type of cached VotesColumnsCfg')
            self.chbOnlyMyVotes.setChecked(self.get_cache_value('VotesHistoryShowOnlyMyVotes', False, bool))

            filter_text = self.get_cache_value('VotesHistoryFilterText', '', str)
            self.edtVotesViewFilter.setText(filter_text)
            if filter_text:
                self.votesProxyModel.set_filter_text(filter_text)
            self.btnApplyVotesViewFilter.setEnabled(False)
            self.tabsDetails.setCurrentIndex(0)

            self.layoutVotesChart.addWidget(self.vote_chart_view)
            self.vote_chart_view.setRenderHint(QPainter.Antialiasing)
            self.votesSplitter.setSizes([self.get_cache_value('VotesHistLeftWidth', 600, int),
                                         self.get_cache_value('VotesHistRightWidth', 600, int)])

            # disable voting tab until we make sure the user has voting masternodes configured
            self.tabsDetails.setTabEnabled(1, False)
            self.btnProposalsRefresh.setEnabled(False)
            self.btnVotesRefresh.setEnabled(False)

            def after_data_load():
                self.setup_user_voting_controls()
                self.enable_refresh_buttons()

            # read initial data (from db) inside a thread and then read data from network if needed
            self.runInThread(self.read_data_thread, (),
                             on_thread_finish=after_data_load,
                             on_thread_exception=self.enable_refresh_buttons,
                             skip_raise_exception=True)

            # run thread reloading proposal details when the selected proposal changes
            self.runInThread(self.refresh_preview_panel_thread, ())
        except:
            logging.exception('Exception occurred')
            raise

    def updateUi(self):
        pass

    def closeEvent(self, event):
        self.finishing = True
        self.refresh_details_event.set()
        self.votesModel.finish()
        self.save_config()
        logging.info('Closing the dialog.')

    def save_config(self):
        """
        Saves dynamic configuration (for example grid columns) to cache.
        :return:
        """
        try:
            cfg = []
            hdr = self.propsView.horizontalHeader()

            for col_idx, col in enumerate(sorted(self.columns, key=lambda x: x.display_order_no)):
                logical_index = hdr.logicalIndex(col_idx)
                c = {
                    'name': col.name,
                    'visible': col.visible,
                    'column_for_vote': col.column_for_vote,
                    'caption': col.caption,
                    'width': self.propsView.columnWidth(logical_index)
                }
                cfg.append(c)
            self.set_cache_value('ProposalsColumnsCfg', cfg)

            # save voting-results tab configuration
            # columns' withds
            cfg.clear()
            for col_idx in range(0, self.votesModel.columnCount()):
                width = self.votesView.columnWidth(col_idx)
                c = {'width': width}
                cfg.append(c)
            self.set_cache_value('VotesColumnsCfg', cfg)

            siz = self.votesSplitter.sizes()
            if len(siz) >= 2:
                self.set_cache_value('VotesHistLeftWidth', siz[0])
                self.set_cache_value('VotesHistRightWidth', siz[1])

            self.set_cache_value('WindowWidth', self.size().width())
            self.set_cache_value('WindowHeight', self.size().height())
            self.set_cache_value('DetailsHeight', self.tabsDetails.size().height())
            self.set_cache_value('VotesHistoryShowOnlyMyVotes', self.chbOnlyMyVotes.isChecked())
            self.set_cache_value('VotesHistoryFilterText', self.edtVotesViewFilter.text())
            self.set_cache_value('TabDetailsCurrentIndex', self.tabsDetails.currentIndex())

        except Exception as e:
            logging.exception('Exception while saving dialog configuration to cache.')

    def setup_user_voting_controls(self):
        # setup a user-voting tab
        mn_index = 0
        self.btnVoteYesForAll.setProperty('yes', True)
        self.btnVoteNoForAll.setProperty('no', True)
        self.btnVoteAbstainForAll.setProperty('abstain', True)
        self.btnVoteYesForAll.setEnabled(False)
        self.btnVoteNoForAll.setEnabled(False)
        self.btnVoteAbstainForAll.setEnabled(False)
        for user_mn in self.users_masternodes:
            lbl = QtWidgets.QLabel(self.scrollAreaVotingContents)
            lbl.setText('<b>%s</b> (%s)' % (user_mn.masternode_config.name,
                                            user_mn.masternode_config.ip + ':' +
                                            user_mn.masternode_config.port))
            self.layoutUserVoting.addWidget(lbl, mn_index + 1, 0, 1, 1)

            user_mn.btn_vote_yes = QtWidgets.QPushButton(self.scrollAreaVotingContents)
            user_mn.btn_vote_yes.setText("Vote Yes")
            user_mn.btn_vote_yes.setProperty('yes', True)
            user_mn.btn_vote_yes.setEnabled(False)
            user_mn.btn_vote_yes.setAutoDefault(False)
            user_mn.btn_vote_yes.clicked.connect(partial(self.on_btnVoteYes_clicked, user_mn))
            self.layoutUserVoting.addWidget(user_mn.btn_vote_yes, mn_index + 1, 1, 1, 1)

            user_mn.btn_vote_no = QtWidgets.QPushButton(self.scrollAreaVotingContents)
            user_mn.btn_vote_no.setText("Vote No")
            user_mn.btn_vote_no.setProperty('no', True)
            user_mn.btn_vote_no.setEnabled(False)
            user_mn.btn_vote_no.setAutoDefault(False)
            user_mn.btn_vote_no.clicked.connect(partial(self.on_btnVoteNo_clicked, user_mn))
            self.layoutUserVoting.addWidget(user_mn.btn_vote_no, mn_index + 1, 2, 1, 1)

            user_mn.btn_vote_abstain = QtWidgets.QPushButton(self.scrollAreaVotingContents)
            user_mn.btn_vote_abstain.setText("Vote Abstain")
            user_mn.btn_vote_abstain.setProperty('abstain', True)
            user_mn.btn_vote_abstain.setEnabled(False)
            user_mn.btn_vote_abstain.setAutoDefault(False)
            user_mn.btn_vote_abstain.clicked.connect(partial(self.on_btnVoteAbstain_clicked, user_mn))
            self.layoutUserVoting.addWidget(user_mn.btn_vote_abstain, mn_index + 1, 3, 1, 1)

            user_mn.lbl_last_vote = QtWidgets.QLabel(self.scrollAreaVotingContents)
            user_mn.lbl_last_vote.setText('')
            self.layoutUserVoting.addWidget(user_mn.lbl_last_vote, mn_index + 1, 4, 1, 1)
            mn_index += 1
        self.scrollAreaVotingContents.setStyleSheet('QPushButton[yes="true"]{color:%s} QPushButton[no="true"]{color:%s}'
                                     'QPushButton[abstain="true"]{color:%s}' %
                                     (COLOR_YES, COLOR_NO, COLOR_ABSTAIN))
        if len(self.users_masternodes) > 0:
            self.tabsDetails.setTabEnabled(1, True)
        self.controls_initialized = True

    def disable_refresh_buttons(self):
        self.btnProposalsRefresh.setEnabled(False)
        self.btnVotesRefresh.setEnabled(False)

    def enable_refresh_buttons(self, exception_in=None):
        if self.current_proposal is None and len(self.proposals) > 0:
            self.propsView.selectRow(0)
        self.btnProposalsRefresh.setEnabled(True)
        self.btnVotesRefresh.setEnabled(True)

    def keyPressEvent(self, event):
        mods = int(event.modifiers())
        processed = False

        if mods == int(Qt.ControlModifier) | int(Qt.AltModifier):

            if ord('E') == event.key():
                # CTR-ALT-E (Mac: CMD-ALT-E): reload all proposals external properties
                self.special_action_reload_external_attributes()
                processed = True

        if not processed:
            QDialog.keyPressEvent(self, event)

    def special_action_reload_external_attributes(self):
        """ Action invoked by the shortcut: CTRL/CMD-ALT-E: reload proposal external attributes. """
        if self.btnProposalsRefresh.isEnabled():
            if self.queryDlg('Do you really want to reload proposal external attributes?',
                             buttons=QMessageBox.Yes | QMessageBox.Cancel,
                             default_button=QMessageBox.Yes, icon=QMessageBox.Information) == QMessageBox.Yes:

                def display_data():
                    self.display_proposals_data()
                    self.refresh_preview_panel()

                def reload_ext_attrs_thread(ctrl):
                    cur = self.db_intf.get_cursor()
                    try:
                        cur.execute("update PROPOSALS set title=null, owner=null, ext_attributes_loaded=0")
                        self.db_intf.commit()
                        if self.read_external_attibutes(self.proposals):
                            WndUtils.call_in_main_thread(display_data)

                    except CloseDialogException:
                        pass
                    except Exception as e:
                        logging.exception('Exception while reloading proposal external attributes')
                        self.errorMsg('Error while retrieving proposals data: ' + str(e))
                    finally:
                        self.db_intf.release_cursor()

                self.disable_refresh_buttons()
                self.runInThread(reload_ext_attrs_thread, (),
                                 on_thread_finish=self.enable_refresh_buttons,
                                 on_thread_exception=self.enable_refresh_buttons,
                                 skip_raise_exception=True)

    def update_proposals_order_no(self):
        """ Executed always when number of proposals changed. """
        for index, prop in enumerate(self.proposals):
            prop.initial_order_no = self.proxyModel.mapFromSource(self.propsModel.index(index, 0)).row()

    def add_voting_column(self, mn_ident, mn_label, my_masternode=None, insert_before_column=None):
        """
        Adds a dynamic column that displays a vote of the masternode with the specified identifier.
        :return:
        """
        # first check if this masternode is already added to voting columns
        for col in self.columns:
            if col.column_for_vote and col.name == mn_ident:
                return  # column for this masternode is already added

        col = ProposalColumn(mn_ident, mn_label, visible=True, column_for_vote=True)
        if isinstance(insert_before_column, int) and insert_before_column < len(self.columns):
            self.columns.insert(insert_before_column, col)
        else:
            self.columns.append(col)
        self.vote_columns_by_mn_ident[mn_ident] = col

        if my_masternode is None:
            # check if the specified masternode is in the user configuration; if so, mark the column
            # that it can't be removed
            for idx, mn in enumerate(self.main_wnd.config.masternodes):
                mn_ident_cfg = mn.collateralTx + '-' + str(mn.collateralTxIndex)
                if mn_ident_cfg == mn_ident:
                    col.my_masternode = True
                    break
        else:
            col.my_masternode = my_masternode

    def display_message(self, message):
        def disp(msg):
            if msg:
                self.lblMessage.setVisible(True)
                self.lblMessage.setText('<b style="color:#0059b3">' + msg + '<b>')
            else:
                self.lblMessage.setVisible(False)
                self.lblMessage.setText('')

        if not self.finishing:
            if threading.current_thread() != threading.main_thread():
                WndUtils.call_in_main_thread(disp, message)
            else:
                disp(message)

    def display_budget_message(self, message):
        def disp(msg):
            if msg:
                self.lblBudgetSummary.setVisible(True)
                self.lblBudgetSummary.setText(message)
            else:
                self.lblBudgetSummary.setVisible(False)
                self.lblBudgetSummary.setText('')

        if not self.finishing:
            if threading.current_thread() != threading.main_thread():
                WndUtils.call_in_main_thread(disp, message)
            else:
                disp(message)

    def column_index_by_name(self, name):
        """
        Returns index of a column with a given name.
        :param name: name of a column
        :return: index of a column
        """
        for idx, pc in enumerate(self.columns):
            if pc.name == name:
                return idx
        raise Exception('Invalid column name: ' + name)

    def read_proposals_from_network(self):
        """ Reads proposals from the Crown network. """

        def clean_float(data_in):
            # deals with JSON field 'monthly_payment' passed as different type for different proposals  - when it's
            # a string, then comma (if exists) is replaced wit a dot, otherwise it's converted to a float
            if isinstance(data_in, str):
                return float(data_in.replace(',', '.'))
            elif data_in is None:
                return data_in
            else:
                return float(data_in)  # cast to float regardless of the type

        try:

            self.display_message('Reading proposals data, please wait...')
            logging.info('Reading proposals from the Crown network.')
            begin_time = time.time()
            proposals_new = self.crownd_intf.mnbudget("show")
            logging.info('Read proposals from network (mnbudget show). Count: %s, operation time: %s' %
                         (str(len(proposals_new)), str(time.time() - begin_time)))

            rows_added = False

            # reset marker value in all existing Proposal object - we'll use it to check which
            # of previously read proposals do not exist anymore
            for prop in self.proposals:
                prop.marker = False
                prop.modified = False  # all modified proposals will be saved to DB cache

            # optimise get_block_time 
            cache_height = self.crownd_intf.getblockcount()
            hash = self.crownd_intf.getblockhash(cache_height)
            header = self.crownd_intf.getblockheader(hash)
            cache_time = header['time']

            errors = 0
            for pro_key in proposals_new:
                hash = '?'
                try:
                    prop_raw = proposals_new[pro_key]

                    hash = prop_raw['Hash']
                    prop = self.proposals_by_hash.get(hash)
                    if not prop:
                        is_new = True
                        prop = Proposal(self.columns, self.vote_columns_by_mn_ident, self.next_superblock_time)
                    else:
                        is_new = False
                    prop.marker = True

                    block_start = int(prop_raw['BlockStart'])
                    total_payment_count = int(prop_raw['TotalPaymentCount'])

                    prop.set_value('name', prop_raw['Name'])
                    prop.set_value('url', prop_raw['URL'])
                    prop.set_value('hash', hash)
                    prop.set_value('fee_hash', prop_raw['FeeHash'])
                    prop.set_value('block_start', block_start)
                    prop.set_value('total_payment_count', total_payment_count)
                    prop.set_value('payment_address', prop_raw["PaymentAddress"])
                    prop.set_value('ratio', clean_float(prop_raw['Ratio']))
                    prop.set_value('yes_count', int(prop_raw['Yeas']))
                    prop.set_value('no_count', int(prop_raw['Nays']))
                    prop.set_value('absolute_yes_count', int(prop_raw['Yeas']) - int(prop_raw['Nays']))
                    prop.set_value('abstain_count', int(prop_raw['Abstains']))
                    prop.set_value('total_payment', clean_float(prop_raw['TotalPayment']))
                    prop.set_value('monthly_payment', clean_float(prop_raw['MonthlyPayment']))
                    prop.set_value('is_established', prop_raw['IsEstablished'])
                    prop.set_value('is_valid', prop_raw['IsValid'])
                    prop.set_value('is_valid_reason', prop_raw['IsValidReason'])
                    prop.set_value('f_valid', prop_raw['fValid'])

                    # Some of the values in the proposal system are at best dubious, otherwise wrong.
                    # In particular, BlockEnd is set in masternode-budget.cpp to 
                    #    BlockStart+(TotalPaymentCount*SuperblockInterval)+SuperblockInterval/2
                    # which is confusing nonsense. I *think* the fencepost error is unintentional and the BlockEnd
                    # value is badly named and is really the block after which the proposal should be deleted from
                    # the network.
                    # Also, RemainingPaymentCount can be wrong so we calculate it ourself.
                    block_end = block_start + (total_payment_count - 1) * SUPERBLOCK_INTERVAL
                    if cache_height < block_start:
                        payments_remaining = total_payment_count
                    elif cache_height <= block_end:
                        payments_made = (cache_height - block_start) // SUPERBLOCK_INTERVAL + 1
                        payments_remaining = int(prop_raw['TotalPaymentCount']) - payments_made
                    else:
                        payments_remaining = 0
                    prop.set_value('block_end', block_end)
                    prop.set_value('remaining_payment_count', payments_remaining)
                    prop.set_value('payment_start', datetime.datetime.fromtimestamp(self.time_of_block2(block_start, cache_height, cache_time)))
                    prop.set_value('payment_end', datetime.datetime.fromtimestamp(self.time_of_block2(block_end, cache_height, cache_time)))

                    prop.apply_values(self.masternodes, self.last_superblock_time, self.next_superblock_time)
                    
                    if is_new:
                        creation_txn = self.crownd_intf.getrawtransaction(prop_raw['FeeHash'], 1)
                        prop.set_value('creation_time', datetime.datetime.fromtimestamp(creation_txn['time']))
                        self.proposals.append(prop)
                        self.proposals_by_hash[prop.get_value('hash')] = prop
                        rows_added = True
                except Exception as e:
                    logging.exception('Error while processing proposal data. Proposal hash: ' + hash)
                    errors += 1

            if len(proposals_new) > 0:
                if errors < len(proposals_new)/10:
                    try:
                        cur = self.db_intf.get_cursor()

                        for prop in self.proposals:
                            if self.finishing:
                                raise CloseDialogException

                            if prop.marker:
                                if not prop.db_id:
                                    # first, check if there is a proposal with the same hash in the database
                                    # crownd sometimes does not return some proposals, so they are deactivated in the db
                                    hash = prop.get_value('hash')
                                    cur.execute('SELECT id from PROPOSALS where hash=?', (hash,))
                                    row = cur.fetchone()
                                    if row:
                                        prop.db_id = row[0]
                                        prop.modified = True
                                        cur.execute('UPDATE PROPOSALS set cmt_active=1, cmt_deactivation_time=NULL '
                                                    'WHERE id=?', (row[0],))
                                        logging.info('Proposal "%s" (db_id: %d) exists int the DB. Re-activating.' %
                                                     (hash, row[0]))

                                if not prop.db_id:
                                    logging.info('Adding a new proposal to DB. Hash: ' + prop.get_value('hash'))
                                    cur.execute("INSERT INTO PROPOSALS (name, url, hash, fee_hash, block_start,"
                                                " block_end, total_payment_count, remaining_payment_count,"
                                                " payment_address, ratio, yes_count, no_count, absolute_yes_count,"
                                                " abstain_count, total_payment, monthly_payment, is_established,"
                                                " is_valid, is_valid_reason, f_valid, payment_start, payment_end,"
                                                " creation_time, cmt_active, cmt_create_time,"
                                                " cmt_deactivation_time, cmt_voting_last_read_time)"
                                                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)",
                                                (prop.get_value('name'),
                                                 prop.get_value('url'),
                                                 prop.get_value('hash'),
                                                 prop.get_value('fee_hash'),
                                                 prop.get_value('block_start'),
                                                 prop.get_value('block_end'),
                                                 prop.get_value('total_payment_count'),
                                                 prop.get_value('remaining_payment_count'),
                                                 prop.get_value('payment_address'),
                                                 prop.get_value('ratio'),
                                                 prop.get_value('yes_count'),
                                                 prop.get_value('no_count'),
                                                 prop.get_value('absolute_yes_count'),
                                                 prop.get_value('abstain_count'),
                                                 prop.get_value('total_payment'),
                                                 prop.get_value('monthly_payment'),
                                                 prop.get_value('is_established'),
                                                 prop.get_value('is_valid'),
                                                 prop.get_value('is_valid_reason'),
                                                 prop.get_value('f_valid'),
                                                 prop.get_value('payment_start').strftime('%Y-%m-%d %H:%M:%S'),
                                                 prop.get_value('payment_end').strftime('%Y-%m-%d %H:%M:%S'),
                                                 prop.get_value('creation_time').strftime('%Y-%m-%d %H:%M:%S'),
                                                 1,
                                                 datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                                 None))
                                    prop.db_id = cur.lastrowid
                                    self.proposals_by_db_id[prop.db_id] = prop
                                else:
                                    # proposal's db record already exists, check if should be updated
                                    if prop.modified:
                                        logging.debug('Updating proposal in the DB. Hash: %s, DB id: %d' %
                                                      (prop.get_value('hash'), prop.db_id) )
                                        cur.execute("UPDATE PROPOSALS set name=?, url=?, hash=?, fee_hash=?, "
                                                    "block_start=?, block_end=?, total_payment_count=?, "
                                                    "remaining_payment_count=?, payment_address=?, ratio=?, "
                                                    "yes_count=?, no_count=?, absolute_yes_count=?, abstain_count=?, "
                                                    "total_payment=?, monthly_payment=?, is_established=?, "
                                                    "is_valid=?, is_valid_reason=?, f_valid=? WHERE id=?",
                                                    (
                                                        prop.get_value('name'),
                                                        prop.get_value('url'),
                                                        prop.get_value('hash'),
                                                        prop.get_value('fee_hash'),
                                                        prop.get_value('block_start'),
                                                        prop.get_value('block_end'),
                                                        prop.get_value('total_payment_count'),
                                                        prop.get_value('remaining_payment_count'),
                                                        prop.get_value('payment_address'),
                                                        prop.get_value('ratio'),
                                                        prop.get_value('yes_count'),
                                                        prop.get_value('no_count'),
                                                        prop.get_value('absolute_yes_count'),
                                                        prop.get_value('abstain_count'),
                                                        prop.get_value('total_payment'),
                                                        prop.get_value('monthly_payment'),
                                                        prop.get_value('is_established'),
                                                        prop.get_value('is_valid'),
                                                        prop.get_value('is_valid_reason'),
                                                        prop.get_value('f_valid'),
                                                        prop.db_id
                                                    ))

                        # delete proposals which no longer exists in tha Crown network
                        rows_removed = False
                        for prop_idx in reversed(range(len(self.proposals))):
                            if self.finishing:
                                raise CloseDialogException

                            prop = self.proposals[prop_idx]

                            if not prop.marker:
                                logging.info('Deactivating proposal in the cache. Hash: %s, DB id: %s' %
                                              (prop.get_value('hash'), str(prop.db_id)))
                                cur.execute("UPDATE PROPOSALS set cmt_active=0, cmt_deactivation_time=? WHERE id=?",
                                            (datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), prop.db_id))

                                self.proposals_by_hash.pop(prop.get_value('hash'), 0)
                                self.proposals_by_db_id.pop(prop.db_id)
                                del self.proposals[prop_idx]
                                rows_removed = True

                        # self.set_cache_value('ProposalsLastReadTime', int(time.time()))  # save when proposals has been
                        cur.execute("UPDATE LIVE_CONFIG SET value=? WHERE symbol=?",
                                    (int(time.time()), CFG_PROPOSALS_LAST_READ_TIME))
                        if cur.rowcount == 0:
                            cur.execute("INSERT INTO LIVE_CONFIG(symbol, value) VALUES(?, ?)",
                                        (CFG_PROPOSALS_LAST_READ_TIME, int(time.time())))

                        if rows_added or rows_removed:
                            WndUtils.call_in_main_thread(self.display_proposals_data)

                    except CloseDialogException:
                        raise

                    except Exception as e:
                        logging.exception('Exception while saving proposals to db.')
                        self.db_intf.rollback()
                        raise
                    finally:
                        self.db_intf.commit()
                        self.db_intf.release_cursor()
                        self.display_message('')

                    if errors > 0:
                        self.warnMsg('Problems encountered while processing some of the proposals data. '
                                     'Look into the log file for details.')
                else:
                    # error count > 10% of the proposals count
                    raise Exception('Errors while processing proposals data. Look into the log file for details.')
            else:
                # no proposals read from network - skip deactivating records because probably
                # some network glitch occured
                logging.warning('No proposals returned from crownd.')
            logging.info('Finished reading proposals data from network.')

        except CloseDialogException:
            logging.info('Closing the dialog.')

        except Exception as e:
            logging.exception('Exception while reading proposals from Crown network.')
            self.display_message('')
            self.errorMsg('Error while reading proposals data from the Crown network: ' + str(e))
            raise

    def read_data_thread(self, ctrl):
        """ Reads data from the database.
        :param ctrl:
        """

        try:
            self.display_message('Connecting to Crown daemon, please wait...')
            if not self.crownd_intf.open():
                self.errorMsg('Crown daemon not connected')
            else:
                try:
                    try:
                        self.display_message('Reading governance data, please wait...')

                        # get the date-time of the next superblock and calculate the date-time of the last one
                        sb_next = self.crownd_intf.mnbudget('nextblock')
                        sb_last = sb_next - SUPERBLOCK_INTERVAL

                        cur_block = self.crownd_intf.getblockcount()

                        sb_last_hash = self.crownd_intf.getblockhash(sb_last)
                        last_bh = self.crownd_intf.getblockheader(sb_last_hash)
                        self.last_superblock_time = last_bh['time']
                        self.next_superblock_time = 0
                        if cur_block > 0 and cur_block <= sb_next:
                            cur_hash = self.crownd_intf.getblockhash(cur_block)
                            cur_bh = self.crownd_intf.getblockheader(cur_hash)
                            self.next_superblock_time = cur_bh['time'] + (sb_next - cur_block) * 60

                        if self.next_superblock_time == 0:
                            self.next_superblock_time = last_bh['time'] + SUPERBLOCK_INTERVAL * 60
                        deadline_block = sb_next - SUPERBLOCK_DEADLINE
                        self.voting_deadline_passed = deadline_block <= cur_block < sb_next

                        self.next_voting_deadline = self.next_superblock_time - (SUPERBLOCK_DEADLINE * 60)
                        self.next_voting_deadline -= time.timezone  # add a timezone correction
                        self.next_superblock_time -= time.timezone
                        next_sb_dt = datetime.datetime.utcfromtimestamp(self.next_superblock_time)
                        voting_deadline_dt = datetime.datetime.utcfromtimestamp(self.next_voting_deadline)
                        t = time.localtime(self.next_voting_deadline)
                        if self.voting_deadline_passed:
                            dl_passed = '<span style="color:red"> (passed)<span>'
                        else:
                            dl_passed = ''

                        message = '<div style="display:inline-block;margin-left:6px"><b>Next superblock date:</b> %s&nbsp;&nbsp;&nbsp;' \
                                  '<b>Voting deadline:</b> %s%s</div>' % \
                                  (self.main_wnd.config.to_string(next_sb_dt),
                                   self.main_wnd.config.to_string(voting_deadline_dt),
                                   dl_passed)
                        self.display_budget_message(message)

                    except Exception as e:
                        logging.exception('Exception while reading governance info.')
                        self.errorMsg("Coundn't read governance info from the Crown network. "
                                      "Some features may not work correctly because of this. Details: " + str(e))

                    # get list of all masternodes
                    self.display_message('Reading masternode data, please wait...')

                    # prepare a dict of user's masternodes configs (app_config.MasterNodeConfig); key: masternode
                    # ident (transaction id-transaction index)
                    users_mn_configs_by_ident = {}
                    for mn_cfg in self.main_wnd.config.masternodes:
                        ident = mn_cfg.collateralTx + '-' + mn_cfg.collateralTxIndex
                        if not ident in users_mn_configs_by_ident:
                            users_mn_configs_by_ident[ident] = mn_cfg

                    mns = self.crownd_intf.get_masternodelist('full')
                    self.masternodes = mns
                    self.mn_count = 0
                    statuses = {}

                    # count all active masternodes
                    for mn in mns:
                        if mn.status in ('ENABLED', 'PRE_ENABLED', 'NEW_START_REQUIRED', 'WATCHDOG_EXPIRED'):
                            self.mn_count += 1
                        if statuses.get(mn.status):
                            statuses[mn.status] += 1
                        else:
                            statuses[mn.status] = 1

                        # add mn to an ident indexed dict
                        self.masternodes_by_ident[mn.ident] = mn
                        self.masternodes_by_db_id[mn.db_id] = mn

                        mn_cfg = users_mn_configs_by_ident.get(mn.ident)
                        if mn_cfg:
                            if mn.ident not in self.users_masternodes_by_ident:
                                vmn = VotingMasternode(mn, mn_cfg)
                                self.users_masternodes.append(vmn)
                                self.users_masternodes_by_ident[mn.ident] = vmn

                    # sort user masternodes according to the order from the app's configuration
                    self.users_masternodes.sort(
                        key=lambda vmn: self.main_wnd.config.masternodes.index(vmn.masternode_config))

                    if self.db_intf.db_active:
                        try:
                            self.display_message('Reading proposals data from DB, please wait...')

                            # read all proposals from DB cache
                            cur = self.db_intf.get_cursor()
                            cur_fix = self.db_intf.get_cursor()
                            cur_fix_upd = self.db_intf.get_cursor()

                            cur.execute("SELECT value FROM LIVE_CONFIG WHERE symbol=?", (CFG_PROPOSALS_LAST_READ_TIME,))
                            row = cur.fetchone()
                            if row:
                                self.proposals_last_read_time = int(row[0])

                            logging.info("Reading proposals' data from DB")
                            tm_begin = time.time()
                            cur.execute(
                                "SELECT name, payment_start, payment_end, monthly_payment,"
                                " yes_count, absolute_yes_count, no_count, abstain_count, creation_time,"
                                " url, payment_address, hash, fee_hash,"
                                " is_valid_reason, cmt_active, cmt_create_time, cmt_deactivation_time, id,"
                                " cmt_voting_last_read_time, owner, title, ext_attributes_loaded "
                                "FROM PROPOSALS where cmt_active=1"
                            )

                            data_modified = False
                            for row in cur.fetchall():
                                if self.finishing:
                                    raise CloseDialogException

                                # fix the problem of duplicated proposals with the same hash, which could be
                                # deactivated due to some problems with previuos executions
                                # select all proposals with the same hash and move their votes to the current one
                                cur_fix.execute('select id from PROPOSALS where hash=? and id<>?',
                                                (row[11], row[17]))
                                for fix_row in cur_fix.fetchall():
                                    cur_fix_upd.execute('UPDATE VOTING_RESULTS set proposal_id=? where proposal_id=?',
                                                        (row[17], fix_row[0]))
                                    cur_fix_upd.execute('DELETE FROM PROPOSALS WHERE id=?', (fix_row[0],))
                                    data_modified = True
                                    logging.warning('Deleted duplicated proposal from DB. ID: %s, HASH: %s' %
                                                    (str(fix_row[0]), row[11]))

                                prop = Proposal(self.columns, self.vote_columns_by_mn_ident, self.next_superblock_time)
                                prop.set_value('name', row[0])
                                prop.set_value('payment_start', datetime.datetime.strptime(row[1], '%Y-%m-%d %H:%M:%S'))
                                prop.set_value('payment_end',  datetime.datetime.strptime(row[2], '%Y-%m-%d %H:%M:%S'))
                                prop.set_value('monthly_payment', row[3])
                                prop.set_value('yes_count', row[4])
                                prop.set_value('absolute_yes_count', row[5])
                                prop.set_value('no_count', row[6])
                                prop.set_value('abstain_count', row[7])
                                prop.set_value('creation_time', datetime.datetime.strptime(row[8], '%Y-%m-%d %H:%M:%S'))
                                prop.set_value('url', row[9])
                                prop.set_value('payment_address', row[10])
                                prop.set_value('hash', row[11])
                                prop.set_value('fee_hash', row[12])
                                prop.set_value('is_valid_reason', row[13])
                                prop.db_id = row[17]
                                prop.voting_last_read_time = row[18]
                                prop.set_value('owner', row[19])
                                prop.set_value('title', row[20])
                                prop.ext_attributes_loaded = True if row[21] else False
                                prop.apply_values(self.masternodes, self.last_superblock_time,
                                                  self.next_superblock_time)
                                self.proposals.append(prop)
                                self.proposals_by_hash[prop.get_value('hash')] = prop
                                self.proposals_by_db_id[prop.db_id] = prop

                            if data_modified:
                                self.db_intf.commit()

                            logging.info("Finished reading proposals' data from DB. Time: %s s" %
                                         str(time.time() - tm_begin))

                            def disp():
                                self.propsView.sortByColumn(self.column_index_by_name('no'),
                                                            Qt.AscendingOrder)
                                self.display_proposals_data()

                            # display data, now without voting results, which will be read below
                            WndUtils.call_in_main_thread(disp)

                        except CloseDialogException:
                            raise
                        except Exception as e:
                            logging.exception('Exception while saving proposals to db.')
                            self.errorMsg('Error while saving proposals data to db. Details: ' + str(e))
                        finally:
                            self.db_intf.release_cursor()
                            self.db_intf.release_cursor()
                            self.db_intf.release_cursor()

                    # read voting data from DB (only for "voting" columns)
                    self.read_voting_from_db(self.columns)

                except CloseDialogException:
                    raise

                except CrowndIndexException as e:
                    self.errorMsg(str(e))

                except Exception as e:
                    logging.exception('Exception while retrieving proposals data.')
                    self.errorMsg('Error while retrieving proposals data: ' + str(e))

            if not self.finishing:
                if int(time.time()) - self.proposals_last_read_time > PROPOSALS_CACHE_VALID_SECONDS or \
                   len(self.proposals) == 0:
                    # read proposals from network only after a configured time
                    self.read_proposals_from_network()

            if not self.finishing:
                # read additional data from external sources, if configured (Crown Services)
                proposals = []
                if self.main_wnd.config.read_proposals_external_attributes:
                    for prop in self.proposals:
                        if not prop.ext_attributes_loaded:
                            proposals.append(prop)
                if proposals and not self.finishing:
                    if self.read_external_attibutes(proposals):
                        WndUtils.call_in_main_thread(self.display_proposals_data)  # refresh display

            if not self.finishing:
                proposals = []
                for prop in self.proposals:
                    if (((time.time() - prop.voting_last_read_time) > VOTING_RELOAD_TIME) and
                       (prop.voting_in_progress or prop.voting_last_read_time == 0)):
                        proposals.append(prop)

                if proposals and not self.finishing:
                    self.read_voting_from_network(False, proposals)

        except CloseDialogException:
            logging.info('Closing the dialog.')

        except Exception as e:
            logging.exception('Exception while reading data.')
            self.errorMsg(str(e))

        finally:
            self.display_message("")

    def read_external_attibutes(self, proposals):
        """Method reads additional proposal attributes from an external source such as services.crownplatform.com
        :return True if proposals' external attributes has been updated.
        """
        self.display_message("Reading proposal external attributes, please wait...")
        begin_time = time.time()
        network_duration = 0
        modified_ext_attributes = False
        ssl._create_default_https_context = ssl._create_unverified_context
        url_err_retries = 2

        try:
            url = self.main_wnd.config.crown_services_proposal_api
            if url:
                exceptions_occurred = False
                for idx, prop in enumerate(proposals):
                    if self.finishing:
                        raise CloseDialogException
                    self.display_message("Reading proposal external attributes (%d/%d), please wait..." %
                                         (idx+1, len(proposals)))

                    prop.modified = False
                    try:
                        prop.marker = False
                        hash = prop.get_value('hash')
                        cur_url = url.replace('%HASH%', hash)
                        network_tm_begin = time.time()

                        for url_try in range(0, url_err_retries+1):
                            try:
                                response = urllib.request.urlopen(cur_url)
                                contents = response.read()
                                break
                            except URLError:
                                if url_try >= url_err_retries:
                                    raise
                                logging.info('URLError, retrying...')

                        network_duration += time.time() - network_tm_begin
                        if contents is not None:
                            contents = json.loads(contents.decode('utf-8'))
                        else:
                            contents = ''
                        prop.marker = True  # network operation went OK
                        p = contents.get('proposal')
                        if p is not None:
                            user_name = p.get('owner_username')
                            if user_name:
                                prop.set_value('owner', user_name)
                            title = p.get('title')
                            if title:
                                prop.set_value('title', title)
                        else:
                            err = contents.get('error_type')
                            if err is not None:
                                logging.error('Error returned for proposal "' + hash + '": ' + err)
                            else:
                                logging.error('Empty "proposal" attribute for proposal: ' + hash)
                    except CloseDialogException:
                        raise

                    except URLError as e:
                        exceptions_occurred = True
                        logging.warning(str(e))

                    except Exception as e:
                        exceptions_occurred = True
                        logging.error(str(e))

                if not self.finishing:
                    cur = self.db_intf.get_cursor()
                    try:
                        for prop in proposals:
                            if self.finishing:
                                raise CloseDialogException

                            if prop.marker:
                                if prop.modified:
                                    cur.execute(
                                        'UPDATE PROPOSALS set owner=?, title=?, ext_attributes_loaded=1 where id=?',
                                        (prop.get_value('owner'), prop.get_value('title'), prop.db_id))
                                    modified_ext_attributes = True
                                elif not prop.ext_attributes_loaded:
                                    # ext attributes loaded but empty; set ext_attributes_loaded to 1 to avoid reading
                                    # the same information the next time
                                    cur.execute('UPDATE PROPOSALS set ext_attributes_loaded=1 where id=?',
                                                (prop.db_id,))
                                prop.ext_attributes_loaded = True

                        self.db_intf.commit()
                    finally:
                        self.db_intf.release_cursor()

                    if exceptions_occurred:
                        self.errorMsg('Error(s) occurred while retrieving proposals external data from '
                                      'services.crownplatform.com.')

        except CloseDialogException:
            logging.info('Closing the dialog.')

        except Exception as e:
            logging.exception('Exception while reading external attributes.')

        finally:
            time_diff = time.time() - begin_time
            logging.info('Finished reading external attributes. Overall time: %s seconds, network time: %s.' %
                         (str(time_diff), str(network_duration)))
            self.display_message('')
        return modified_ext_attributes

    def read_voting_from_db(self, columns):
        """ Read voting results for specified voting columns
        :param columns list of voting columns for which data will be loaded from db; it is used when user adds
          a new column - we want read data only for this column
        """
        self.display_message('Reading voting data from DB, please wait...')
        begin_time = time.time()

        try:
            cur = self.db_intf.get_cursor()

            for col in columns:
                if col.column_for_vote:
                    mn_ident = col.name
                    mn = self.masternodes_by_ident.get(mn_ident)
                    if mn:
                        cur.execute("SELECT proposal_id, voting_time, voting_result "
                                    "FROM VOTING_RESULTS vr WHERE masternode_ident=? AND EXISTS "
                                    "(SELECT 1 FROM PROPOSALS p where p.id=vr.proposal_id and p.cmt_active=1)",
                                    (mn_ident,))
                        for row in cur.fetchall():
                            if self.finishing:
                                raise CloseDialogException
                            prop = self.proposals_by_db_id.get(row[0])
                            if prop:
                                prop.apply_vote(mn_ident, datetime.datetime.strptime(row[1], '%Y-%m-%d %H:%M:%S'),
                                                row[2])

        except CloseDialogException:
            logging.info('Closing the dialog.')

        except Exception as e:
            logging.exception('Exception while saving proposals to db.')

        finally:
            self.db_intf.release_cursor()
            time_diff = time.time() - begin_time
            logging.info('Voting data read from database time: %s seconds' % str(time_diff))

    def read_voting_from_network_thread(self, ctrl, force_reload_all, proposals):
        self.read_voting_from_network(force_reload_all, proposals)

    def read_voting_from_network(self, force_reload_all, proposals):
        """
        Retrieve from a Crown daemon voting results for all defined masternodes, for all visible Proposals.
        :param force_reload_all: force reloading all votes and make sure if a db cache contains all of them,
               if False, read only votes posted after last time when votes were read from the network
        :param proposals: list of proposals, which votes will be retrieved
        :return:
        """

        last_vote_max_date = 0
        cur_vote_max_date = 0
        db_modified = False
        cur = None
        refresh_preview_votes = False
        logging.info('Begin reading voting data from network.')
        try:
            # read the date/time of the last vote, read from the DB the last time, to initially filter out
            # of all older votes from finding if it has its record in the DB:
            if self.db_intf.is_active():
                cur = self.db_intf.get_cursor()
                cur.execute("SELECT value from LIVE_CONFIG WHERE symbol=?", (CFG_PROPOSALS_VOTES_MAX_DATE,))
                row = cur.fetchone()
                if row:
                    last_vote_max_date = int(row[0])

            votes_added = []  # list of tuples (proposal, masternode, voting_time, voting_result, masternode ident),
            # that has been added (will be saved to the database cache)

            if not self.crownd_intf.open():
                self.errorMsg('Crown daemon not connected')
            else:
                try:
                    proposals_updated = []  # list of proposals for which votes were loaded
                    db_oper_duration = 0.0
                    db_oper_count = 0
                    network_duration = 0.0

                    for row_idx, prop in enumerate(proposals):
                        if self.finishing:
                            raise CloseDialogException

                        self.display_message('Reading voting data %d of %d' % (row_idx+1, len(proposals)))
                        tm_begin = time.time()
                        votes = self.crownd_intf.mnbudget("getvotes", prop.get_value('name'))
                        network_duration += (time.time() - tm_begin)

                        for mn_ident in votes:
                            if self.finishing:
                                raise CloseDialogException

                            v = votes[mn_ident]
                            voting_timestamp = int(v['nTime'])
                            voting_time = datetime.datetime.fromtimestamp(voting_timestamp)
                            voting_hash = v['nHash']
                            voting_result = v['Vote']
                            mn = self.masternodes_by_ident.get(mn_ident)

                            if voting_timestamp > cur_vote_max_date:
                                cur_vote_max_date = voting_timestamp

                            if voting_timestamp >= (last_vote_max_date - 3600) or force_reload_all:
                                # check if vote exists in the database
                                if cur:
                                    tm_begin = time.time()
                                    cur.execute("SELECT id, proposal_id from VOTING_RESULTS WHERE hash=?",
                                                (voting_hash,))

                                    found = False
                                    for row in cur.fetchall():
                                        if row[1] == prop.db_id:
                                            found = True
                                            break

                                    db_oper_duration += (time.time() - tm_begin)
                                    db_oper_count += 1
                                    if not found:
                                        votes_added.append((prop, mn, voting_time, voting_result, mn_ident, voting_hash))
                                else:
                                    # no chance to check whether record exists in the DB, so assume it's not
                                    # to have it displayed on the grid
                                    votes_added.append((prop, mn, voting_time, voting_result, mn_ident, voting_hash))

                        proposals_updated.append(prop)

                    logging.info('Network calls duration: %s for %d proposals' %
                                 (str(network_duration), (len(proposals))))

                    # display data from dynamic (voting) columns
                    # WndUtils.call_in_main_thread(self.update_grid_data, cells_to_update)
                    logging.info('DB calls duration (stage 1): %s, SQL count: %d' % (str(db_oper_duration),
                                                                                    db_oper_count))

                    # save voting results to the database cache
                    for prop, mn, voting_time, voting_result, mn_ident, hash in votes_added:
                        if self.finishing:
                            raise CloseDialogException

                        if cur:
                            tm_begin = time.time()
                            try:
                                cur.execute("INSERT INTO VOTING_RESULTS(proposal_id, masternode_ident,"
                                            " voting_time, voting_result, hash) VALUES(?,?,?,?,?)",
                                            (prop.db_id,
                                             mn_ident,
                                             voting_time,
                                             voting_result,
                                             hash))
                            except sqlite3.IntegrityError as e:
                                if e.args and e.args[0].find('UNIQUE constraint failed') >= 0:
                                    # this vote is assigned to the same proposal but inactive one; correct this
                                    cur.execute("UPDATE VOTING_RESULTS"
                                        " set proposal_id=?, masternode_ident=?,"
                                        " voting_time=?, voting_result=? WHERE hash=?",
                                        (prop.db_id,
                                         mn_ident,
                                         voting_time,
                                         voting_result,
                                         hash))
                            db_modified = True
                            db_oper_duration += (time.time() - tm_begin)

                        if mn_ident in self.vote_columns_by_mn_ident:
                            prop.apply_vote(mn_ident, voting_time, voting_result)

                        # check if voting masternode has its column in the main grid;
                        # if so, pass the voting result to a corresponding proposal field
                        for col_idx, col in enumerate(self.columns):
                            if col.column_for_vote and col.name == mn_ident:
                                if prop.get_value(col.name) != voting_result:
                                    prop.set_value(col.name, voting_result)
                                break

                        # check if currently selected proposal got new votes; if so, update details panel
                        if prop == self.current_proposal:
                            refresh_preview_votes = True

                    if cur:
                        # update proposals' voting_last_read_time
                        for prop in proposals_updated:
                            if self.finishing:
                                raise CloseDialogException

                            prop.voting_last_read_time = time.time()
                            tm_begin = time.time()
                            cur.execute("UPDATE PROPOSALS set cmt_voting_last_read_time=? where id=?",
                                        (int(time.time()), prop.db_id))
                            db_modified = True
                            db_oper_duration += (time.time() - tm_begin)

                        logging.info('DB calls duration (stage 2): %s' % str(db_oper_duration))

                        if cur_vote_max_date > last_vote_max_date:
                            # save max vote date to the DB
                            db_modified = True
                            cur.execute("UPDATE LIVE_CONFIG SET value=? WHERE symbol=?",
                                        (cur_vote_max_date, CFG_PROPOSALS_VOTES_MAX_DATE))
                            if not cur.rowcount:
                                cur.execute("INSERT INTO LIVE_CONFIG(symbol, value) VALUES(?, ?)",
                                            (CFG_PROPOSALS_VOTES_MAX_DATE, cur_vote_max_date))

                except CloseDialogException:
                    raise

                except CrowndIndexException as e:
                    logging.exception('Exception while retrieving voting data.')
                    self.errorMsg(str(e))

                except Exception as e:
                    logging.exception('Exception while retrieving voting data.')
                    self.errorMsg('Error while retrieving voting data: ' + str(e))

        except CloseDialogException:
            logging.info('Closing the dialog.')

        except Exception as e:
            logging.exception('Exception while retrieving voting data.')

        finally:
            if cur:
                if db_modified:
                    self.db_intf.commit()
                self.db_intf.release_cursor()
            self.display_message(None)

        if refresh_preview_votes and not self.finishing:
            self.refresh_details_event.set()
        logging.info('Finished reading voting data from network.')

    def display_proposals_data(self):
        try:
            tm_begin = time.time()
            # reset special columns' widgets assigned to proposals
            for prop in self.proposals:
                prop.name_col_widget = None
                prop.title_col_widget = None
                prop.url_col_widget = None

            self.propsModel.beginResetModel()
            self.propsModel.endResetModel()

            # if there is no saved column widths, resize widths to its contents
            widths_initialized = False
            for col in self.columns:
                if col.initial_width:
                    widths_initialized = True
                    break

            if not widths_initialized:
                self.propsView.resizeColumnsToContents()

                # 'title' can be a quite long string so after auto-sizing columns we'd like to correct the
                # column's width to some reasonable value
                col_idx = self.column_index_by_name('title')
                col = self.columns[col_idx]
                if col.visible and self.propsView.columnWidth(col_idx) > 430:
                    self.propsView.setColumnWidth(col_idx, 430)

            self.update_proposals_order_no()

            logging.debug("Display proposals' data time: " + str(time.time() - tm_begin))
        except Exception as e:
            logging.exception("Exception occurred while displaing proposals.")
            self.lblMessage.setVisible(False)
            raise Exception('Error occurred while displaying proposals: ' + str(e))

    @pyqtSlot()
    def on_btnProposalsRefresh_clicked(self):
        self.btnProposalsRefresh.setEnabled(False)
        self.btnVotesRefresh.setEnabled(False)
        self.runInThread(self.refresh_proposals_thread, (),
                         on_thread_finish=self.enable_refresh_buttons,
                         on_thread_exception=self.enable_refresh_buttons,
                         skip_raise_exception=True)

    def refresh_proposals_thread(self, ctrl):
        self.read_proposals_from_network()

        proposals = []
        if self.main_wnd.config.read_proposals_external_attributes:
            # select proposals for which we read additional data from external sources as services.crownplatform.com
            for prop in self.proposals:
                if not prop.ext_attributes_loaded:
                    proposals.append(prop)
        if proposals and not self.finishing:
            if self.read_external_attibutes(proposals):
                WndUtils.call_in_main_thread(self.display_proposals_data) # refresh display

        proposals = []  # refresh "live" proposals only
        for prop in self.proposals:
            if prop.voting_in_progress or prop.voting_last_read_time == 0:
                proposals.append(prop)

        if proposals and not self.finishing:
            self.read_voting_from_network(False, proposals)

    @pyqtSlot()
    def on_buttonBox_accepted(self):
        self.accept()

    @pyqtSlot()
    def on_buttonBox_rejected(self):
        self.reject()

    def refresh_vote_tab(self):
        """ Refresh data displayed on the user-voting tab. Executed after changing focused proposal and after
        submitting a new votes. """
        if not self.controls_initialized:
            return

        if self.current_proposal is None or not self.current_proposal.voting_in_progress:
            for user_mn in self.users_masternodes:
                # setup voting buttons for each of user's masternodes
                user_mn.btn_vote_yes.setEnabled(False)
                user_mn.btn_vote_no.setEnabled(False)
                user_mn.btn_vote_abstain.setEnabled(False)
                user_mn.lbl_last_vote.setText('')
            self.btnVoteYesForAll.setEnabled(False)
            self.btnVoteNoForAll.setEnabled(False)
            self.btnVoteAbstainForAll.setEnabled(False)
        else:
            self.btnVoteYesForAll.setEnabled(True)
            self.btnVoteNoForAll.setEnabled(True)
            self.btnVoteAbstainForAll.setEnabled(True)

            for user_mn in self.users_masternodes:
                # setup voting buttons for each of user's masternodes
                user_mn.btn_vote_yes.setEnabled(True)
                user_mn.btn_vote_no.setEnabled(True)
                user_mn.btn_vote_abstain.setEnabled(True)
                vote = self.current_proposal.votes_by_masternode_ident.get(user_mn.masternode.ident)
                if vote:
                    user_mn.lbl_last_vote.setText('Last voted ' + vote[1] + ' on ' +
                                                  self.main_wnd.config.to_string(vote[0]))
                else:
                    user_mn.lbl_last_vote.setText('No your votes for this masternode')

    def on_propsView_currentChanged(self, new_index, old_index):
        """ Triggered when changing focused row in proposals' grid. """

        try:
            new_row = None
            old_row = None

            if new_index:
                new_index = self.proxyModel.mapToSource(new_index)
                if new_index:
                    new_row = new_index.row()
            if old_index:
                old_index = self.proxyModel.mapToSource(old_index)
                if old_index:
                    old_row = old_index.row()

            if new_row != old_row:
                if new_row is None:
                    self.current_proposal = None  # hide the details
                    self.votesModel.set_proposal(self.current_proposal)
                else:
                    if 0 <= new_row < len(self.proposals):
                        prev_proposal = self.current_proposal
                        self.current_proposal = self.proposals[new_row]  # show the details
                        self.correct_proposal_hyperlink_color(self.current_proposal)
                        self.correct_proposal_hyperlink_color(prev_proposal)
                    else:
                        self.current_proposal = None
                self.votesModel.set_proposal(self.current_proposal)
                self.refresh_vote_tab()
                self.refresh_preview_panel()
        except Exception as e:
            logging.exception('Exception while changing proposal selected.')
            self.errorMsg('Problem while refreshing data in the details panel: ' + str(e))

    def correct_proposal_hyperlink_color(self, proposal):
        """ When:
              a) proposal is active and
                a1) props grid is focused, font color of hyperlinks is white
                a2) props grid is not focused, color of hyperlinks is default
              b) proposal is inactive (not selected), font color of hyperlinks is default
        """
        def correct_hyperlink_color_active_row(prop):
            """ On proposals' grid there are some columns displaying hyperlinks. When rows are focused though, default
            colors make it hard to read: both, background and font are blue. To make it readable, set font's color to
            white."""
            if prop:
                url = prop.get_value('url')
                if url:
                    if prop.name_col_widget:
                        prop.name_col_widget.setText('<a href="%s" style="color:white">%s</a>' %
                                                     (url, prop.get_value('name')))
                    if prop.title_col_widget:
                        prop.title_col_widget.setText('<a href="%s" style="color:white">%s</a>' %
                                                     (url, prop.get_value('title')))
                    if prop.url_col_widget:
                        prop.url_col_widget.setText('<a href="%s" style="color:white">%s</a>' % (url, url))

        def correct_hyperlink_color_inactive_row(prop):
            """ After loosing focus, restore hyperlink's font color."""
            if prop:
                url = prop.get_value('url')
                if url:
                    if prop.name_col_widget:
                        prop.name_col_widget.setText('<a href="%s">%s</a>' % (url, prop.get_value('name')))
                    if prop.title_col_widget:
                        prop.title_col_widget.setText('<a href="%s">%s</a>' % (url, prop.get_value('title')))
                    if prop.url_col_widget:
                        prop.url_col_widget.setText('<a href="%s">%s</a>' % (url, url))

        if proposal == self.current_proposal and self.propsView.hasFocus():
            correct_hyperlink_color_active_row(proposal)
        else:
            correct_hyperlink_color_inactive_row(proposal)

    def focusInEvent(self, event):
        QTableView.focusInEvent(self.propsView, event)
        if self.current_proposal:
            self.correct_proposal_hyperlink_color(self.current_proposal)

    def focusOutEvent(self, event):
        QTableView.focusOutEvent(self.propsView, event)
        if self.current_proposal:
            self.correct_proposal_hyperlink_color(self.current_proposal)

    def refresh_preview_panel(self):
        try:
            if self.current_proposal:
                prop = self.current_proposal
                url = self.current_proposal.get_value('url')
                status = str(self.current_proposal.voting_status)

                payment_addr = self.current_proposal.get_value('payment_address')
                if self.main_wnd.config.block_explorer_addr:
                    payment_url = self.main_wnd.config.block_explorer_addr.replace('%ADDRESS%', payment_addr)
                    payment_addr = '<a href="%s">%s</a>' % (payment_url, payment_addr)

                col_hash = self.current_proposal.get_value('fee_hash')
                if self.main_wnd.config.block_explorer_tx:
                    col_url = self.main_wnd.config.block_explorer_tx.replace('%TXID%', col_hash)
                    col_hash = '<a href="%s">%s</a>' % (col_url, col_hash)

                def get_date_str(d):
                    if d is not None:
                        return self.main_wnd.config.to_string(d.date())
                    return None

                owner = prop.get_value('owner')
                if not owner:
                    owner = "&lt;Unknown&gt;"

                months = prop.get_value('total_payment_count')
                if months == 1:
                    months_str = '1 month'
                else:
                    months_str = str(months) + ' months'

                if prop.voting_in_progress:
                    class_voting_activity = 'vo-active'
                    voting_activity_str = 'Voting active'
                else:
                    class_voting_activity = 'vo-inactive'
                    voting_activity_str = 'Voting inactive'

                details = """<html>
                    <head>
                    <style type="text/css">
                        td.first-col-label, td.padding {padding-top:2px;padding-bottom:2px;}
                        td {border-style: solid; border-color:darkgray}
                        .first-col-label {font-weight: bold; text-align: right; padding-right:6px; white-space:nowrap}
                        .inter-label {font-weight: bold; padding-right: 5px; padding-left: 5px; white-space:nowrap}
                        .status-1{background-color:%s;color:white}
                        .status-2{background-color:%s;color:white}
                        .status-3{color:%s}
                        .status-4{color:%s}
                        .vo-active{color:green;font-weight: bold}
                        .vo-inactive{color:gray;font-weight: bold}
                    </style>
                    </head>
                    <body>
                    <table>
                        <tbody>
                            <tr class="main-row">
                                <td class="first-col-label">Name:</td>
                                <td class="padding">%s</td>
                            </tr>
                            <tr class="main-row">
                                <td class="first-col-label">Title:</td>
                                <td class="padding">%s</td>
                            </tr>
                            <tr class="main-row">
                                <td class="first-col-label">Owner:</td>
                                <td class="padding">%s</td>
                            </tr>
                            <tr class="main-row">
                                <td class="first-col-label">URL:</td>
                                <td class="padding"><a href="%s">%s</a></td>
                            </tr>
                            <tr class="main-row">
                                <td class="first-col-label">Voting:</td>
                                <td>
                                    <table>
                                        <tr >
                                            <td class="padding" style="white-space:nowrap"><span class="status-%s padding">%s</span>
                                            <br/><span class="%s">%s</span>
                                            <br/><span class="inter-label padding">Absolute yes count: </span>%s
                                            <span class="inter-label padding">&nbsp;&nbsp;Yes count: </span>%s
                                            <span class="inter-label padding">&nbsp;&nbsp;No count: </span>%s
                                            <span class="inter-label padding">&nbsp;&nbsp;Abstain count: </span>%s</td>
                                        </tr>
                                    </table>
                                </td>
                            </tr>
                            <tr class="main-row">
                                <td class="first-col-label">Payment:</td>
                                <td class="padding" style="white-space:nowrap"><span>%s Crown&#47;month (%s, %s Crown total)
                                    <br/><span class="inter-label">start - end:</span>&nbsp;&nbsp;%s - %s</span>
                                    <br/><span class="inter-label">address:</span>&nbsp;&nbsp;%s
                                </td>
                            </tr>
                            <tr class="main-row">
                                <td class="first-col-label">Creation time:</td>
                                <td class="padding">%s</td>
                            </tr>
                            <tr class="main-row">
                                <td class="first-col-label">Proposal hash:</td>
                                <td class="padding">%s</td>
                            </tr>
                            <tr class="main-row">
                                <td class="first-col-label">Collateral hash:</td>
                                <td class="padding">%s</td>
                            </tr>
                        </tbody>
                    </table>
                     </body>
                    </html>""" % (
                        COLOR_YES, COLOR_ABSTAIN, COLOR_UNKNOWN, COLOR_NO,
                        prop.get_value('name'),
                        prop.get_value('title'),
                        owner,
                        url, url,
                        status,
                        prop.get_value('voting_status_caption'),
                        class_voting_activity, voting_activity_str,
                        str(prop.get_value('absolute_yes_count')),
                        str(prop.get_value('yes_count')),
                        str(prop.get_value('no_count')),
                        str(prop.get_value('abstain_count')),
                        self.main_wnd.config.to_string(prop.get_value('monthly_payment')),
                        months_str,
                        self.main_wnd.config.to_string(prop.get_value('total_payment')),
                        get_date_str(prop.get_value('payment_start')),
                        get_date_str(prop.get_value('payment_end')),
                        payment_addr,
                        get_date_str(prop.get_value('creation_time')),
                        prop.get_value('hash'),
                        col_hash)

                self.edtDetails.setHtml(details)
                self.refresh_details_event.set()
            else:
                self.edtDetails.setHtml('')
                self.refresh_details_event.set()

        except Exception:
            logging.exception('Exception while refreshing proposal details panel')
            raise

    def draw_chart(self):
        """Draws a voting chart if proposal has changed.
        """
        try:
            new_chart_type = self.current_chart_type
            self.last_chart_proposal = self.current_proposal
            for s in self.vote_chart.series():
                self.vote_chart.removeSeries(s)

            if self.vote_chart.axisX() is not None:
                self.vote_chart.removeAxis(self.vote_chart.axisX())
            if self.vote_chart.axisY() is not None:
                self.vote_chart.removeAxis(self.vote_chart.axisY())

            if self.votesModel:
                if new_chart_type == 1:
                    # draw chart - incremental votes count by date

                    # key: vote day, type: timestamp, value, type: 3-element tuple of mn voting
                    votes_aggr = {}
                    mn_last_votes = {}
                    vote_mapper = {'YES': 0, 'NO': 1, 'ABSTAIN': 2}
                    dates = []
                    prev_vd = None
                    max_y = 1

                    for idx in range(len(self.votesModel.votes)-1, -1, -1):
                        v = self.votesModel.votes[idx]
                        ts = int(datetime.datetime(v[0].year, v[0].month, v[0].day, 0, 0, 0).timestamp()) * 1000
                        vd = votes_aggr.get(ts)
                        mn = v[2]
                        vote = v[1]
                        if not vd:
                            # there is no entry for this date yet - add and copy vote counts from the previous
                            # one if any
                            if prev_vd is not None:
                                vd = [prev_vd[0], prev_vd[1], prev_vd[2]]
                            else:
                                vd = [0, 0, 0]  # yes, no, abstain
                            prev_vd = vd
                            votes_aggr[ts] = vd
                            dates.append(ts)

                        last_mn_vote = mn_last_votes.get(mn)
                        if last_mn_vote != vote:
                            if last_mn_vote is not None:
                                # subtract votes count for last mn vote type (yes, no, abstain), because
                                # changing vote by the mn
                                vd[vote_mapper[last_mn_vote]] -= 1
                            vd[vote_mapper[vote]] += 1
                            mn_last_votes[mn] = vote  # save the last mn vote
                            max_y = max(max_y, vd[vote_mapper[vote]])

                    ser_abs_yes = QLineSeries()
                    ser_abs_yes.setName('Absolute Yes')
                    pen = QPen(QColor('#6699ff'))
                    pen.setWidth(2)
                    ser_abs_yes.setPen(pen)

                    ser_yes = QLineSeries()
                    ser_yes.setName('Yes')
                    pen = QPen(QCOLOR_YES)
                    pen.setWidth(2)
                    ser_yes.setPen(pen)

                    ser_no = QLineSeries()
                    ser_no.setName('No')
                    pen = QPen(QCOLOR_NO)
                    pen.setWidth(2)
                    ser_no.setPen(pen)

                    ser_abstain = QLineSeries()
                    ser_abstain.setName('Abstain')
                    pen = QPen(QCOLOR_ABSTAIN)
                    pen.setWidth(2)
                    ser_abstain.setPen(pen)

                    max_absolute_yes = 1
                    min_absolute_yes = 0
                    for ts in dates:
                        vd = votes_aggr[ts]
                        sum_yes = vd[0]
                        sum_no = vd[1]
                        sum_abstain = vd[2]
                        ser_yes.append(ts, sum_yes)
                        ser_no.append(ts, sum_no)
                        ser_abstain.append(ts, sum_abstain)
                        absolute_yes = sum_yes - sum_no
                        max_absolute_yes = max(max_absolute_yes, absolute_yes)
                        min_absolute_yes = min(min_absolute_yes, absolute_yes)
                        ser_abs_yes.append(ts, absolute_yes)

                    self.vote_chart.addSeries(ser_abs_yes)
                    self.vote_chart.addSeries(ser_yes)
                    self.vote_chart.addSeries(ser_no)
                    self.vote_chart.addSeries(ser_abstain)

                    axisX = QDateTimeAxis()
                    axisX.setLabelsVisible(True)
                    axisX.setFormat("dd MMM")
                    self.vote_chart.addAxis(axisX, Qt.AlignBottom)
                    axisY = QValueAxis()
                    axisY.setLabelFormat('%d')
                    axisY.setLabelsVisible(True)

                    self.vote_chart.addAxis(axisY, Qt.AlignLeft)
                    ser_yes.attachAxis(axisX)
                    ser_yes.attachAxis(axisY)
                    ser_no.attachAxis(axisX)
                    ser_no.attachAxis(axisY)
                    ser_abstain.attachAxis(axisX)
                    ser_abstain.attachAxis(axisY)
                    ser_abs_yes.attachAxis(axisX)
                    ser_abs_yes.attachAxis(axisY)

                    try:
                        x_ticks = min(max(len(dates), 2), 10)
                        self.vote_chart.axisX().setTickCount(x_ticks)
                    except Exception as e:
                        raise

                    if len(dates) == 0:
                        min_date = datetime.datetime.now()
                        max_date = datetime.datetime.now()
                        max_date += datetime.timedelta(days=1)
                    elif len(dates) == 1:
                        min_date = datetime.datetime.fromtimestamp(dates[0] / 1000)
                        max_date = min_date
                        max_date += datetime.timedelta(days=1)
                    else:
                        min_date = datetime.datetime.fromtimestamp(dates[0] / 1000)
                        max_date = datetime.datetime.fromtimestamp(dates[len(dates)-1] / 1000)

                    self.vote_chart.axisX().setMin(min_date)
                    self.vote_chart.axisX().setMax(max_date)
                    self.vote_chart.axisY().setMin(min(0, min_absolute_yes))
                    max_y = max_y + int(max_y * 0.05)
                    self.vote_chart.axisY().setMax(max_y)

                elif new_chart_type == 2:
                    bs_abs_yes = QBarSet("Absolute Yes")
                    bs_abs_yes.setColor(QColor('#6699ff'))
                    bs_abs_yes.setLabelColor(QColor('#6699ff'))
                    bs_abs_yes.append(self.current_proposal.get_value('absolute_yes_count'))

                    bs_yes = QBarSet('Yes')
                    bs_yes.setColor(QCOLOR_YES)
                    bs_yes.setLabelColor(QCOLOR_YES)
                    bs_yes.append(self.current_proposal.get_value('yes_count'))

                    bs_no = QBarSet('No')
                    bs_no.setColor(QCOLOR_NO)
                    bs_no.setLabelColor(QCOLOR_NO)
                    bs_no.append(self.current_proposal.get_value('no_count'))

                    bs_abstain = QBarSet('Abstain')
                    bs_abstain.setColor(QCOLOR_ABSTAIN)
                    bs_abstain.setLabelColor(QCOLOR_ABSTAIN)
                    bs_abstain.append(self.current_proposal.get_value('abstain_count'))

                    ser = QBarSeries()
                    ser.setLabelsVisible(True)
                    ser.setLabelsPosition(3)  # LabelsOutsideEnd
                    ser.append(bs_abs_yes)
                    ser.append(bs_yes)
                    ser.append(bs_no)
                    ser.append(bs_abstain)
                    self.vote_chart.addSeries(ser)

                    if self.vote_chart.axisX() is None:
                        axisX = QBarCategoryAxis()
                        axisX.setLabelsVisible(False)
                        self.vote_chart.addAxis(axisX, Qt.AlignBottom)
                        self.vote_chart.setAxisX(axisX, ser)

                    if self.vote_chart.axisY() is None:
                        axisY = QValueAxis()
                        axisY.setLabelFormat('%d')
                        axisY.setLabelsVisible(True)
                        self.vote_chart.addAxis(axisY, Qt.AlignLeft)
                        self.vote_chart.setAxisX(axisY, ser)
                    else:
                        self.vote_chart.setAxisY(self.vote_chart.axisY(), ser)

                    self.vote_chart.axisY().setMin(min(0, self.current_proposal.get_value('absolute_yes_count')))
                    max_y = max(self.current_proposal.get_value('yes_count'),
                                self.current_proposal.get_value('no_count'),
                                self.current_proposal.get_value('abstain_count'),
                                self.current_proposal.get_value('absolute_yes_count'))
                    max_y = max_y + int(max_y * 0.15)  # space for label
                    self.vote_chart.axisY().setMax(max_y)

                elif new_chart_type == 3:
                    # chart of changing vote by masternodes by date

                    # dict of lists (key: timestamp) of how many vote-changes has been made within a specific date
                    votes_change_by_date = {}
                    vote_change_mapper = {
                        'No->Yes': 0,
                        'Abstain->Yes': 1,
                        'No->Abstain': 2,
                        'Yes->Abstain': 3,
                        'Yes->No': 4,
                        'Abstain->No': 5
                    }
                    vote_change_colors = {
                        0: '#47d147',
                        1: '#248f24',
                        2: '#ff9933',
                        3: '#e67300',
                        4: '#ff0000',
                        5: '#cc2900'
                    }
                    change_existence = [False] * 6
                    mn_last_votes = {}
                    dates = []
                    max_y = 0

                    for idx in range(len(self.votesModel.votes)-1, -1, -1):
                        v = self.votesModel.votes[idx]
                        ts = int(datetime.datetime(v[0].year, v[0].month, v[0].day, 0, 0, 0).timestamp()) * 1000
                        mn = v[2]
                        vote = v[1]

                        last_mn_vote = mn_last_votes.get(mn)
                        if last_mn_vote and last_mn_vote != vote:
                            vd = votes_change_by_date.get(ts)
                            if not vd:
                                # there is no entry for this date yet
                                vd = [0] * 6
                                votes_change_by_date[ts] = vd
                                dates.append(ts)
                            change_type = last_mn_vote.capitalize() + '->' + vote.capitalize()
                            change_type_idx = vote_change_mapper[change_type]
                            vd[change_type_idx] += 1
                            change_existence[change_type_idx] = True
                            max_y = max(max_y, vd[change_type_idx])
                        mn_last_votes[mn] = vote  # save the last mn vote

                    ser = QBarSeries()
                    ser.setLabelsVisible(True)
                    ser.setLabelsPosition(3)  # LabelsOutsideEnd

                    for change_type_idx in list(range(6)):
                        if change_existence[change_type_idx]:  # NO->YES
                            # get the string representation of the mn vote change
                            change_label = '?'
                            for key, value in vote_change_mapper.items():
                                if value == change_type_idx:
                                    change_label = key

                            bs = QBarSet(change_label)
                            bs.setColor(QColor(vote_change_colors[change_type_idx]))
                            bs.setLabelColor(QColor(vote_change_colors[change_type_idx]))
                            for date in dates:
                                bs.append(votes_change_by_date[date][change_type_idx] )
                            ser.append(bs)

                    self.vote_chart.addSeries(ser)

                    if self.vote_chart.axisX() is None:
                        axisX = QBarCategoryAxis()
                        self.vote_chart.addAxis(axisX, Qt.AlignBottom)
                    else:
                        axisX = self.vote_chart.axisX()

                    dates_str = []
                    for date in dates:
                        d = QDateTime(datetime.datetime.fromtimestamp(date/1000))
                        ds = QLocale.toString(self.app_config.get_default_locale(), d, 'dd MMM')
                        dates_str.append(ds)
                    axisX.clear()
                    axisX.append(dates_str)
                    self.vote_chart.setAxisX(axisX, ser)
                    axisX.setLabelsVisible(True)

                    if self.vote_chart.axisY() is None:
                        axisY = QValueAxis()
                        axisY.setLabelFormat('%d')
                        axisY.setLabelsVisible(True)
                        self.vote_chart.addAxis(axisY, Qt.AlignLeft)
                        self.vote_chart.setAxisY(axisY, ser)
                    else:
                        self.vote_chart.setAxisY(self.vote_chart.axisY(), ser)
                    max_y = max_y + 1 + int(max_y * 0.15)  # space for label
                    self.vote_chart.axisY().setMax(max_y)

                self.last_chart_type = new_chart_type

        except Exception:
            logging.exception('Exception while drawing vote chart.')

    def refresh_preview_panel_thread(self, ctrl):
        """Thread reloading additional proposal data after changing current proposal. This is done in the background
        to avoid blocking the UI when user jumps quickly between proposals - the work involves reading voting data
        from the cache database, so it's relatively time-consuming operation.
        """
        last_proposal_read = None
        last_chart_type = None

        def apply_grid_data():
            self.votesModel.refresh_view()
            self.draw_chart()

        while not self.finishing:
            try:
                if last_proposal_read != self.current_proposal:
                    self.votesModel.read_votes()
                    last_proposal_read = self.current_proposal
                    last_chart_type = self.current_chart_type
                    WndUtils.call_in_main_thread(apply_grid_data)
                elif last_chart_type != self.current_chart_type:
                    last_chart_type = self.current_chart_type
                    WndUtils.call_in_main_thread(self.draw_chart)

                wr = self.refresh_details_event.wait(2)
                if self.refresh_details_event.is_set():
                    self.refresh_details_event.clear()
            except Exception:
                logging.exception('Exception while refreshing preview panel')

    def on_chart_type_change(self):
        if self.rbVotesChartIncremental.isChecked():
            self.current_chart_type = 1
        elif self.rbVotesChartFinal.isChecked():
            self.current_chart_type = 2
        elif self.rbVotesChartChanges.isChecked():
            self.current_chart_type = 3
        else:
            self.current_chart_type = -1
        self.refresh_details_event.set()

    @pyqtSlot(bool)
    def on_rbVotesChartIncremental_toggled(self, checked):
        self.on_chart_type_change()

    @pyqtSlot(bool)
    def on_rbVotesChartFinal_toggled(self, checked):
        self.on_chart_type_change()

    @pyqtSlot(bool)
    def on_rbVotesChartChanges_toggled(self, checked):
        self.on_chart_type_change()

    def apply_votes_filter(self):
        changed_chb = self.votesProxyModel.set_only_my_votes(self.chbOnlyMyVotes.isChecked())
        changed_text = self.votesProxyModel.set_filter_text(self.edtVotesViewFilter.text())
        if changed_chb or changed_text:
            self.votesProxyModel.invalidateFilter()
        self.btnApplyVotesViewFilter.setEnabled(False)

    @pyqtSlot()
    def on_btnVotesRefresh_clicked(self):
        def enable_button():
            self.btnVotesRefresh.setEnabled(True)
            self.btnProposalsRefresh.setEnabled(True)

        if self.current_proposal:
            self.btnVotesRefresh.setEnabled(False)
            self.btnProposalsRefresh.setEnabled(False)
            self.runInThread(self.read_voting_from_network_thread, (True, [self.current_proposal]),
                             on_thread_finish=enable_button)

    @pyqtSlot(int)
    def on_chbOnlyMyVotes_stateChanged(self, state):
        self.apply_votes_filter()

    @pyqtSlot(str)
    def on_edtVotesViewFilter_textEdited(self, text):
        self.btnApplyVotesViewFilter.setEnabled(True)

    def on_edtVotesViewFilter_returnPressed(self):
        self.apply_votes_filter()

    def on_btnApplyVotesViewFilter_clicked(self):
        self.apply_votes_filter()

    @pyqtSlot()
    def on_btnVoteYesForAll_clicked(self):
        if not self.main_wnd.config.confirm_when_voting or \
            self.queryDlg('Vote YES for all masternodes?',
                          buttons=QMessageBox.Yes | QMessageBox.Cancel,
                          default_button=QMessageBox.Yes, icon=QMessageBox.Information) == QMessageBox.Yes:
            vl = []
            for mn_info in self.users_masternodes:
                vl.append((mn_info, VOTE_CODE_YES))
            if vl:
                self.vote(vl)

    @pyqtSlot()
    def on_btnVoteNoForAll_clicked(self):
        if not self.main_wnd.config.confirm_when_voting or \
            self.queryDlg('Vote NO for all masternodes?',
                          buttons=QMessageBox.Yes | QMessageBox.Cancel,
                          default_button=QMessageBox.Yes, icon=QMessageBox.Information) == QMessageBox.Yes:
            vl = []
            for mn_info in self.users_masternodes:
                vl.append((mn_info, VOTE_CODE_NO))
            if vl:
                self.vote(vl)

    @pyqtSlot()
    def on_btnVoteAbstainForAll_clicked(self):
        if not self.main_wnd.config.confirm_when_voting or \
            self.queryDlg('Vote ABSTAIN for all masternodes?',
                          buttons=QMessageBox.Yes | QMessageBox.Cancel,
                          default_button=QMessageBox.Yes, icon=QMessageBox.Information) == QMessageBox.Yes:
            vl = []
            for mn_info in self.users_masternodes:
                vl.append((mn_info, VOTE_CODE_ABSTAIN))
            if vl:
                self.vote(vl)

    def on_btnVoteYes_clicked(self, mn_info):
        if not self.main_wnd.config.confirm_when_voting or \
           self.queryDlg('Vote YES for masternode %s?' % mn_info.masternode_config.name,
                         buttons=QMessageBox.Yes | QMessageBox.Cancel,
                         default_button=QMessageBox.Yes, icon=QMessageBox.Information) == QMessageBox.Yes:
            self.vote([(mn_info, VOTE_CODE_YES)])

    def on_btnVoteNo_clicked(self, mn_info):
        if not self.main_wnd.config.confirm_when_voting or \
           self.queryDlg('Vote NO for masternode %s?' % mn_info.masternode_config.name,
                         buttons=QMessageBox.Yes | QMessageBox.Cancel,
                         default_button=QMessageBox.Yes, icon=QMessageBox.Information) == QMessageBox.Yes:
            self.vote([(mn_info, VOTE_CODE_NO)])

    def on_btnVoteAbstain_clicked(self, mn_info):
        if not self.main_wnd.config.confirm_when_voting or \
           self.queryDlg('Vote ABSTAIN for masternode %s?' % mn_info.masternode_config.name,
                         buttons=QMessageBox.Yes | QMessageBox.Cancel,
                         default_button=QMessageBox.Yes, icon=QMessageBox.Information) == QMessageBox.Yes:
            self.vote([(mn_info, VOTE_CODE_ABSTAIN)])

    def vote(self, vote_list):
        """ Process votes for currently focused proposal. """

        if self.current_proposal:
            if not self.crownd_intf.open():
                self.errorMsg('Crown daemon not connected')
            else:
                prop_hash = self.current_proposal.get_value('hash')

                step = 1
                successful_votes = 0
                unsuccessful_votes = 0
                vote_sig = ''
                serialize_for_sig = ''

                for vote_idx, v in enumerate(vote_list):
                    mn_info = None
                    sig_time = int(time.time())
                    try:
                        mn_info = v[0]
                        vote_code = v[1]
                        vote = {VOTE_CODE_YES: 'yes', VOTE_CODE_NO: 'no', VOTE_CODE_ABSTAIN: 'abstain'}[vote_code]

                        if self.main_wnd.config.add_random_offset_to_vote_time:
                            sig_time += random.randint(-1800, 1800)

                        serialize_for_sig = mn_info.masternode.ident + '|' + \
                                            prop_hash + '|' + \
                                            '1' + '|' + \
                                            vote_code + '|' + \
                                            str(sig_time)

                        step = 2
                        vote_sig = crown_utils.ecdsa_sign(serialize_for_sig, mn_info.masternode_config.privateKey)

                        step =3
                        v_res = self.crownd_intf.voteraw(
                            masternode_tx_hash=mn_info.masternode_config.collateralTx,
                            masternode_tx_index=int(mn_info.masternode_config.collateralTxIndex),
                            governance_hash=prop_hash,
                            vote_signal='funding',
                            vote=vote,
                            sig_time=sig_time,
                            vote_sig=vote_sig)

                        if v_res == 'Voted successfully':
                            self.current_proposal.apply_vote(mn_ident=mn_info.masternode.ident,
                                                             vote_timestamp=datetime.datetime.fromtimestamp(sig_time),
                                                             vote_result=vote.upper())
                            successful_votes += 1
                        else:
                            self.warnMsg(v_res)
                            unsuccessful_votes += 1

                    except Exception as e:
                        if step == 1:
                            msg = "Error for masternode %s: %s " %  (mn_info.masternode_config.name, str(e))
                            logging.exception(msg)
                        elif step == 2:
                            msg = "Error while signing voting message with masternode's %s private key." % \
                                  mn_info.masternode_config.name
                            logging.exception(msg)
                        else:
                            logging.error(str(e))
                            msg = "Error while broadcasting vote message for masternode %s: %s" % \
                                  (mn_info.masternode_config.name, str(e))
                            # write some info to the log file for analysis in case of problems
                            logging.info('masternode_priv_key: %s' % str(mn_info.masternode_config.privateKey))
                            logging.info('masternode_tx_hash: %s' % str(mn_info.masternode_config.collateralTx))
                            logging.info('masternode_tx_index: %s' % str(mn_info.masternode_config.collateralTxIndex))
                            logging.info('governance_hash: %s' % prop_hash)
                            logging.info('vote_sig: %s' % vote_sig)
                            logging.info('sig_time: %s' % str(sig_time))
                            t = time.time()
                            logging.info('cur_time: timestamp: %s, timestr local: %s, timestr UTC: %s' %
                                         (str(t), str(datetime.datetime.fromtimestamp(t)),
                                          str(datetime.datetime.utcfromtimestamp(t))))
                            logging.info('serialize_for_sig: %s' % str(serialize_for_sig))

                        unsuccessful_votes += 1

                        if vote_idx < len(vote_list) - 1:
                            if self.queryDlg(msg, buttons=QMessageBox.Ok | QMessageBox.Abort,
                                             default_button=QMessageBox.Cancel, icon=QMessageBox.Critical) == \
                               QMessageBox.Abort:
                                break
                        else:
                            self.errorMsg(msg)

                if successful_votes > 0:
                    self.refresh_vote_tab()
                    try:
                        # move back the 'last read' time to force reading vote data from the network
                        # next time and save it to the db
                        cur = self.db_intf.get_cursor()
                        cur.execute("UPDATE PROPOSALS set cmt_voting_last_read_time=? where id=?",
                                    (int(time.time()) - VOTING_RELOAD_TIME, self.current_proposal.db_id))
                    except Exception:
                        logging.exception('Exception while saving configuration data.')
                    finally:
                        self.db_intf.commit()
                        self.db_intf.release_cursor()

                if unsuccessful_votes == 0 and successful_votes > 0:
                    self.infoMsg('Voted successfully')

    @pyqtSlot()
    def on_btnProposalsSaveToCSV_clicked(self):
        """ Save the proposals' data to a CSV file. """
        file_name = self.save_file_query('Enter name of the CSV file to save',
                                         filter="All Files (*);;CSV files (*.csv)",
                                         initial_filter="CSV files (*.csv)")
        if file_name:
            try:
                with codecs.open(file_name, 'w', 'utf-8') as f_ptr:
                    elems = [col.caption for col in self.columns]
                    self.write_csv_row(f_ptr, elems)
                    for prop in sorted(self.proposals, key = lambda p: p.initial_order_no):
                        elems = [prop.get_value(col.name) for col in self.columns]
                        self.write_csv_row(f_ptr, elems)
                self.infoMsg('Proposals data successfully saved.')
            except Exception as e:
                logging.exception("Exception saving proposals' data to a file.")
                self.errorMsg('Couldn\'t save a CSV file due to the following error: ' + str(e))

    @pyqtSlot()
    def on_btnVotesSaveToCSV_clicked(self):
        """ Save the voting data of the current proposal to a CSV file. """
        if self.votesModel and self.current_proposal:
            file_name = self.save_file_query('Enter name of the CSV file to save',
                                             filter="All Files (*);;CSV files (*.csv)",
                                             initial_filter="CSV files (*.csv)")
            if file_name:
                try:
                    with codecs.open(file_name, 'w', 'utf-8') as f_ptr:
                        elems = ['Vote date/time', 'Vote', 'Masternode', 'User\'s masternode']
                        self.write_csv_row(f_ptr, elems)

                        for v in self.votesModel.votes:
                            self.write_csv_row(f_ptr, v)

                    self.infoMsg('Votes of the proposal "%s" successfully saved.' %
                                 self.current_proposal.get_value('name'))
                except Exception as e:
                    logging.exception("Exception saving proposals votes to a file.")
                    self.errorMsg('Couldn\'t save a CSV file due to the following error: ' + str(e))

    @pyqtSlot()
    def on_btnProposalsColumns_clicked(self):
        try:
            cols = []

            cols_before = sorted(self.columns, key=lambda x: x.display_order_no \
                                 if x.display_order_no is not None else 100)
            for col in cols_before:
                cols.append([col.caption, col.visible, col])

            ui = ColumnsConfigDlg(self, columns=cols)
            ret = ui.exec_()
            if ret > 0:
                head = self.propsView.horizontalHeader()
                col_index = 0
                order_changed = False
                for _, visible, col in cols:
                    old_index = cols_before.index(col)
                    if old_index != col_index:
                        head.swapSections(old_index, col_index)
                        # head.moveSection(old_index, col_index)
                        cols_before[old_index], cols_before[col_index] = cols_before[col_index], cols_before[old_index]
                        order_changed = True

                    logical_index = self.columns.index(col)
                    is_visible_old = not head.isSectionHidden(logical_index)
                    if is_visible_old != visible:
                        if not is_visible_old:
                            head.showSection(logical_index)
                        else:
                            head.hideSection(logical_index)
                        col.visible = visible

                    col_index += 1

                if order_changed:
                    for col_idx, col in enumerate(cols_before):
                        col.display_order_no = col_idx
        except Exception as e:
            logging.exception('Exception while configuring proposals\' columns')
            self.errorMsg(str(e))

    @pyqtSlot(int, int, int)
    def on_propsViewColumnMoved(self, logicalIndex, oldVisualIndex, bewVisualIndex):
        """ Update columns display order after column moving with mouse. """
        hdr = self.propsView.horizontalHeader()
        for col_idx, col in enumerate(self.columns):
            vis_index = hdr.visualIndex(col_idx)
            col.display_order_no = vis_index

    @pyqtSlot(str)
    def on_edtProposalFilter_textEdited(self, text):
        self.proxyModel.set_filter_text(text)
        self.proxyModel.invalidateFilter()


class ProposalFilterProxyModel(QSortFilterProxyModel):
    """ Proxy for proposals sorting. """

    def __init__(self, parent, proposals, columns):
        super().__init__(parent)
        self.columns = columns
        self.proposals = proposals
        self.filter_text = ''
        self.filter_columns = []

    def set_filter_text(self, text):
        self.filter_text = text

    def add_filter_column(self, idx):
        if idx >= 0 and idx not in self.filter_columns:
            self.filter_columns.append(idx)

    def lessThan(self, left, right):
        """ Custom comparison method: for comparing data from columns which have custom widget controls
          associated with it, such as hyperlink columns (name, url). Such "widget" columns
          can't be compared with the use of default method, because data to be compared is hidden
          behind widget.
        """
        col_index = left.column()
        col = self.columns[col_index]
        left_row_index = left.row()

        if 0 <= left_row_index < len(self.proposals):
            left_prop = self.proposals[left_row_index]
            right_row_index = right.row()

            if 0 <= right_row_index < len(self.proposals):
                right_prop = self.proposals[right_row_index]
                left_value = left_prop.get_value(col.name)
                right_value = right_prop.get_value(col.name)

                if col.name in ('name', 'url', 'title'):
                    # compare hyperlink columns
                    if not left_value:
                        left_value = ""
                    if not right_value:
                        right_value = ""
                    left_value = left_value.lower()
                    right_value = right_value.lower()
                    return left_value < right_value

                elif col.name == 'voting_status_caption':
                    # compare status column by its status code, not status text
                    left_value = left_prop.voting_status
                    right_value = right_prop.voting_status

                    if left_value == right_value:
                        # for even statuses, order by votes number
                        diff = right_prop.get_value('absolute_yes_count') < left_prop.get_value('absolute_yes_count')
                    else:
                        diff = left_value < right_value
                    return diff

                elif col.name == 'no':
                    left_voting_in_progress = left_prop.voting_in_progress
                    right_voting_in_progress = right_prop.voting_in_progress

                    if left_voting_in_progress == right_voting_in_progress:
                        # statuses 1, 2: voting in progress
                        # for even statuses, order by creation time (newest first)
                        diff = right_prop.get_value('creation_time') < left_prop.get_value('creation_time')
                    else:
                        diff = left_prop.voting_status < right_prop.voting_status
                    return diff

                elif col.name in ('payment_start', 'payment_end', 'creation_time'):
                    diff = right_value < left_value
                    return diff

        return super().lessThan(left, right)

    def filterAcceptsRow(self, source_row, source_parent):
        will_show = True
        try:
            if self.filter_text:
                will_show = False
                for col_idx in self.filter_columns:
                    if source_row >=0 and source_row < len(self.proposals):
                        data = str(self.proposals[source_row].get_value(col_idx))
                        if data and data.lower().find(self.filter_text) >= 0:
                            will_show = True
        except Exception:
            logging.exception('Exception wile filtering votes')
        return will_show


class ProposalsModel(QAbstractTableModel):
    def __init__(self, parent, columns, proposals):
        QAbstractTableModel.__init__(self, parent)
        self.parent = parent
        self.columns = columns
        self.proposals = proposals

    def columnCount(self, parent=None, *args, **kwargs):
        return len(self.columns)

    def rowCount(self, parent=None, *args, **kwargs):
        return len(self.proposals)

    def headerData(self, section, orientation, role=None):
        if role != 0:
            return QVariant()
        if orientation == 0x1:
            if section < len(self.columns):
                return self.columns[section].caption
            return ''
        else:
            return '  '

    def setData(self, row, col, role=None):
        index = self.index(row, col)
        index = self.parent.proxyModel.mapFromSource(index)

        self.dataChanged.emit(index, index)
        return True

    def flags(self, index):
        ret = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        return ret

    def data(self, index, role=None):
        if index.isValid():
            col_idx = index.column()
            row_idx = index.row()
            if row_idx < len(self.proposals) and col_idx < len(self.columns):
                prop = self.proposals[row_idx]
                col = self.columns[col_idx]
                if prop:
                    if role == Qt.DisplayRole:
                        if col.name in ('payment_start', 'payment_end', 'creation_time'):
                            value = prop.get_value(col.name)
                            if value is not None:
                                return self.parent.main_wnd.config.to_string(value.date())
                            else:
                                return ''
                        elif col.name in ('active'):
                            return 'Yes' if prop.get_value(col.name) is True else 'No'
                        elif col.name in ('title', 'url', 'name'):
                            col_idx = self.parent.column_index_by_name(col.name)
                            src_index = self.index(row_idx, col_idx)
                            index = self.parent.proxyModel.mapFromSource(src_index)
                            if index:
                                if not self.parent.propsView.indexWidget(index):
                                    value = prop.get_value(col.name)
                                    prop.title_col_widget = QtWidgets.QLabel(self.parent.propsView)
                                    url = prop.get_value('url')
                                    prop.title_col_widget.setText('<a href="%s">%s</a>' % (url, value))
                                    prop.title_col_widget.setOpenExternalLinks(True)
                                    self.parent.propsView.setIndexWidget(index, prop.title_col_widget)
                        else:
                            value = prop.get_value(col.name)
                            if isinstance(value, datetime.datetime):
                                return str(value)
                            return value
                        if col.name == 'no':
                            return str(prop.initial_order_no + 1)

                    elif role == Qt.ForegroundRole:
                        if col.name == 'voting_status_caption':
                            if prop.voting_status == 1:
                                return QtGui.QColor('white')
                            elif prop.voting_status == 2:
                                return QtGui.QColor('white')
                            elif prop.voting_status == 3:
                                return QCOLOR_YES
                            elif prop.voting_status == 4:
                                return QCOLOR_NO
                        elif col.column_for_vote:
                            value = prop.get_value(col.name)
                            if value == 'YES':
                                return QCOLOR_YES
                            elif value == 'ABSTAIN':
                                return QCOLOR_ABSTAIN
                            elif value == 'NO':
                                return QCOLOR_NO

                    elif role == Qt.BackgroundRole:
                        if col.name == 'voting_status_caption':
                            if prop.voting_status == 1:
                                return QCOLOR_YES
                            elif prop.voting_status == 2:
                                return QCOLOR_ABSTAIN

                    elif role == Qt.TextAlignmentRole:
                        if col.name in ('monthly_payment', 'total_payment', 'absolute_yes_count',
                                        'yes_count', 'no_count', 'abstain_count', 'total_payment_count', 
                                        'remaining_payment_count'):
                            return Qt.AlignRight

                    elif role == Qt.FontRole:
                        if col.column_for_vote:
                            font = QtGui.QFont()
                            font.setBold(True)
                            return font

        return QVariant()


class VotesFilterProxyModel(QSortFilterProxyModel):
    """ Proxy for votes sorting/filtering. """

    def __init__(self, parent):
        super().__init__(parent)
        self.only_my_votes = False
        self.filter_text = ''

    def set_only_my_votes(self, only_my_votes):
        if only_my_votes != self.only_my_votes:
            self.only_my_votes = only_my_votes
            return True
        else:
            return False

    def set_filter_text(self, filter_text):
        if self.filter_text != filter_text:
            self.filter_text = filter_text.lower()
            return True
        else:
            return False

    def filterAcceptsRow(self, source_row, source_parent):
        will_show = True
        try:
            if self.only_my_votes:
                index = self.sourceModel().index(source_row, 3, source_parent)
                if index:
                    data = self.sourceModel().data(index, Qt.DisplayRole)
                    if not data:
                        will_show = False

            if will_show and self.filter_text:
                # if none of remaining columns contain self.filter_text do not show record
                will_show = False
                for col_idx in (0, 1, 2, 3):
                    index = self.sourceModel().index(source_row, col_idx, source_parent)
                    if index:
                        data = str(self.sourceModel().data(index, Qt.DisplayRole))
                        if data and data.lower().find(self.filter_text) >= 0:
                            will_show = True
                            break
        except Exception:
            logging.exception('Exception wile filtering votes')
        return will_show


class VotesModel(QAbstractTableModel):
    def __init__(self, proposals_dlg, masternodes, masternodes_by_db_id, users_masternodes_by_ident, db_intf):
        QAbstractTableModel.__init__(self, proposals_dlg)
        self.proposals_dlg = proposals_dlg
        self.masternodes = masternodes
        self.masternodes_by_db_id = masternodes_by_db_id
        self.db_intf = db_intf
        self.users_masternodes_by_ident = users_masternodes_by_ident
        self.only_my_votes = False
        self.proposal = None
        self.votes = []  # list of tuples: voting time (datetime), vote, masternode_label, users_masternode_name
        self.columns = ['Vote timestamp', 'Vote', 'Masternode', "User's Masternode"]

    def columnCount(self, parent=None, *args, **kwargs):
        return 4

    def rowCount(self, parent=None, *args, **kwargs):
        return len(self.votes)

    def headerData(self, section, orientation, role=None):
        if role != 0:
            return QVariant()
        if orientation == 0x1:
            return self.columns[section] if 0 <= section < len(self.columns) else ''
        else:
            return str(section + 1)

    def flags(self, index):
        ret = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        return ret

    def data(self, index, role=None):
        if index.isValid():
            col_idx = index.column()
            row_idx = index.row()
            if row_idx < len(self.votes) and col_idx < len(self.columns):
                vote = self.votes[row_idx]
                if vote:
                    if role == Qt.DisplayRole:
                        if col_idx == 0:    # vote timestamp
                            value = vote[0]
                            if value is not None:
                                return self.proposals_dlg.main_wnd.config.to_string(value)
                            else:
                                return ''
                        elif col_idx == 1:  # YES/NO/ABSTAIN
                            return vote[1]
                        elif col_idx == 2:  # voting masternode label
                            return vote[2]
                        elif col_idx == 3:  # voting masternode config-name if exists in the user's configuration
                            return vote[3]
                    elif role == Qt.ForegroundRole:
                        if col_idx == 1:
                            if vote[1] == 'YES':
                                return QCOLOR_YES
                            elif vote[1] == 'NO':
                                return QCOLOR_NO
                            elif vote[1] == 'ABSTAIN':
                                return QCOLOR_ABSTAIN
                    elif role == Qt.FontRole:
                        if col_idx == 1:
                            font = QtGui.QFont()
                            font.setBold(True)
                            return font

        return QVariant()

    def read_votes(self):
        try:
            self.votes.clear()
            tm_begin = time.time()
            cur = self.db_intf.get_cursor()
            if self.proposal:
                logging.debug('Get votes fot proposal id: ' + str(self.proposal.db_id))
                cur.execute("SELECT voting_time, voting_result, masternode_ident, m.ip "
                            "FROM VOTING_RESULTS v "
                            "LEFT OUTER JOIN MASTERNODES m on m.ident = v.masternode_ident "
                            "WHERE proposal_id=? order by voting_time desc", (self.proposal.db_id,))

                for row in cur.fetchall():
                    if self.proposals_dlg.finishing:
                        raise CloseDialogException
                    users_mn_name = ''
                    mn_label = row[3]
                    if not mn_label:
                        mn_label = row[2]

                    # check if this masternode is in the user's configuration
                    users_mn = self.users_masternodes_by_ident.get(row[2])
                    if users_mn:
                        users_mn_name = users_mn.masternode_config.name

                    self.votes.append((datetime.datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S'),
                                       row[1], mn_label, users_mn_name))
                logging.debug('Reading votes time from DB: %s' % str(time.time() - tm_begin))

        except CloseDialogException:
            logging.info('Closing the dialog.')

        except Exception as e:
            logging.exception('SQLite error')

        finally:
            self.db_intf.release_cursor()

    def set_proposal(self, proposal):
        self.proposal = proposal

    def refresh_view(self):
        self.beginResetModel()
        self.endResetModel()

    def finish(self):
        pass

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Author: Bertrand256
# Created on: 2018-07

from typing import Tuple, List, Optional, Dict
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import QAbstractTableModel, QVariant, Qt, pyqtSlot, QStringListModel, QItemSelectionModel, \
    QItemSelection, QSortFilterProxyModel
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QDialog, QTableView, QHeaderView, QMessageBox, QSplitter, QVBoxLayout, QPushButton, \
    QItemDelegate, QLineEdit, QCompleter, QInputDialog, QLayout
import app_utils
from ext_item_model import TableModelColumn, ExtSortFilterTableModel


class TransactionsModel(ExtSortFilterTableModel):
    def __init__(self, parent):
        ExtSortFilterTableModel.__init__(self, parent, [
            TableModelColumn('amount', 'Amount', True, 100),
            TableModelColumn('date', 'Date', True, 100),
            TableModelColumn('height', 'Height', False, 100),
            TableModelColumn('senders', 'Sender', True, 100),
            TableModelColumn('receiver', 'Receiver', True, 100),
            TableModelColumn('txid', 'TX ID', False, 100),
            TableModelColumn('tx_index', 'TX index', False, 100),
            TableModelColumn('coinbase', 'Coinbase TX', False, 100),
            TableModelColumn('comment', 'Comment', True, 100)
        ], False, True)
        self.accounts: List[Bip44AccountType] = []
        self.__data_modified = False
        self.show_zero_balance_addresses = False
        self.set_attr_protection()

        QAbstractTableModel.__init__(self, parent)
        self.columns = [TableModelColumn('amount', 'Amount', True, 100),
                        TableModelColumn('date', 'Date', True, 100),
                        TableModelColumn('height', 'Height', False, 100),
                        TableModelColumn('senders', 'Sender', True, 100),
                        TableModelColumn('receiver', 'Receiver', True, 100),
                        TableModelColumn('txid', 'TX ID', False, 100),
                        TableModelColumn('tx_index', 'TX index', False, 100),
                        TableModelColumn('coinbase', 'Coinbase TX', False, 100),
                        TableModelColumn('comment', 'Comment', True, 100)
                        ]
        self._col_by_name = {}
        for col in self.columns:
            self._col_by_name[col.name] = col
        self.transactions = []

    def columnByName(self, col_name: str):
        col = self._col_by_name.get(col_name, None)
        if not col:
            raise NameError(f'Column {col_name} not found')
        return col

    def columnCount(self, parent=None, *args, **kwargs):
        return len(self.columns)

    def rowCount(self, parent=None, *args, **kwargs):
        return len(self.transactions)

    def headerData(self, section, orientation, role=None):
        if role != 0:
            return QVariant()
        if orientation == 0x1:
            if section < len(self.columns):
                return self.columns[section].caption
            return ''
        else:
            return "Row"

    def getDefaultColWidths(self):
        widths = [col.def_width for col in self.columns]
        return widths

    def flags(self, index):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable

    def data(self, index, role=None):
        if index.isValid():
            col = index.column()
            row = index.row()
            if row < len(self.transactions):
                utxo = self.transactions[row]
                if utxo:
                    if role in (Qt.DisplayRole, Qt.EditRole):
                        pass

                    elif role == Qt.ForegroundRole:
                        pass

                    elif role == Qt.BackgroundRole:
                        pass

                    elif role == Qt.TextAlignmentRole:
                        pass
        return QVariant()


class TransactionsProxyModel(QSortFilterProxyModel):
    """ Proxy for UTXO filtering/sorting. """

    def __init__(self, parent):
        super().__init__(parent)
        self.tx_model: TransactionsModel = None

    def filterAcceptsRow(self, source_row, source_parent):
        will_show = True
        return will_show

    def setSourceModel(self, source_model: TransactionsModel):
        self.tx_model = source_model
        super().setSourceModel(source_model)

    def lessThan(self, left, right):
        return super().lessThan(left, right)
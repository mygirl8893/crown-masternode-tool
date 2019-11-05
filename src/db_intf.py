#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Author: Bertrand256
# Created on: 2017-10
import sqlite3
import logging
import threading
import thread_utils


class DBCache(object):
    """Purpose: coordinating access to a database cache (sqlite) from multiple threads.

    Usage: call 'get_cursor' when before starting dealing with the cache db and 'release_cursor' after finishing.

    Note:
        1. get_cursor call locks the cache database to be used by the calling thread only
        2. subsequent get_cursor calls by the same thread require the same number of release_cursor calls;
           this is useful if you need multiple cursors to perform the required operations in one thread
    """

    def __init__(self, db_cache_file_name):
        self.db_cache_file_name = db_cache_file_name
        self.db_active = False
        self.lock = thread_utils.EnhRLock(stackinfo_skip_lines=1)
        self.depth = 0

        self.db_conn = None
        try:
            self.db_conn = sqlite3.connect(self.db_cache_file_name)
            self.create_structures()
            self.db_active = True
        except Exception as e:
            logging.exception('SQLite initialization error')
        finally:
            if self.db_conn:
                self.db_conn.close()
            self.db_conn = None

    def is_active(self):
        return self.db_active

    def get_cursor(self):
        if self.db_active:
            logging.debug('Trying to acquire db cache session')
            self.lock.acquire()
            self.depth += 1
            if self.db_conn is None:
                self.db_conn = sqlite3.connect(self.db_cache_file_name)
            logging.debug('Acquired db cache session (%d)' % self.depth)
            return self.db_conn.cursor()
        else:
            raise Exception('Database cache not active.')

    def release_cursor(self):
        if self.db_active:
            try:
                self.lock.acquire()
                if self.depth == 0:
                    raise Exception('Cursor not acquired by this thread.')
                self.depth -= 1
                if self.depth == 0:
                    self.db_conn.close()
                    self.db_conn = None
                self.lock.release()
                logging.debug('Released db cache session (%d)' % self.depth)
            finally:
                self.lock.release()
        else:
            logging.warning('Cannot release database session if db_active is False.')

    def commit(self):
        if self.db_active:
            try:
                self.lock.acquire()
                if self.depth == 0:
                    raise Exception('Cursor not acquired by this thread. Cannot commit.')
                self.db_conn.commit()
            finally:
                self.lock.release()
        else:
            logging.warning('Cannot commit if db_active is False.')

    def rollback(self):
        if self.db_active:
            try:
                self.lock.acquire()
                if self.depth == 0:
                    raise Exception('Cursor not acquired by this thread. Cannot rollback.')
                self.db_conn.rollback()
            finally:
                self.lock.release()
        else:
            logging.warning('Cannot commit if db_active is False.')

    def close(self):
        if self.depth > 0:
            logging.error('Database not closed yet. Depth: ' + str(self.depth))

    def create_structures(self):
        cur = self.db_conn.cursor()
        # create structures for masternodes data:
        cur.execute("CREATE TABLE IF NOT EXISTS MASTERNODES(id INTEGER PRIMARY KEY, ident TEXT, status TEXT,"
                    " protocol TEXT, payee TEXT, last_seen INTEGER, active_seconds INTEGER,"
                    " last_paid_time INTEGER, last_paid_block INTEGER, ip TEXT,"
                    " cmt_active INTEGER, cmt_create_time TEXT, cmt_deactivation_time TEXT)")
        cur.execute("CREATE INDEX IF NOT EXISTS IDX_MASTERNODES_CMT_ACTIVE ON MASTERNODES(cmt_active)")
        cur.execute("CREATE INDEX IF NOT EXISTS IDX_MASTERNODES_IDENT ON MASTERNODES(ident)")

        # create structures for proposals:
        cur.execute("CREATE TABLE IF NOT EXISTS PROPOSALS(id INTEGER PRIMARY KEY, name TEXT, url TEXT,"
                    " hash TEXT, fee_hash TEXT, payment_start TEXT, payment_end TEXT, block_start INTEGER, block_end INTEGER,"
                    " total_payment_count INTEGER, remaining_payment_count INTEGER, payment_address TEXT,"
                    " ratio REAL, yes_count INTEGER, no_count INTEGER, absolute_yes_count INTEGER,"
                    " abstain_count INTEGER, total_payment REAL, monthly_payment REAL, creation_time TEXT,"
                    " is_established INTEGER, is_valid INTEGER, is_valid_reason TEXT, f_valid INTEGER,"
                    " cmt_active INTEGER, cmt_create_time TEXT, cmt_deactivation_time TEXT,"
                    " cmt_voting_last_read_time INTEGER,"
                    " ext_attributes_loaded INTEGER, owner TEXT, title TEXT)")
        cur.execute("CREATE INDEX IF NOT EXISTS IDX_PROPOSALS_HASH ON PROPOSALS(hash)")
        cur.execute("CREATE TABLE IF NOT EXISTS VOTING_RESULTS(id INTEGER PRIMARY KEY, proposal_id INTEGER,"
                    " masternode_ident TEXT, voting_time TEXT, voting_result TEXT,"
                    "hash TEXT)")
#        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS IDX_VOTING_RESULTS_HASH ON VOTING_RESULTS(hash)")
        cur.execute("CREATE INDEX IF NOT EXISTS IDX_VOTING_RESULTS_1 ON VOTING_RESULTS(proposal_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS IDX_VOTING_RESULTS_2 ON VOTING_RESULTS(masternode_ident)")

        # Create table for storing live data for example last read time of proposals
        cur.execute("CREATE TABLE IF NOT EXISTS LIVE_CONFIG(symbol text PRIMARY KEY, value TEXT)")
        cur.execute("CREATE INDEX IF NOT EXISTS IDX_LIVE_CONFIG_SYMBOL ON LIVE_CONFIG(symbol)")

        # create structures for systemnodes data:
        cur.execute("CREATE TABLE IF NOT EXISTS SYSTEMNODES(id INTEGER PRIMARY KEY, ident TEXT, status TEXT,"
                    " protocol TEXT, payee TEXT, last_seen INTEGER, active_seconds INTEGER,"
                    " last_paid_time INTEGER, last_paid_block INTEGER, ip TEXT,"
                    " cmt_active INTEGER, cmt_create_time TEXT, cmt_deactivation_time TEXT)")
        cur.execute("CREATE INDEX IF NOT EXISTS IDX_SYSTEMNODES_CMT_ACTIVE ON SYSTEMNODES(cmt_active)")
        cur.execute("CREATE INDEX IF NOT EXISTS IDX_SYSTEMNODES_IDENT ON SYSTEMNODES(ident)")

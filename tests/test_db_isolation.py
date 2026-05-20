# -*- coding: utf-8 -*-

from app.db import BaseDB, SIMCardDB


class TestFreshDBIsolation:

    def test_first_test_writes_a_row(self, fresh_db):
        assert BaseDB._DB_FILE_NAME == ':memory:'

        SIMCardDB().update('/dev/ttyUSB0', '+8613500000001', True, True)

        assert len(SIMCardDB().list()) == 1

    def test_second_test_starts_with_empty_db(self, fresh_db):
        assert BaseDB._DB_FILE_NAME == ':memory:'
        assert SIMCardDB().list() == []

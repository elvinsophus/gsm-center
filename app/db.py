# -*- coding: utf-8 -*-

from threading import Semaphore, local
from time import time
from datetime import datetime
from functools import partial
from enum import Enum
from typing import Tuple, List, Mapping, Union, Optional
from .utils import (NamedObject, camel_to_underscore, compact_json_dumps,
                    remove_prefix, remove_suffix)
import sqlite3


_EMPTY = NamedObject('Empty')


class _BaseDBMeta(type):

    _name_to_class_ = {}

    def __new__(mcs, name, bases, dct):
        new_cls = partial(super().__new__, mcs, name, bases, dct)
        if not any(isinstance(b, mcs) for b in bases):
            return new_cls()
        if not dct.get('name'):
            dct['name'] = camel_to_underscore(
                remove_suffix(remove_prefix(name, '_'), 'DB'))
        if not dct.get('schema'):
            raise AttributeError(f'{name}.schema is not defined')
        name2cls = mcs._name_to_class_
        if name in name2cls:
            raise ValueError(f'table name {name!r} is already registered')
        name2cls[name] = cls = new_cls()
        return cls


class BaseDB(metaclass=_BaseDBMeta):

    name: str
    schema: str
    indices: Mapping[str, Tuple[str]] = None

    _DB_FILE_NAME = 'db.sqlite3'
    _db_connexion_lock = Semaphore()
    _threading_local = local()

    def __new__(cls, *args, **kwargs):
        if cls is BaseDB:
            raise RuntimeError(f'{cls!r} cannot be instantiated')
        return super().__new__(cls)

    def __init__(self):
        self._init_db()

    @staticmethod
    def _db():
        cls = BaseDB
        th_local = cls._threading_local
        if (db := getattr(th_local, 'db', None)) is None:
            with cls._db_connexion_lock:
                if (db := getattr(th_local, 'db', None)) is None:
                    th_local.db = db = sqlite3.connect(cls._DB_FILE_NAME)
        return db

    def _init_db(self):
        db = self._db()
        cursor = db.cursor()
        cursor.execute(f"""
            create table if not exists `{self.name}` ({self.schema})
        """)
        for idx, columns in (self.indices or {}).items():
            cursor.execute(f"""
                create index if not exists `{idx}` on `{self.name}` 
                ({", ".join(columns)})
            """)
        return db

    @classmethod
    def _execute(cls, sql: str, parameters: Union[list, tuple] = ()):
        with (_db := cls._db()):
            return _db.execute(sql, parameters)


class SIMCardDB(BaseDB):

    schema = '''
        `gsm_port` TEXT NOT NULL UNIQUE,
        `phone_number` TEXT NOT NULL UNIQUE,
        `call_enabled` INT NOT NULL,
        `sms_enabled` INT NOT NULL,
        `updated_at` INTEGER NOT NULL
    '''

    def list(self,
             since: datetime | int = None, *,
             call_enabled: bool = None,
             sms_enabled: bool = None) -> List[dict]:
        where = {}
        if call_enabled is not None:
            where["`call_enabled` = ?"] = int(call_enabled)
        if sms_enabled is not None:
            where["`sms_enabled` = ?"] = int(sms_enabled)
        if since:
            if isinstance(since, datetime):
                since = int(since.timestamp())
            where["`updated_at` >= ?"] = since
        where_clause = '' if not where else f"where {' and '.join(where)}"
        cursor = self._execute(
            f"select * from `{self.name}` {where_clause}",
            list(where.values())
        )
        cols = [c[0] for c in cursor.description]
        return [dict(zip(cols, r)) for r in cursor.fetchall()]

    def list_phone_numbers(self, since: datetime | int = None, *,
                           call_enabled: bool = None,
                           sms_enabled: bool = None) -> List[str]:
        return [
            r['phone_number']
            for r in self.list(
                since, call_enabled=call_enabled, sms_enabled=sms_enabled)
        ]

    def update(self, gsm_port: str, phone_number: str,
               call_enabled: bool, sms_enabled: bool):
        if self._execute(
            f"select * from `{self.name}` where `phone_number` = ?",
            [phone_number]
        ).fetchone():
            return bool(self._execute(
                f"update `{self.name}` set `phone_number` = ?, "
                f"`call_enabled` = ?, `sms_enabled` = ?, `updated_at` = ? "
                f"where `gsm_port` = ?",
                [phone_number, int(call_enabled), int(sms_enabled),
                 int(time()), gsm_port]
            ).rowcount)
        self._execute(
            f"insert into `{self.name}` "
            f"(`gsm_port`, `phone_number`, `call_enabled`, `sms_enabled`, "
            f"`updated_at`) "
            f"values (?, ?, ?, ?, ?)",
            [gsm_port, phone_number, int(call_enabled), int(sms_enabled),
             int(time())]
        )
        return True


class PendingSMSDB(BaseDB):

    schema = '''
        `id` INTEGER PRIMARY KEY AUTOINCREMENT,
        `created_at` INTEGER NOT NULL,
        `updated_at` INTEGER NOT NULL,
        `sender` TEXT NOT NULL,
        `recipient` TEXT NOT NULL,
        `content` TEXT NOT NULL,
        `sent_sms_id` INT,
        `status` TEXT NOT NULL,
        `extra` TEXT
    '''
    indices = {'sender_status_idx': {'sender', 'status'}}

    def list(self, sender: str, *,
             status: str | Enum = None, limit: int = 10) -> List[dict]:
        where = {'sender': sender}
        if status is not None:
            where['status'] = (status.name if isinstance(status, Enum)
                               else status)
        where_clause = (f"where {' and '.join(f'`{w}` = ?' for w in where)}"
                        if where else '')
        cursor = self._execute(
            f"select * from `{self.name}` {where_clause} "
            f"order by `id` limit ?",
            [*where.values(), limit]
        )
        cols = [c[0] for c in cursor.description]
        return [dict(zip(cols, r)) for r in cursor.fetchall()]

    def get(self, id_: int) -> Optional[dict]:
        cursor = self._execute(
            f"select * from `{self.name}` where `id` = ?",
            [id_]
        )
        if not (row := cursor.fetchone()):
            return None
        cols = [c[0] for c in cursor.description]
        return dict(zip(cols, row))

    def insert(self, sender: str, recipient: str, content: str,
               status: str | Enum) -> int:
        if isinstance(status, Enum):
            status = status.name
        return self._execute(
            f"insert into `{self.name}` "
            f"(`created_at`, `updated_at`, "
            f"`sender`, `recipient`, `content`, `status`) "
            f"values (?, ?, ?, ?, ?, ?)",
            [(t := int(time())), t, sender, recipient, content, status]
        ).lastrowid

    def process(self, id_: int, from_status: str | Enum, to_status: str | Enum,
                sent_sms_id: int = None, extra: dict = None) -> Optional[dict]:
        if isinstance(from_status, Enum):
            from_status = from_status.name
        if isinstance(to_status, Enum):
            to_status = to_status.name
        values = {'status': to_status, 'updated_at': int(time())}
        if sent_sms_id is not None:
            values['sent_sms_id'] = sent_sms_id
        if extra is not None:
            values['extra'] = compact_json_dumps(extra)
        if not self._execute(
            f"update `{self.name}` "
            f"set {', '.join(f'`{k}` = ?' for k in values)} "
            f"where `id` = ? and `status` = ?",
            [*values.values(), id_, from_status]
        ).rowcount:
            return None
        return self.get(id_)

    def delete(self, id_: int) -> bool:
        return bool(self._execute(
            f"delete from `{self.name}` where `id` = ?",
            [id_]
        ).rowcount)


class SmsDB(BaseDB):

    class SMSType(Enum):
        SENT = 0
        RECEIVED = 1

    schema = '''
        `id` INTEGER PRIMARY KEY AUTOINCREMENT,
        `created_at` INTEGER NOT NULL,
        `updated_at` INTEGER NOT NULL,
        `type` TEXT NOT NULL,
        `time` INTEGER,
        `own_number` TEXT NOT NULL,
        `other_number` TEXT NOT NULL,
        `content` TEXT NOT NULL,
        `delivery_report` TEXT,
        `status` TEXT NOT NULL,
        `extra` TEXT
    '''
    indices = {'numbers_idx': ('own_number', 'other_number', 'id ASC'),
               'type_numbers_idx': ('type', 'own_number', 'other_number',
                                    'id ASC'),
               'type_status_idx': {'type', 'status', 'id ASC'}}

    def list(self,
             type_: SMSType | str = None,
             own_number: str = '', *,
             other_number: str = '',
             status: str | Enum = None,
             limit: int = 10
             ) -> List[dict]:
        where = {}
        if type_ is not None:
            where['type'] = (type_.name if isinstance(type_, Enum) else type_)
        elif status is not None:
            raise ValueError(
                f'`status` is only available when `type_` is given')
        if own_number:
            where['own_number'] = own_number
        elif other_number:
            raise ValueError(
                f'`other_number` is only available when `own_number` is given')
        if other_number:
            where['other_number'] = other_number
        if status is not None:
            where['status'] = (status.name if isinstance(status, Enum)
                               else status)
        where_clause = (f"where {' and '.join(f'`{w}` = ?' for w in where)}"
                        if where else '')
        cursor = self._execute(
            f"select * from `{self.name}` {where_clause} "
            f"order by `id` desc limit ?",
            [*where.values(), limit]
        )
        cols = [c[0] for c in cursor.description]
        return [dict(zip(cols, r)) for r in cursor.fetchall()]

    def list_last_of_each(self, own_number: str = '', *, limit: int = 10):
        where = {}
        if own_number:
            where['own_number'] = own_number
        where_clause = (f"where {' and '.join(f'`{w}` = ?' for w in where)}"
                        if where else '')
        cursor = self._execute(
            f"select * from `{self.name}` inner join "
            f"(select max(`id`) max_id, count(*) id_count"
            f" from `{self.name}` {where_clause}"
            f" group by `own_number`, `other_number`) as sq "
            f"on `sq`.`max_id` = `id`"
            f"order by `id` desc limit ?",
            [*where.values(), limit]
        )
        cols = [c[0] for c in cursor.description]
        return [dict(zip(cols, r)) for r in cursor.fetchall()]

    def get(self, id_: int) -> Optional[dict]:
        cursor = self._execute(
            f"select * from `{self.name}` where `id` = ?",
            [id_]
        )
        if not (row := cursor.fetchone()):
            return None
        cols = [c[0] for c in cursor.description]
        return dict(zip(cols, row))

    def insert(self, type_: SMSType | str,
               own_number: str, other_number, content: str,
               status: str | Enum, time_: int = None) -> int:
        if isinstance(type_, Enum):
            type_ = type_.name
        if isinstance(status, Enum):
            status = status.name
        return self._execute(
            f"insert into `{self.name}` "
            f"(`created_at`, `updated_at`, "
            f"`type`, `own_number`, `other_number`, `content`, `time`, "
            f"`status`) "
            f"values (?, ?, ?, ?, ?, ?, ?, ?)",
            [(t := int(time())), t, type_, own_number, other_number, content,
             time_, status]
        ).lastrowid

    def update_status(self, id_: int, status: str | Enum, *,
                      delivery_report: dict = _EMPTY,
                      extra: dict = _EMPTY
                      ) -> bool:
        if isinstance(status, Enum):
            status = status.name
        values = {'status': status}
        if delivery_report is not _EMPTY:
            if delivery_report is not None:
                delivery_report = compact_json_dumps(delivery_report)
            values['delivery_report'] = delivery_report
        if extra is not _EMPTY:
            if extra is not None:
                extra = compact_json_dumps(extra)
            values['extra'] = extra
        values['updated_at'] = int(time())
        return bool(self._execute(
            f"update `{self.name}` "
            f"set {', '.join(f'`{k}` = ?' for k in values)} "
            f"where `id` = ?",
            [*values.values(), id_]
        ).rowcount)

    def batch_update_status(self, type_: SMSType | str,
                            status: str | Enum,
                            from_status: str | Enum = None) -> int:
        where = {'type': type_.name if isinstance(type_, Enum) else type_}
        if from_status is not None:
            where['status'] = (from_status.name
                               if isinstance(from_status, Enum)
                               else from_status)
        where_clause = (f"where {' and '.join(f'`{w}` = ?' for w in where)}"
                        if where else '')
        return self._execute(
            f"update `{self.name}` "
            f"set `status` = ?, `updated_at` = ? "
            f"{where_clause}",
            [(status.name if isinstance(status, Enum) else status,
              int(time()), *where.values())]
        ).rowcount

    def delete(self, id_: int) -> bool:
        return bool(self._execute(
            f"delete from `{self.name}` where `id` = ?",
            [id_]
        ).rowcount)

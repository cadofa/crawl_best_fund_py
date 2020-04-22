#/usr/bin/python
#coding=utf-8

import sqlite3

from global_list import ROOT_PATH

#db_path = '/opt/ctc/cephmon/db/ceph_info.db'
db_path = '../db/ceph_info.db'
#db_path = '/home/secure/ceph_deploy_auto/db/ceph_info.db'
#db_path = ROOT_PATH + 'db/ceph_info.db'

#
# --------------------------------------- cursor operation ---------------------------------------#
#
# conn:database句柄，必须先调用connect('database name')
# sql:sql语句，不包括where子句
# condition_pair:where子句条件，具体是一个列表，格式为('条件名=','条件的值')
# order:排序字段名称，不排序为None
# 调用完后必须调用cursor.close()和conn.close()
def db_get_cursor(conn, sql, condition_pair, order=None):
    if condition_pair:
        where, values = condition_pair
        sql += ' where %s' % where
        if order:
            sql = '%s order by %s' % (sql, order)
        cursor = conn.execute(sql, values)
    else:
        if order:
            sql = '%s order by %s' % (sql, order)
        cursor = conn.execute(sql)
    return cursor


def db_get_cursor_top_N(conn, sql, condition_pair, order=None, top=1):
    if condition_pair:
        where, values = condition_pair
        sql += ' where %s' % where
        if order:
            sql = '%s order by %s' % (sql, order)
        sql += ' limit ' + str(top)
        cursor = conn.execute(sql, values)
    else:
        if order:
            sql = '%s order by %s' % (sql, order)
        sql += ' limit ' + str(top)
        cursor = conn.execute(sql)
    return cursor


def db_cursor_get_count(conn, sql, condition_pair):
    cursor = db_get_cursor(conn, sql, condition_pair)
    if cursor:
        row = cursor.fetchone()
        if row:
            return row[0]
    return 0


def db_cursor_has_item(conn, sql, condition_pair):
    return db_cursor_get_count(conn, sql, condition_pair) > 0


def db_cursor_get_field_names(cursor):
    return (i[0] for i in cursor.description)


#
# --------------------------------------- table operation ---------------------------------------#
#
def db_table_get_cursor(conn, table, condition_pair, order=None, fields=None):
    return db_get_cursor(conn, 'select %s from %s' % (fields if fields else '*', table), condition_pair, order)


def db_table_get_count(conn, table, condition_pair):
    return db_cursor_get_count(conn, 'select count(*) from %s' % table, condition_pair)


def db_table_has_item(conn, table, condition_pair):
    return db_table_get_count(conn, table, condition_pair) > 0


def db_table_get_field_names(conn, table):
    return db_cursor_get_field_names(conn.execute('select * from %s where 1<>1' % table))


def db_has_table(conn, table):
    return db_table_has_item(conn, 'sqlite_master', ('name=?', [table]))


# conn:database句柄，必须先调用connect('database name')
# table:表名
# rows：插入的数据，列表格式，rows[0]为表头，例如[('hostname','status'), (0, 0), (1, 1), (2, 2)]
def db_table_add_rows(conn, table, rows):
    if not rows:
        return True, ''
    header = rows[0]
    #condition_key_index = [header.index(key) for key in keys]
    #condition_where = ' and '.join(('%s=?' % key for key in keys))

    #def has_item(row):
    #    return db_table_has_item(conn, table, [condition_where, [row[i] for i in condition_key_index]])

    sql = 'insert into %s(%s) values(%s)' % (table, ','.join(header), ','.join('?' * len(header)))
    try:
        for row in rows[1:]:
            #if not has_item(row):
            conn.execute(sql, row)
    except Exception as e:
        conn.rollback()
        return False, str(e)
    else:
        conn.commit()
        return True, ''


# 删除表中符合条件的所有数据
def db_table_remove(conn, table, condition_pair):
    sql = 'delete from ' + table
    if condition_pair:
        where, values = condition_pair
        sql = '%s where %s' % (sql, where)
        conn.execute(sql, values)
    else:
        conn.execute(sql)
    conn.commit()


# 完全删除数据表
def db_table_drop(conn, table):
    sql = 'drop table if exists ' + table
    try:
        conn.execute(sql)
        conn.commit()
    except Exception as e:
        conn.rollback()
        return False, str(e)
    else:
        conn.commit()
        return True, ''


# 更新表中某字段
def db_table_update(conn, table, field_name, field_value, condition_pair):
    sql = 'update %s set %s' % (table, ','.join(field_name))
    try:
        if condition_pair:
            where, values = condition_pair
            sql = '%s where %s' % (sql, where)
            conn.execute(sql, field_value + values)
        else:
            conn.execute(sql)
        conn.commit()
    except Exception as e:
        conn.rollback()
        return False, str(e)
    else:
        return True, ''


# 创建表
# conn:database句柄，必须先调用connect('database name')
# table:表名称
# fields_define:列表形式，包括所有的字段名称
# index_fields:索引名称，可以为空[]
# 调用完后必须调用cursor.close()和conn.close()
def db_create_table(conn, table, fields_define, index_fields):
    if not db_has_table(conn, table):
        try:
            conn.execute('''create table %s(%s)''' % (table, ','.join(fields_define)))
            for index_field in index_fields:
                conn.execute('create index idx_%s_%s on %s(%s)' % ((table, index_field) * 2))
        except Exception as e:
            conn.rollback()
            return False, str(e)
        else:
            conn.commit()
            return True, ''
    else:
        db_table_remove(conn, table, None)
        return True, ''


def db_get_conn():
    global db_path
    return sqlite3.connect(db_path)


def db_close(cursor, conn):
    if cursor:
        cursor.close()
    if conn:
        conn.close()

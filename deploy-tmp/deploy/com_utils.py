#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import logging
import logging.config
import time


def compare_list(src_list, cmp_list):
    """
    比较两个list是否相等
    :param src_list: 源list
    :param cmp_list: 目标list
    :return: True：相等 False：不等
    """
    return set(src_list) == set(cmp_list)


def is_contain_null(src_list):
    """
    判断列表中是否包含空元素
    :param src_list: 元素列表
    :return: True：包含空元素 False: 不包含空元素
    """
    return '' in src_list or [] in src_list or {} in src_list


def get_timestamp():
    """
    获取当前时间戳
    :return:
    """
    return time.time()


def get_local_time():
    """
    返回当前时间，格式化为2016-03-20 11:45:39形式
    :return:
    """
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


class Callback:
    def __init__(self, instance, function_name):
        self.instance = instance
        self.function_name = function_name
    
    def __call__(self, params):
        self.action(params)

    def action(self, params):
        self.instance.__getattribute__(self.function_name)(params)

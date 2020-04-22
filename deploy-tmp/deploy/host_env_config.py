#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import logging
import logging.config


class HostEnvConfig(object):
    def __init__(self, host_config_dict=dict(), logger=None):
        """
        配置主机环境
        :param host_config_dict: dict 配置主机环境参数，格式如下：

        :param logger:
        """
        self.logger = logger

        return

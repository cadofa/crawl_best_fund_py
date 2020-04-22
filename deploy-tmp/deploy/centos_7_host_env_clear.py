#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import logging
import logging.config
import parse_config
from host_env_clear import *


class CentOs7HostEnvClear(HostEnvClear):
    def __init__(self):
        self.os_type = self.host_info['os']['type']
        self.os_version = self.host_info['os']['version']
        return

    def service_restart(self, service_list=[], is_restart_configed_service=False):
        """
        重启服务
        :param service_list: 服务列表
        :param is_restart_configed_service: True：重启配置的服务，False: 不重启配置的服务
        :return:
        """
        return

    def kernel_set(self):
        """
        完成配置文件中多个小节配置，包括：remove_kernel_param，recover_disk_config，recover_ssd_config
        :return:
        """
        return

    def remove_pkg(self):
        """
        卸载程序
        :return:
        """
        pass

    def clear_host_env(self):
        return

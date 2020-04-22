#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import logging
import logging.config
import global_variable
import json
import threading


def get_cluster_env_clear_status():
    """
    获取整个集群目前清理的结果
    :return:  完成的情况：{'status':'status', 'detail':dict}，status包括'success'，'failure', 'finish', 其中success: finish+success, failure: 完全失败，finish: 有成功，有失败
             未完成的情况：{'status':'unfinished', 'detail':{}}
    """
    result = dict()
    return result


class CephClusterEnvClear(object):
    def __init__(self, host_list=[], os_clear_config_dict={}, logger=None):
        """
        集群机器列表信息初始化
        :param host_list: 集群机器列表信息，各个host节点信息格式和内容如下：{'hostname':'hostname', 'ip':'ip', 'root_pass':'root_pass', 'ssh_port': 'ssh_port',
         'os':{'type':'centos', 'version':'version'}}
        :param os_clear_config_dict: os_config_dict: key为os_type+os_version,value为该版本类型host的环境配置，具体参考host_env_init.conf
         {'centos7':{'remove_kernel_param':{},'remove_pkg':[], 'recover_disk_config':{}, 'recover_ssd_config':{}, 'del_file':['path1', 'path2'...]}}
         有的服务或配置，通过remove pkg即可
        :param logger:
        """
        self.host_list = host_list
        self.os_clear_config_dict = os_clear_config_dict
        self.logger = logger
        self.host_count = len(host_list)
        self.host_cleared = 0
        # 存储所有主机的实例
        self.host_env_clear_instances = dict()
        global_variable.cluster_clear_mutex = threading.Lock()
        return

    def clear_cluster_env(self):
        """
        并行清理集群各个节点的环境，这里考虑使用线程池，还是无限制创建线程------考虑集群规模，机器配置
        :return:
        """
        return

    def notify_host_env_clear_result(self, params):
        """
        一旦某一个host环境清理状态发生改变，通知cluster
        :param params:
        :return:
        """
        return

    def get_cluster_env_clear_detail(self):
        """
        获取整个集群目前清理进度的详细信息
        :return:
        """
        return

    def get_one_host_env_clear_status(self, hostname):
        """
        获取指定hostname机器环境清理结果
        :param hostname: 机器名称
        :return:
        """
        return

    def get_one_host_env_clear_detail(self, hostname):
        """
        获取指定hostname机器环境清理详情
        :param hostname:
        :return:
        """
        return

    def get_cluster_env_clear_failed_hosts_detail(self):
        """
        获取集群环境清理时，清理失败的hosts详细信息
        :return:
        """
        return







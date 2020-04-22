#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import threading
from enum import IntEnum

global host_const_keys_info_keys
global host_const_keys_info
global CMD_RETRY_TIMES_CONST
CMD_RETRY_TIMES_CONST = 5
#global cluster_init_mutex

# current support host type and version list for env initializing and clearing
support_host_type_version_list = ['centos7']

# current support host op type
support_host_env_op_type = ['init_env', 'clear_env']

host_const_keys_info = {'main': ['hostname', 'ips', 'network', 'rock_id', 'ssh_user', 'ssh_port', 'os',
                                 'node_type', 'ntp_server', 'op_type'],
                        'ips': ['manage_ip', 'public_network_ip', 'private_network_ip'],
                        'network': ['manage_network', 'public_network', 'private_network'],
                        'os': ['type', 'version']}
host_const_keys_info_keys = ['main', 'ips', 'network', 'os']

"""
DB相关
"""
cluster_env_op_result_table = 'cluster_env_op_result'
tables_info = {
    'cluster_env_op_result': ['cluster_id', 'result', 'host_num', 'success_updated_num',
                              'success_updated_host_list',
                              'failed_updated_host_list', 'need_optmize_host_list', 'details', 'time']
}

"""
host-env初始化步骤
"""


class HostEnvInitSteps(IntEnum):
    INIT_VAR = 1  # 1. 初始化变量
    CHECK_CONNECTION = 2  # 2. 连通性检查
    UPDATE_SOURCE = 3  # 3. 更换源
    REMOVE_INSTALL_PKG = 4  # 4. 卸载/安装必备的pkg
    CONFIG_FIREWALL = 5  # 5. 防火墙配置
    CONFIG_KERNEL = 6  # 6. kernel参数配置
    CONFIG_DISK_OPTMIZE = 7  # 7. 磁盘优化配置
    CONFIG_DISK_BREAK_BIND = 8  # 8. 硬盘中断绑定配置
    CONFIG_NTP = 9  # 9. ntp配置(包含时区配置)
    CONFIG_SELINUX = 10  # 10. selinux设置
    CHECK_BANDWIDTH = 11  # 11. 带宽检测
    CONFIG_HOSTNAME = 12  # 12. 配置主机名
    REBOOT = 13  # 13. 重启机器


class HostEnvClearSteps(IntEnum):
    INIT_VAR = 1  # 1. 初始化变量
    REMOVE_PKG_CEPH = 2  # 2. 卸载安装包
    CLEAR_FIREWALL = 3  # 3. 清理防火墙配置
    CLEAR_DISK_OPTMIZE = 4  # 4. 清理磁盘优化配置
    CLEAR_DISK_BREAK_BIND = 5  # 5. 清理硬盘中断绑定配置
    CLEAR_NTP_CONFIG = 6  # 6. 清理ntp配置配置
    RECOVER_SELINUX_CONFIG = 7  # 7. 还原selinux配置
    REBOOT = 8  # 8. 重启机器



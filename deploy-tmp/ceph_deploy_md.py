#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import sys
import os
import threading
import threadpool
import commands
import re
import copy
import logging
import logging.config
import time

import global_list
from command import *

from deploy.ceph_cluster_env import CephClusterEnv


def config_os_env():
    os_dict = dict()
    os_dict['centos7'] = dict()
    os_dict['centos7']['linux_source'] = dict()
    os_dict['centos7']['linux_source']['repo_file'] = './deploy/CentOS-Base.repo'
    os_dict['centos7']['kernel_param'] = list()
    item_1 = dict()
    item_1['kernel.pid_max'] = '4194303'
    item_1['file'] = '/etc/sysctl.conf'
    item_1['vm.swappiness'] = '0'
    item_1['fs.file-max'] = '1310710'
    os_dict['centos7']['kernel_param'].append(item_1)
    item_2 = dict()
    item_2['file'] = '/etc/security/limits.conf'
    item_2['soft_limit'] = '1024000'
    item_2['hard_limit'] = '1024000'
    os_dict['centos7']['kernel_param'].append(item_2)
    os_dict['centos7']['request_pkg'] = dict()
    os_dict['centos7']['request_pkg']['remove'] = 'firewalld NetworkManager chrony'
    os_dict['centos7']['request_pkg']['install'] = 'iptables-services ntp hdparm smartmontools bc gdisk nvme-cli ceph'
    os_dict['centos7']['disk_optimize'] = dict()
    os_dict['centos7']['disk_optimize']['source_file'] = './deploy/disk-optimize.sh'
    os_dict['centos7']['disk_optimize']['dest_file_path'] = '/usr/local/bin/'
    os_dict['centos7']['ssd_break_bind'] = dict()
    os_dict['centos7']['ssd_break_bind']['source_file'] = './deploy/bind_nvme_irq.sh'
    os_dict['centos7']['ssd_break_bind']['dest_file_path'] = '/usr/local/bin/'
    os_dict['centos7']['timezone'] = dict()
    os_dict['centos7']['timezone']['continent'] = 'Asia'
    os_dict['centos7']['timezone']['city'] = 'Shanghai'
    return os_dict


# OSD请求类
class ReqDeploy:
    def __init__(self, user_data, reqid, logger):
        self.act = user_data['act']
        self.reqid = int(reqid)
        self.logger = logger

    # 线程处理函数
    def ThreadDealer(self):
        resp = dict()
        resp['act'] = str(self.act)
        resp['type'] = 'deploy'
        resp['status'] = 'running'

        # 加锁->获取结果列表->追加结果->更新列表->解锁
        mtx = global_list.get_value('MUTEX')
        mtx.acquire()
        result = global_list.get_value('RESULTS')
        result[int(self.reqid)] = copy.deepcopy(resp)
        global_list.set_value('RESULTS',result)
        mtx.release()

        # 执行具体命令
        if self.act == 'init_host_env':
            ret = self.init_host_env()
            resp = self.update_resp(ret, resp)
        elif self.act == 'check_network':
            ret = self.check_network()
            resp = self.update_resp(ret, resp)
        elif self.act == 'set_linux_source':
            ret = self.set_linux_source()
            resp = self.update_resp(ret, resp)
        else:
            pass
 
        # 更新结果
        mtx = global_list.get_value('MUTEX')
        mtx.acquire()
        res = global_list.get_value('RESULTS')
        res[int(self.reqid)] = copy.deepcopy(resp)
        global_list.set_value('RESULTS',res)
        mtx.release()


    def update_resp(self, ret, resp):
        resp.update(ret)
        if ret.has_key('err') is False:
            resp['status'] = 'success'
        else:
            resp['status'] = 'failed'
        return resp

    def set_linux_source(self):
        respdict = dict()
        respdict['err'] = "set linux source"
        return respdict

    def check_network(self):
        err_dict = dict()
        respdict = dict()
        return respdict

    def init_host_env(self):
        host_list = None
        try:
            ret = True
            info = [{u'network': {u'private_network': '10.211.55.0', 
                                  u'manage_network': '10.211.55.0', 
                                  u'public_network': '10.211.55.0'}, 
                     u'ssh_port': '22', 
                     u'hostname': 'CentOS-Virtual-2', 
                     u'node_type': [u'mon'], 
                     u'ips': {u'private_network_ip': '10.211.55.6', 
                              u'manage_ip': '10.211.55.6', 
                              u'public_network_ip': '10.211.55.6'}, 
                     u'rock_id': u'1', 
                     u'ssh_user': u'root', 
                     u'op_type': u'init_env', 
                     u'ntp_server': '10.39.111.239', 
                     u'os': {u'version': u'7', 
                             u'type': u'centos'}
                            }
                   ]
            if ret is False:
                print("error: " + info)
            else:
                host_list = info
                #print('host_list: ' + json.dumps(host_list))
        except Exception as e:
            print(e)
        if host_list is not None and len(host_list) > 0:
            print "start config_os_env"
            os_dict = config_os_env()
            print "CephClusterEnv init"
            ceph_cluster_env_init_obj = CephClusterEnv(host_list, os_dict, self.logger)
            print "self start op_cluster_env()"
            ceph_cluster_env_init_obj.op_cluster_env()
        else:
            print('len(host_list) is zero')
        respdict = dict()
        return respdict

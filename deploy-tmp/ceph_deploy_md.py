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
from subprocess import Popen, PIPE, STDOUT

import global_list
from command import *
import database_api as db
import paramiko_api as sshc

# OSD请求类
class ReqDeploy:
    def __init__(self, user_data, reqid, logger):
        self.act = user_data['act']
        self.reqid = int(reqid)
        self.logger = logger
        self.host_status_dict = dict()
        self.host_info = {
            u'network': {
                u'private_network': '192.168.198.0', 
                u'manage_network': '192.168.198.0', 
                u'public_network': '192.168.198.0'
            }, 
            u'ssh_port': '22', 
            u'hostname': 'centos-virtual-2', 
            u'node_type': [u'mon'], 
            u'ips': {
                u'private_network_ip': '192.168.198.129', 
                u'manage_ip': '192.168.198.129', 
                u'public_network_ip': '192.168.198.129'
            }, 
            u'rock_id': u'1', 
            u'ssh_user': u'root', 
            u'op_type': u'init_env', 
            u'ntp_server': '10.39.111.239', 
            u'os': {
                u'version': u'7', 
                u'type': u'centos'
            }
        }

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
        if self.act == 'check_pass_free':
            ret = self.check_pass_free()
            resp.update(ret)
        if ret.has_key('err') is False:
            resp['status'] = 'success'
        else:
            resp['status'] = 'failed'
 
        # 更新结果
        mtx = global_list.get_value('MUTEX')
        mtx.acquire()
        res = global_list.get_value('RESULTS')
        res[int(self.reqid)] = copy.deepcopy(resp)
        global_list.set_value('RESULTS',res)
        mtx.release()

    def check_pass_free(self):
        
        self.host_status_dict['hostname'] = self.host_info['hostname']
        self.host_status_dict['result'] = 'unfinished'
        self.host_status_dict['status'] = 'none'
        self.host_status_dict['details'] = list()
        self.host_status_dict['current_step'] = 1
        self.host_status_dict['need_optmize_steps'] = list()
        
        passless_login_cmd = 'ssh -p ' + str(self.host_info['ssh_port']) + ' -o stricthostkeychecking=no ' \
                             + self.host_info['ssh_user'] + '@' + self.host_info['hostname'] + ' "ls"'
        print "passless_login_cmd", passless_login_cmd
        cmd_result_list = self._run_popen_cmd(passless_login_cmd)
        for cmd_result_item in cmd_result_list:
            if cmd_result_item.strip().find('password:') >= 0:
                #self.logger.error("HostEnv::_init_system_var: ssh passwordless login failed. ")
                print "HostEnv::_init_system_var: ssh passwordless login failed. "
                return False

        if self._get_ssh_instance() is False:
            #self.logger.error("HostEnv::_init_system_var: ssh connect failed, hostname is "
            #                  + self.host_info['hostname'])
            print "HostEnv::_init_system_var: ssh connect failed, hostname is " + self.host_info['hostname']
            return False
        self.logger.info("HostEnv::_init_system_var: get ssh_client instance success.")
        return True

    def _run_popen_cmd(self, cmd):
        """
        执行popen命令
        :param cmd: 要执行的命令
        :return: 命令输出
        """
        ret = Popen(cmd, stdout=PIPE, stderr=STDOUT, shell=True)
        cmd_result_list = ret.stdout.readlines()
        ret.stdout.close()
        return cmd_result_list

    def _get_ssh_instance(self):
        """
        获取ssh_client实例
        :return: True: 成功 False: 失败
        """
        self.ssh_client = sshc.mySSH(self.host_info['hostname'],
                                     int(self.host_info['ssh_port']), self.host_info['ssh_user'])
        ret, err = self.ssh_client.connect()
        if ret is False:
            self.logger.error("HostEnv::_get_ssh_instance: invoke ssh connect error.")
            return False
        return True

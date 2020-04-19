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
                u'private_network': '10.211.55.0', 
                u'manage_network': '10.211.55.0', 
                u'public_network': '10.211.55.0'
            }, 
            u'ssh_port': '22', 
            u'hostname': 'CentOS-Virtual-2', 
            u'node_type': [u'mon'], 
            u'ips': {
                u'private_network_ip': '10.211.55.6', 
                u'manage_ip': '10.211.55.6', 
                u'public_network_ip': '10.211.55.6'
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
        has_err = False
        for k, v in self.host_info["ips"].items():
            err_dict[k] = list()
            ssh_client = self.get_ssh_client(v, 22, "root")
            if not ssh_client:
                err_dict[k].append("get ssh_client failed %s" % v)
                has_err = True
                continue
            ret, info = self._run_command(ssh_client, 'ping -c 4 ' + v)
            if ret is False:
                info = 'HostEnv::_check_network: execute cmd failed, ' + info
                self.logger.error(info)
                has_err = True
            if info.find('4 received') <= 0 and info.find('3 received') <= 0 \
                    and info.find('2 received') <= 0 and info.find('1 received') <= 0:
                err_dict[k].append("get ssh_client failed %s" % v)
                has_err = True
            ssh_client.close()
        if has_err:
            respdict["err"] = err_dict
        return respdict

    def _run_command(self, ssh_client, cmd):
        """
        执行指定的命令
        :param cmd:
        :return: True, result:成功 False, err_info：失败
        """
        ret = ssh_client.run_cmd(cmd)
        if ret['ret'] == -1:
            err_info = "HostEnv::_run_command: execute cmd: " + cmd + " error."
            self.logger.error(err_info)
            return False, err_info
        return True, ret['out'].strip()


    def check_pass_free(self):
        respdict = dict()
        self.host_status_dict['hostname'] = self.host_info['hostname']
        self.host_status_dict['result'] = 'unfinished'
        self.host_status_dict['status'] = 'none'
        self.host_status_dict['details'] = list()
        self.host_status_dict['current_step'] = 1
        self.host_status_dict['need_optmize_steps'] = list()
        
        passless_login_cmd = 'ssh -p ' + str(self.host_info['ssh_port']) + ' -o stricthostkeychecking=no ' \
                             + self.host_info['ssh_user'] + '@' + self.host_info['hostname'] + ' "ls"'
        cmd_result_list = self._run_popen_cmd(passless_login_cmd)
        for cmd_result_item in cmd_result_list:
            if cmd_result_item.strip().find('password:') >= 0:
                self.logger.error("HostEnv::_init_system_var: ssh passwordless login failed. ")
                respdict['err'] = "HostEnv::_init_system_var: ssh passwordless login failed. "

        return respdict
        

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

    def get_ssh_client(self, host_ip, ssh_port=22, ssh_user="root"):
        """
        获取ssh_client实例
        :return: True: 成功 False: 失败
        """
        ssh_client = sshc.mySSH(host_ip, ssh_port, ssh_user)
        ret, err = ssh_client.connect()
        if ret is False:
            self.logger.error("ssh connect error.")
            return 
        return ssh_client

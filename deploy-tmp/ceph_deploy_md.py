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
import database_api as db
import paramiko_api as sshc

# OSD请求类
class ReqDeploy:
    def __init__(self, dict, reqid, logger):
       self.act = dict['act']
       self.reqid = int(reqid)

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
        if self.act == 'getstats':
            if self.item is not None:
                ret = self.getstatsbyorder()
            else:
                ret = self.getstats()
            if ret.has_key('err') is False:
                resp.update(ret)
                resp['status'] = 'success'
            else:
                resp['status'] = 'failed'
        else:
            pass
 
        # 更新结果
        mtx = global_list.get_value('MUTEX')
        mtx.acquire()
        res = global_list.get_value('RESULTS')
        res[int(self.reqid)] = copy.deepcopy(resp)
        global_list.set_value('RESULTS',res)
        mtx.release()

    # 辅助函数，用于获取某个OSD的host和ip
    def find_osd(self, idx, version):
        item = dict()
        osd_find = CephExeCommand(cmd='osd find', arg=str(idx), format='json')
        if osd_find.has_key('err') is True:
            self.logger.error("reqid:" + str(self.reqid) + " osd find failed, error is " + str(osd_find['err']))
            item['err'] = osd_find['err']
            item['id'] = idx
            return item

        result = osd_find['result']
        try:
            item['id'] = idx
            item['host'] = result.get('crush_location').get('host')
            item['ip'] = result.get('ip')
        except Exception as e:
            self.logger.error("reqid:" + str(self.reqid) + " find osd failed, error is " + str(e))
            item['err'] = "find osd failed"
            item['id'] = idx
            return item

        # support ssh configure user and port
        sshclient = sshc.mySSH(str(item['host']))
        ret, err = sshclient.connect()
        if ret is False:
            self.logger.error("reqid:" + str(self.reqid) + " ssh connect failed")
            item['err'] = '连接主机失败'
            item['id'] = idx
            return item

        # 从ceph daemon获取nearfull
        if version >= 12:
            cmd = "ceph daemon osd." + str(idx) + " config get mon_osd_nearfull_ratio -f json 2>/dev/null"
        else:
            cmd = "ceph daemon osd." + str(idx) + " config get osd_failsafe_nearfull_ratio -f json 2>/dev/null"
        ret = sshclient.run_cmd(cmd)
        if ret['ret'] != 0:
            self.logger.error("reqid:" + str(self.reqid) + " get osd_failsafe_nearfull_ratio failed, ret is " + str(ret))
            item['nearfull_ratio'] = 0
        else:
            res = ret['out']
            try:
                val = json.loads(res)
                if version >= 12:
                    item['nearfull_ratio'] = float(val['mon_osd_nearfull_ratio'])
                else:
                    item['nearfull_ratio'] = float(val['osd_failsafe_nearfull_ratio'])
            except Exception as e:
                self.logger.error("reqid:" + str(self.reqid) + " parse nearfull_ratio error, output is " + str(res))
                item['nearfull_ratio'] = 0

        # 从ceph daemon获取full
        cmd = "ceph daemon osd." + str(idx) + " config get osd_failsafe_full_ratio -f json 2>/dev/null"
        ret = sshclient.run_cmd(cmd)
        if ret['ret'] != 0:
            self.logger.error("reqid:" + str(self.reqid) + " get osd_failsafe_full_ratio failed, ret is " + str(ret))
            item['full_ratio'] = 0
        else:
            res = ret['out']
            try:
                val = json.loads(res)
                item['full_ratio'] = float(val['osd_failsafe_full_ratio'])
            except Exception as e:
                self.logger.error("reqid:" + str(self.reqid) + " parse full_ratio error, output is " + str(res))
                item['full_ratio'] = 0

        sshclient.close()
        self.logger.debug("reqid:" + str(self.reqid) + " osd id:" + str(idx) + " host:" + str(item['host']) +
                          " ip:" + str(item['ip']))
        return item


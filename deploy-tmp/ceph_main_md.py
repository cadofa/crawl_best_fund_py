#!/ur/bin/python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import sys
import web
import json
import threading
import random
import copy
import logging
import logging.config
import commands

from ceph_mon_md import *
from ceph_osd_md import *
from ceph_deploy_md import ReqDeploy
from ceph_diskusage_md import *
from ceph_data_md import *
from ceph_scrub_md import *
from ceph_image_md import *
from ceph_disk_md import *
from ceph_update_md import *
from command import *
from init_zabbix_md import *
from global_list import *
from ceph_jobs_md import *
from init_basecheck_md import *
from ceph_mgr_md import *
from utils import detect_file_change, log_full_url, get_rbd_info_period
#from init_customcheck_md import *

#import database_api as db
import paramiko_api as sshc

web.config.debug = True

# 结果字典，key为reqid
results = dict()
taskinfo = dict()

urls = (
    '/ceph/mon', 'mon',
    '/ceph/osd', 'osd',
    # '/ceph/config', 'config',
    '/ceph/diskusage', 'diskusage',
    '/ceph/data', 'data',
    '/ceph/consistent', 'consistent',
    '/ceph/disk', 'disk',
    '/ceph/image', 'image',
    '/ceph/update', 'update',
    '/ceph/result', 'result',
    '/ceph/mgr', 'mgr',
    '/ceph/zabbix', 'zbx',
    '/ceph/basecheck', 'basecheck',
    '/ceph/customcheck', 'customcheck',
    '/ceph/jobs', 'jobs',
    '/ceph/deploy', 'deploy',
)

# 各个class动作名称一览
MonAct = ('getstats', 'getstatsbyregex', 'start', 'stop', 'restart', 'delete', 'add', 'gethosts')
DeployAct = ('check_pass_free', 'check_network', 'set_linux_source')
OsdAct = ('getstats', 'getstatsbyregex', 'start', 'stop', 'restart', 'getreweight', 'setreweight',
          'getnearfull', 'setnearfull', 'getfull', 'setfull', 'setout', 'setin', 'setall', 
          'getosdtree', 'getosddf')
DiskusgAct = ('getstats', 'setnearfull', 'setfull', 'setall')
DataAct = ('getstats', 'enable', 'disable', 'getautocontrol', 'setband')
ScrubAct = ('getstats', 'enable', 'disable', 'notdone', 'dodeepscrub', 'doscrub', 'getbad',
            'dodeepscrubbyosd', 'doscrubbyosd', 'repair', 'getrecord')
ScrubPOSTAct = ('batch_scrub', 'batch_deepscrub')
DiskAct = ('getinfo', 'checkdisk', 'replacedata_step_1', 'replacedata_step_3', 'replacejournal_step_1',
           'replacejournal_step_3', 'getdatarecord', 'getosdtree', 'isundersized', 'getjournalrecord',
           'checkonline', 'replacejournal_step_2')
ImageAct = ('getpoolname', 'getallstats', 'getstats', 'getstatsbyregex', 'getrbdbackend', 'getrbdbypool',
            'getrbdsnap', 'getsession', 'getrbd')
UpdateAct = ('getstats', 'getdest', 'doupdate')
ZabbixGETAct = ('register', 'check', 'get', 'clean', 'getceph', 'choosemode', 'getmode', 'getalert',
                'getphystep', 'getcephstep', 'getalertbyname', 'getrule', 'isinitdone', 'initskip',
                'getrulebyid', 'getscaleout', 'getscalehosts')
ZabbixPOSTAct = ('import', 'append', 'set_alert_solved', 'set_alert_processing', 'set_rule')
BasecheckAct = ('netcommon', 'netperf', 'diskperf', 'rbd', 'iscsi', 'cephfs', 'getreport')
CustomcheckGETAct = ('getreport',)
CustomchecPOSTkAct = ('rbd', 'iscsi')
MgrAct = ('getstats', 'getstatsbyregex', 'add', 'delete', 'getaddnode')
JobsAct = ('getjobs',)

#app = web.application(urls, globals(), autoreload=True)

# 处理deploy相关请求
class deploy:
    @log_full_url
    def GET(self):
        user_data = web.input(act=None, page=0, pagesize=0, val=None, item=None, host=None, nearfull=None, full=None)
        # 检验act参数是否正确
        print user_data.act
        print DeployAct
        if user_data.act not in DeployAct:
            return 'error'

        # 利用随机数生成reqid
        res = global_list.get_value('RESULTS')
        while True:
            # 生成reqid
            reqid = random.randint(100, 10000000)
            if res.has_key(reqid) is True:
                continue
            else:
                break

        # start job thread
        logger = logging.getLogger("deploy")
        DeployClt = ReqDeploy(dict(user_data), reqid, logger)
        t = threading.Thread(target=DeployClt.ThreadDealer)
        t.setDaemon(True)
        t.start()

        # 返回应答结果
        respdict = dict()
        respdict['act'] = user_data.act
        respdict['type'] = 'deploy'
        respdict['status'] = 'ok'
        respdict['reqid'] = reqid
        return json.dumps(respdict)

# 处理mon相关请求
class mon:
    @log_full_url
    def GET(self):
        user_data = web.input(act=None, val=None, host=None, order1=None, order2=None)
        # 检验act参数是否正确
        if user_data.act not in MonAct:
            return 'error'
        # 获取mutex
        mtx = global_list.get_value('MUTEX')
        mtx.acquire()

        # gethosts直接返回
        if user_data.act == 'gethosts':
            monhosts = global_list.get_value('MON')
            cephhost = global_list.get_value('HOSTS')
            ret_list = [item for item in cephhost if item not in monhosts]
            respdict = dict()
            respdict['act'] = user_data.act
            respdict['type'] = 'mon'
            respdict['status'] = 'success'
            respdict['result'] = ret_list
            mtx.release()
            logger = logging.getLogger("main")
            logger.info("get available added mon host = " + str(ret_list))
            return json.dumps(respdict)

        # 查看此时是否可以做某些动作
        exclude_mon_act = ('start', 'stop', 'restart', 'delete', 'add')
        exclude = global_list.get_value('EXCLUDE')
        init_status = global_list.get_value('INITDONE')
        # 如果初始化未完成或当前有排他操作，则返回错误
        if init_status == 'no' or (exclude is True and (user_data.act in exclude_mon_act)):
            respdict = dict()
            respdict['act'] = user_data.act
            respdict['type'] = 'mon'
            respdict['status'] = 'failed'
            respdict['reqid'] = 0
            respdict['err'] = '有其它集群操作正在进行，请稍后重试'
            mtx.release()
            logger = logging.getLogger("main")
            logger.error("class: mon act: " + str(user_data.act) +
                         " there are some all cluster effective operations, no permit now")
            return json.dumps(respdict)

        # mon的删除和添加操作不并发执行
        if user_data.act == 'delete' or user_data.act == 'add':
            global_list.set_value('EXCLUDE', True)

        # 利用随机数生成reqid
        res = global_list.get_value('RESULTS')
        while True:
            # 生成reqid
            reqid = random.randint(100, 10000000)
            if res.has_key(reqid) is True:
                continue
            else:
                break
        mtx.release()

        # start job thread
        logger = logging.getLogger("mon")
        MonClt = ReqMon(dict(user_data), reqid, logger)
        t = threading.Thread(target=MonClt.ThreadDealer)
        t.setDaemon(True)
        t.start()

        # 返回应答结果
        respdict = dict()
        respdict['act'] = user_data.act
        respdict['type'] = 'mon'
        respdict['status'] = 'ok'
        respdict['reqid'] = reqid
        return json.dumps(respdict)


# 处理osd相关请求
class osd:
    @log_full_url
    def GET(self):
        user_data = web.input(act=None, page=0, pagesize=0, val=None, item=None, host=None, nearfull=None, full=None)
        # 检验act参数是否正确
        if user_data.act not in OsdAct:
            return 'error'
        # 获取mutex
        mtx = global_list.get_value('MUTEX')
        mtx.acquire()
        # 查看此时是否可以做某些动作
        exclude_osd_act = ('start', 'stop', 'restart', 'setreweight', 'setnearfull', 'setfull', 'setout', 'setin', 'setall')
        exclude = global_list.get_value('EXCLUDE')
        init_status = global_list.get_value('INITDONE')
        # 如果初始化未完成或当前有排他操作，则返回错误
        if init_status == 'no' or (exclude is True and (user_data.act in exclude_osd_act)):
            respdict = dict()
            respdict['act'] = user_data.act
            respdict['type'] = 'osd'
            respdict['status'] = 'failed'
            respdict['reqid'] = 0
            respdict['err'] = '有其它集群操作正在进行，请稍后重试'
            mtx.release()
            logger = logging.getLogger("main")
            logger.error("class: osd act: " + str(user_data.act) +
                         " there are some all cluster effective operations, no permit now")
            return json.dumps(respdict)

        # 利用随机数生成reqid
        res = global_list.get_value('RESULTS')
        while True:
            # 生成reqid
            reqid = random.randint(100, 10000000)
            if res.has_key(reqid) is True:
                continue
            else:
                break
        mtx.release()

        # start job thread
        logger = logging.getLogger("osd")
        OsdClt = ReqOsd(dict(user_data), reqid, logger)
        t = threading.Thread(target=OsdClt.ThreadDealer)
        t.setDaemon(True)
        t.start()

        # 返回应答结果
        respdict = dict()
        respdict['act'] = user_data.act
        respdict['type'] = 'osd'
        respdict['status'] = 'ok'
        respdict['reqid'] = reqid
        return json.dumps(respdict)


# 处理集群容量状态相关请求
class diskusage:
    @log_full_url
    def GET(self):
        user_data = web.input(act=None, val=None, nearfull=1, full=1)
        # 检验act参数是否正确
        if user_data.act not in DiskusgAct:
            return 'error'
        # 获取mutex
        mtx = global_list.get_value('MUTEX')
        mtx.acquire()
        # 查看此时是否可以做某些动作
        exclude_diskusg_act = ('setnearfull', 'setfull', 'setall')
        exclude = global_list.get_value('EXCLUDE')
        init_status = global_list.get_value('INITDONE')
        # 如果初始化未完成或当前有排他操作，则返回错误
        if init_status == 'no' or (exclude is True and (user_data.act in exclude_diskusg_act)):
            respdict = dict()
            respdict['act'] = user_data.act
            respdict['type'] = 'diskusage'
            respdict['status'] = 'failed'
            respdict['reqid'] = 0
            respdict['err'] = '有其它集群操作正在进行，请稍后重试'
            mtx.release()
            logger = logging.getLogger("main")
            logger.error("class: diskusage act: " + str(user_data.act) +
                         " there are some all cluster effective operations, no permit now")
            return json.dumps(respdict)

        # 利用随机数生成reqid
        res = global_list.get_value('RESULTS')
        while True:
            # 生成reqid
            reqid = random.randint(100, 10000000)
            if res.has_key(reqid) is True:
                continue
            else:
                break
        mtx.release()

        # start job thread
        logger = logging.getLogger("diskusage")
        DiskusgClt = ReqDiskusg(dict(user_data), reqid, logger)
        t = threading.Thread(target=DiskusgClt.ThreadDealer)
        t.setDaemon(True)
        t.start()

        # 返回应答结果
        respdict = dict()
        respdict['act'] = user_data.act
        respdict['type'] = 'diskusage'
        respdict['status'] = 'ok'
        respdict['reqid'] = reqid
        return json.dumps(respdict)


# 处理集群数据恢复/回填/均衡相关设置请求
class data:
    @log_full_url
    def GET(self):
        user_data = web.input(act=None, item=None)
        # 检验act参数是否正确
        if user_data.act not in DataAct:
            return 'error'
        # 获取mutex
        mtx = global_list.get_value('MUTEX')
        mtx.acquire()

        # getautocontrol直接返回
        if user_data.act == 'getautocontrol':
            mode = global_list.get_value('AUTOCTRL')
            respdict = dict()
            respdict['act'] = user_data.act
            respdict['type'] = 'data'
            respdict['status'] = 'success'
            respdict['mode'] = str(mode)
            mtx.release()
            logger = logging.getLogger("main")
            logger.info("get autoctrl mode = " + str(mode))
            return json.dumps(respdict)

        # 查看此时是否可以做某些动作
        exclude_data_act = ('enable', 'disable')
        exclude = global_list.get_value('EXCLUDE')
        init_status = global_list.get_value('INITDONE')
        # 如果初始化未完成或当前有排他操作，则返回错误
        if init_status == 'no' or (exclude is True and (user_data.act in exclude_data_act)):
            respdict = dict()
            respdict['act'] = user_data.act
            respdict['type'] = 'data'
            respdict['status'] = 'failed'
            respdict['reqid'] = 0
            respdict['err'] = '有其它集群操作正在进行，请稍后重试'
            mtx.release()
            logger = logging.getLogger("main")
            logger.error("class: data act: " + str(user_data.act) +
                         " there are some all cluster effective operations, no permit now")
            return json.dumps(respdict)

        # data的enable和disable操作不并发执行
        if user_data.act == 'enable' or user_data.act == 'disable':
            global_list.set_value('EXCLUDE', True)

        # 利用随机数生成reqid
        res = global_list.get_value('RESULTS')
        while True:
            # 生成reqid
            reqid = random.randint(100, 10000000)
            if res.has_key(reqid) is True:
                continue
            else:
                break
        mtx.release()

        # start job thread
        logger = logging.getLogger("data")
        DataClt = ReqData(dict(user_data), reqid, logger)
        t = threading.Thread(target=DataClt.ThreadDealer)
        t.setDaemon(True)
        t.start()

        # 返回应答结果
        respdict = dict()
        respdict['act'] = user_data.act
        respdict['type'] = 'data'
        respdict['status'] = 'ok'
        respdict['reqid'] = reqid
        return json.dumps(respdict)


# 处理集群scrub/deep-scrub相关操作请求
class consistent:
    @log_full_url
    def GET(self):
        user_data = web.input(act=None, page=0, pagesize=0, val=None, item=None)
        # 检验act参数是否正确
        if user_data.act not in ScrubAct:
            return 'error'
        # 获取mutex
        mtx = global_list.get_value('MUTEX')
        mtx.acquire()
        # 查看此时是否可以做某些动作
        exclude_scrub_act = ('dodeepscrub', 'doscrub', 'doscrubbyosd', 'dodeepscrubbyosd', 'repair')
        exclude = global_list.get_value('EXCLUDE')
        init_status = global_list.get_value('INITDONE')
        # 如果初始化未完成或当前有排他操作，则返回错误
        if init_status == 'no' or (exclude is True and (user_data.act in exclude_scrub_act)):
            respdict = dict()
            respdict['act'] = user_data.act
            respdict['type'] = 'consistent'
            respdict['status'] = 'failed'
            respdict['reqid'] = 0
            respdict['err'] = '有其它集群操作正在进行，请稍后重试'
            mtx.release()
            logger = logging.getLogger("main")
            logger.error("class: consistent act: " + str(user_data.act) +
                         " there are some all cluster effective operations, no permit now")
            return json.dumps(respdict)

        # 利用随机数生成reqid
        res = global_list.get_value('RESULTS')
        while True:
            # 生成reqid
            reqid = random.randint(100, 10000000)
            if res.has_key(reqid) is True:
                continue
            else:
                break
        mtx.release()

        # start job thread
        logger = logging.getLogger("scrub")
        ScrubClt = ReqScrub(dict(user_data), reqid, logger)
        t = threading.Thread(target=ScrubClt.ThreadDealer)
        t.setDaemon(True)
        t.start()

        # 返回应答结果
        respdict = dict()
        respdict['act'] = user_data.act
        respdict['type'] = 'consistent'
        respdict['status'] = 'ok'
        respdict['reqid'] = reqid
        return json.dumps(respdict)

    def POST(self):
        # user_data = web.input(act=None, pgid=None)
        webdata = web.data()
        user_data = json.loads(webdata)
        # 检验act参数是否正确
        if user_data.get('act') not in ScrubPOSTAct:
            return 'error'
        # 获取mutex
        mtx = global_list.get_value('MUTEX')
        mtx.acquire()
        # 查看此时是否可以做某些动作
        exclude_scrub_act = ('batch_scrub', 'batch_deepscrub')
        exclude = global_list.get_value('EXCLUDE')
        init_status = global_list.get_value('INITDONE')
        # 如果初始化未完成或当前有排他操作，则返回错误
        if init_status == 'no' or (exclude is True and (user_data.act in exclude_scrub_act)):
            respdict = dict()
            respdict['act'] = user_data.get('act')
            respdict['type'] = 'consistent'
            respdict['status'] = 'failed'
            respdict['reqid'] = 0
            respdict['err'] = '有其它集群操作正在进行，请稍后重试'
            mtx.release()
            logger = logging.getLogger("main")
            logger.error("class: consistent act: " + str(user_data.get('act')) +
                         " there are some all cluster effective operations, no permit now")
            return json.dumps(respdict)

        # 利用随机数生成reqid
        res = global_list.get_value('RESULTS')
        while True:
            # 生成reqid
            reqid = random.randint(100, 10000000)
            if res.has_key(reqid) is True:
                continue
            else:
                break
        mtx.release()

        # start job thread
        logger = logging.getLogger("scrub")
        ScrubClt = ReqScrub(dict(user_data), reqid, logger)
        t = threading.Thread(target=ScrubClt.ThreadDealer)
        t.setDaemon(True)
        t.start()

        # 返回应答结果
        respdict = dict()
        respdict['act'] = user_data.get('act')
        respdict['type'] = 'consistent'
        respdict['status'] = 'ok'
        respdict['reqid'] = reqid
        return json.dumps(respdict)


# 处理集群更换磁盘相关请求
class disk:
    @log_full_url
    def GET(self):
        user_data = web.input(act=None, cat=None, host=None, sn=None, item=None, page=1, pagesize=10)
        # 检验act参数是否正确
        if user_data.act not in DiskAct:
            return 'error'
        # 获取mutex
        mtx = global_list.get_value('MUTEX')
        mtx.acquire()
        # 查看此时是否可以做某些动作
        exclude_disk_act = ('replacedata_step_1', 'replacedata_step_3', 'replacejournal_step_1', 'replacejournal_step_3')
        exclude = global_list.get_value('EXCLUDE')
        logger = logging.getLogger("main")
        logger.error("exclude statut " + str(exclude))
        init_status = global_list.get_value('INITDONE')
        logger.error("init_status " + str(init_status))
        # 如果初始化未完成或当前有排他操作，则返回错误
        if init_status == 'no' or (exclude is True and (user_data.act in exclude_disk_act)):
            respdict = dict()
            respdict['act'] = user_data.act
            respdict['type'] = 'disk'
            respdict['status'] = 'failed'
            respdict['reqid'] = 0
            respdict['err'] = '有其它集群操作正在进行，请稍后重试'
            mtx.release()
            logger = logging.getLogger("main")
            logger.error("class: disk act: " + str(user_data.act) +
                         " there are some all cluster effective operations, no permit now")
            return json.dumps(respdict)

        # disk的换盘操作不并发执行
        if user_data.act == 'replacedata_step_1' \
                or user_data.act == 'replacedata_step_3' \
                or user_data.act == 'replacejournal_step_1' \
                or user_data.act == 'replacejournal_step_3':
            global_list.set_value('EXCLUDE', True)

        # 利用随机数生成reqid
        res = global_list.get_value('RESULTS')
        while True:
            # 生成reqid
            reqid = random.randint(100, 10000000)
            if res.has_key(reqid) is True:
                continue
            else:
                break
        mtx.release()

        # start job thread
        logger = logging.getLogger("disk")
        DiskClt = ReqDisk(dict(user_data), reqid, logger)
        t = threading.Thread(target=DiskClt.ThreadDealer)
        t.setDaemon(True)
        t.start()

        # 返回应答结果
        respdict = dict()
        respdict['act'] = user_data.act
        respdict['type'] = 'disk'
        respdict['status'] = 'ok'
        respdict['reqid'] = reqid
        return json.dumps(respdict)


# 处理集群image相关信息请求
class image:
    @log_full_url
    def GET(self):
        user_data = web.input(act=None, page=0, pagesize=0, val=None, item=None, pool=None)
        # 检验act参数是否正确
        if user_data.act not in ImageAct:
            return 'error'
        # 获取mutex
        mtx = global_list.get_value('MUTEX')
        mtx.acquire()
        # 查看此时是否可以做某些动作
        # exclude=global_list.get_value('EXCLUDE')
        init_status = global_list.get_value('INITDONE')
        # 如果初始化未完成，则返回错误
        if init_status == 'no':
            respdict = dict()
            respdict['act'] = user_data.act
            respdict['type'] = 'image'
            respdict['status'] = 'failed'
            respdict['reqid'] = 0
            respdict['err'] = '有其它集群操作正在进行，请稍后重试'
            mtx.release()
            logger = logging.getLogger("main")
            logger.error("class: image act: " + str(user_data.act) +
                         " there are some all cluster effective operations, no permit now")
            return json.dumps(respdict)

        # 利用随机数生成reqid
        res = global_list.get_value('RESULTS')
        while True:
            # 生成reqid
            reqid = random.randint(100, 10000000)
            if res.has_key(reqid) is True:
                continue
            else:
                break
        mtx.release()

        # start job thread
        logger = logging.getLogger("image")
        ImageClt = ReqImage(dict(user_data), reqid, logger)
        t = threading.Thread(target=ImageClt.ThreadDealer)
        t.setDaemon(True)
        t.start()

        # 返回应答结果
        respdict = dict()
        respdict['act'] = user_data.act
        respdict['type'] = 'image'
        respdict['status'] = 'ok'
        respdict['reqid'] = reqid
        return json.dumps(respdict)


# 处理集群升级相关请求
class update:
    @log_full_url
    def GET(self):
        user_data = web.input(act=None, page=0, pagesize=0, host=None, order1=None, order2=None,
                              ver='0.0.0')
        # 检验act参数是否正确
        if user_data.act not in UpdateAct:
            return 'error'
        # 获取mutex
        mtx = global_list.get_value('MUTEX')
        mtx.acquire()
        # 查看此时是否可以做某些动作
        exclude_update_act = ('doupdate',)
        exclude = global_list.get_value('EXCLUDE')
        init_status = global_list.get_value('INITDONE')
        # 如果初始化未完成或当前有排他操作，则返回错误
        if init_status == 'no' or (exclude is True and (user_data.act in exclude_update_act)):
            respdict = dict()
            respdict['act'] = user_data.act
            respdict['type'] = 'update'
            respdict['status'] = 'failed'
            respdict['reqid'] = 0
            respdict['err'] = '有其它集群操作正在进行，请稍后重试'
            mtx.release()
            logger = logging.getLogger("main")
            logger.error("class: update act: " + str(user_data.act) +
                         " there are some all cluster effective operations, no permit now")
            return json.dumps(respdict)

        # update的doupdate操作不并发执行
        if user_data.act == 'doupdate':
            global_list.set_value('EXCLUDE', True)

        # 利用随机数生成reqid
        res = global_list.get_value('RESULTS')
        while True:
            # 生成reqid
            reqid = random.randint(100, 10000000)
            if res.has_key(reqid) is True:
                continue
            else:
                break
        mtx.release()

        # start job thread
        logger = logging.getLogger("update")
        UpdateClt = ReqUpdate(dict(user_data), reqid, logger)
        t = threading.Thread(target=UpdateClt.ThreadDealer)
        t.setDaemon(True)
        t.start()

        # 返回应答结果
        respdict = dict()
        respdict['act'] = user_data.act
        respdict['type'] = 'update'
        respdict['status'] = 'ok'
        respdict['reqid'] = reqid
        return json.dumps(respdict)


# 处理集群mgr相关信息请求
class mgr:
    @log_full_url
    def GET(self):
        user_data = web.input(act=None, host=None)
        # 检验act参数是否正确
        if user_data.act not in MgrAct:
            return 'error'
        # 获取mutex
        mtx = global_list.get_value('MUTEX')
        mtx.acquire()
        # 查看此时是否可以做某些动作
        init_status = global_list.get_value('INITDONE')
        # 如果初始化未完成，则返回错误
        if init_status == 'no':
            respdict = dict()
            respdict['act'] = user_data.act
            respdict['type'] = 'mgr'
            respdict['status'] = 'failed'
            respdict['reqid'] = 0
            respdict['err'] = '有其它集群操作正在进行，请稍后重试'
            mtx.release()
            logger = logging.getLogger("main")
            logger.error("class: mgr act: " + str(user_data.act) +
                         " there are some all cluster effective operations, no permit now")
            return json.dumps(respdict)

        # 利用随机数生成reqid
        res = global_list.get_value('RESULTS')
        while True:
            # 生成reqid
            reqid = random.randint(100, 10000000)
            if res.has_key(reqid) is True:
                continue
            else:
                break
        mtx.release()

        # start job thread
        logger = logging.getLogger("mgr")
        MgrClt = ReqMgr(dict(user_data), reqid, logger)
        t = threading.Thread(target=MgrClt.ThreadDealer)
        t.setDaemon(True)
        t.start()

        # 返回应答结果
        respdict = dict()
        respdict['act'] = user_data.act
        respdict['type'] = 'mgr'
        respdict['status'] = 'ok'
        respdict['reqid'] = reqid
        return json.dumps(respdict)


# 系统初始化zabbix类
class zbx:
    @log_full_url
    def GET(self):
        user_data = web.input(classname=None, act=None, cat=None, page=0, pagesize=0, timefrom=0, timetill=0,
                              ruleid=None, name=None)
        # 检验act参数是否正确
        if user_data.act not in ZabbixGETAct:
            return 'error'

        # isinitdone直接返回
        if user_data.act == 'isinitdone':
            logger = logging.getLogger("main")
            ZbxClt = ReqZbx({}, reqid=0, logger=logger)
            initinfo = ZbxClt.isinitdone()
            return json.dumps(initinfo)

        # 获取mutex
        mtx = global_list.get_value('MUTEX')
        mtx.acquire()

        # 调用工作机器人查看该动作是否可被执行
        ret, reqid = job_robot('check_action', 'zbxget', user_data.classname, user_data.act, user_data.cat, logging.getLogger("zbx"))
        if ret == 'no':
            respdict = dict()
            respdict['act'] = user_data.act
            respdict['type'] = 'zabbix'
            respdict['status'] = 'failed'
            respdict['reqid'] = 0
            respdict['err'] = '有其它集群操作正在进行，请稍后重试'
            mtx.release()
            logger = logging.getLogger("main")
            logger.error("class: zabbix act: " + str(user_data.act) +
                         " there are some all cluster effective operations, no permit now")
            return json.dumps(respdict)
        mtx.release()

        # start job thread
        logger = logging.getLogger("zbx")
        ZbxClt = ReqZbx(dict(user_data), reqid, logger)
        t = threading.Thread(target=ZbxClt.ThreadDealer)
        t.setDaemon(True)
        t.start()

        # 返回应答结果
        respdict = dict()
        respdict['act'] = user_data.act
        respdict['type'] = 'zabbix'
        respdict['status'] = 'ok'
        respdict['reqid'] = reqid
        return json.dumps(respdict)

    def POST(self):
        user_data = web.input(classname=None, act=None, cat=None, page=0, pagesize=0, myfile={}, eventid=None,
                              ruleid=None, threshold=0, period=0, times=0, grouplist=None, eventtype=None)
        # 检验act参数是否正确
        if user_data.act not in ZabbixPOSTAct:
            return 'error'
        mtx = global_list.get_value('MUTEX')
        mtx.acquire()

        # 调用工作机器人查看该动作是否可被执行
        ret, reqid = job_robot('check_action', 'zbxpost', user_data.classname, user_data.act, user_data.cat, logging.getLogger("zbx"))
        if ret == 'no':
            respdict = dict()
            respdict['act'] = user_data.act
            respdict['type'] = 'update'
            respdict['status'] = 'failed'
            respdict['reqid'] = 0
            respdict['err'] = '有其它集群操作正在进行，请稍后重试'
            mtx.release()
            logger = logging.getLogger("main")
            logger.error("class: update act: " + str(user_data.act) +
                         " there are some all cluster effective operations, no permit now")
            return json.dumps(respdict)
        mtx.release()

        # start job thread
        logger = logging.getLogger("zbx")
        ZbxClt = ReqZbx(dict(user_data), reqid, logger)
        t = threading.Thread(target=ZbxClt.ThreadDealer)
        t.setDaemon(True)
        t.start()

        # 返回应答结果
        respdict = dict()
        respdict['act'] = user_data.act
        respdict['type'] = 'zabbix'
        respdict['status'] = 'ok'
        respdict['reqid'] = reqid
        return json.dumps(respdict)


# 基础测试类
class basecheck:
    @log_full_url
    def GET(self):
        user_data = web.input(classname=None, act=None, cat=None, time=0, poolname=None)
        # 检验act参数是否正确
        if user_data.act not in BasecheckAct:
            return 'error'
        mtx = global_list.get_value('MUTEX')
        mtx.acquire()

        # 调用工作机器人查看该动作是否可被执行
        ret, reqid = job_robot('check_action', 'basecheck', user_data.classname, user_data.act, user_data.cat, logging.getLogger("basecheck"))
        if ret == 'no':
            respdict = dict()
            respdict['act'] = user_data.act
            respdict['type'] = 'basecheck'
            respdict['status'] = 'failed'
            respdict['reqid'] = reqid
            respdict['err'] = '有其它集群操作正在进行，请稍后重试'
            mtx.release()
            logger = logging.getLogger("main")
            logger.error("class: basecheck act: " + str(user_data.act) +
                         " there are some all cluster effective operations, no permit now")
            return json.dumps(respdict)
        mtx.release()

        logger = logging.getLogger("basecheck")
        BcheckClt = ReqBcheck(dict(user_data), reqid, logger)
        t = threading.Thread(target=BcheckClt.ThreadDealer)
        t.setDaemon(True)
        t.start()

        # 返回应答结果
        respdict = dict()
        respdict['act'] = user_data.act
        respdict['type'] = 'basecheck'
        respdict['status'] = 'ok'
        respdict['reqid'] = reqid
        return json.dumps(respdict)


# 自定义测试类
class customcheck:
    @log_full_url
    def GET(self):
        user_data = web.input(act=None, cat=None)
        # 检验act参数是否正确
        if user_data.act not in CustomcheckGETAct:
            return 'error'
        mtx = global_list.get_value('MUTEX')
        mtx.acquire()

        # 调用工作机器人查看该动作是否可被执行
        ret, reqid = job_robot('check_action', 'customcheck', None, user_data.act, user_data.cat)
        if ret == 'no':
            respdict = dict()
            respdict['act'] = user_data.act
            respdict['type'] = 'customcheck'
            respdict['status'] = 'failed'
            respdict['reqid'] = reqid
            respdict['err'] = '有其它集群操作正在进行，请稍后重试'
            mtx.release()
            logger = logging.getLogger("main")
            logger.error("class: customcheck act: " + str(user_data.act) +
                         " there are some all cluster effective operations, no permit now")
            return json.dumps(respdict)
        mtx.release()

        # start job thread
        logger = logging.getLogger("customcheck")
        CcheckClt = ReqCcheck(dict(user_data), reqid, logger)
        t = threading.Thread(target=CcheckClt.ThreadDealer)
        t.setDaemon(True)
        t.start()

        # 返回应答结果
        respdict = dict()
        respdict['act'] = user_data.act
        respdict['type'] = 'customcheck'
        respdict['status'] = 'ok'
        respdict['reqid'] = reqid
        return json.dumps(respdict)

    def POST(self):
        user_data = web.data()
        user_data = json.loads(user_data)
        # input(act='None', time=0, poolname='None', mode='None', imgnum=0, lunnum=0, size='0g', rwmixread=30, bs='0')
        # 检验act参数是否正确
        if user_data['act'] not in CustomchecPOSTkAct:
            return 'error'
        mtx = global_list.get_value('MUTEX')
        mtx.acquire()

        # 调用工作机器人查看该动作是否可被执行
        logger = logging.getLogger("main")
        ret, reqid=job_robot('check_action', 'customcheck', user_data.classname, user_data.act, user_data.cat, logger)
        if ret == 'no':
            respdict = dict()
            respdict['act'] = user_data.act
            respdict['type'] = 'customcheck'
            respdict['status'] = 'failed'
            respdict['reqid'] = reqid
            respdict['err'] = '有其它集群操作正在进行，请稍后重试'
            mtx.release()
            logger.error("class: customcheck act: " + str(user_data.act) +
                         " there are some all cluster effective operations, no permit now")
            return json.dumps(respdict)
        mtx.release()

        # start job thread
        logger = logging.getLogger("customcheck")
        CcheckClt = ReqCcheck(dict(user_data), reqid, logger)
        t = threading.Thread(target=CcheckClt.ThreadDealer)
        t.setDaemon(True)
        t.start()

        # 返回应答结果
        respdict = dict()
        respdict['act'] = user_data.act
        respdict['type'] = 'customcheck'
        respdict['status'] = 'ok'
        respdict['reqid'] = reqid
        return json.dumps(respdict)


# 获取任务类
class jobs:
    @log_full_url
    def GET(self):
        user_data = web.input(act=None)
        # 检验act参数是否正确
        if user_data.act not in JobsAct:
            return 'error'

        logger = logging.getLogger("jobs")
        JobsClt = RReqJobs(dict(user_data), logger)
        jobinfo = JobsClt.getjobs()
        respdict = dict()
        respdict['act'] = user_data.act
        respdict['type'] = 'jobs'
        respdict['results'] = jobinfo
        return json.dumps(respdict)


# 根据以上各个请求，输出状态
class result:
    @log_full_url
    def GET(self):
        user_data = web.input(reqid=0, act='None', type='None', page=0, pagesize=0, sn='0')
        mtx = global_list.get_value('MUTEX')
        mtx.acquire()
        res = global_list.get_value('RESULTS')
        if res.has_key(int(user_data.reqid)) is True:
            if user_data.act == 'replacedata' or user_data.act == 'replacejournal':
                if user_data.sn != '0':
                    res[int(user_data.reqid)]['sn'] = copy.deepcopy(user_data.sn)
            ret = json.dumps(res[int(user_data.reqid)], ensure_ascii = False)
            if res[int(user_data.reqid)]['status'] != 'running':
                del res[int(user_data.reqid)]
        else:
            ret = 'None'
        mtx.release()
        return ret


def process_is_active(host):
    # support ssh configure user and port
    sshclient = sshc.mySSH(str(host))
    ret, err = sshclient.connect()
    if ret is False:
        # self.logger.error("reqid:" + str(self.reqid) + " ssh connect failed")
        return False

    cmd = "systemctl is-active zbx-ceph 2>/dev/null"
    ret = sshclient.run_cmd(cmd)
    if ret['out'] == "active":
        sshclient.close()
        return True
    else:
        sshclient.close()
        return False


def start_process(host):
    sshclient = sshc.mySSH(str(host))
    ret, err = sshclient.connect()
    if ret is False:
        # self.logger.error("reqid:" + str(self.reqid) + " ssh connect failed")
        return False

    cmd = "systemctl start zbx-ceph"
    ret = sshclient.run_cmd(cmd)
    if ret['ret'] == 0:
        sshclient.close()
        return True
    else:
        sshclient.close()
        return False


def stop_process(host):
    sshclient = sshc.mySSH(str(host))
    ret, err = sshclient.connect()
    if ret is False:
        # self.logger.error("reqid:" + str(self.reqid) + " ssh connect failed")
        return False

    cmd = "systemctl stop zbx-ceph"
    ret = sshclient.run_cmd(cmd)
    if ret['ret'] == 0:
        sshclient.close()
        return True
    else:
        sshclient.close()
        return False


# 做一些检查的工作
def do_something():
    logger = logging.getLogger("main")

    # 每10秒增加一次loop_count
    loop_count = 0
    zbxsender_ceph_host_local = None
    zbxsender_ceph_host_db = None
    table = 'cephhost'
    nolink_count = 0

    while True:
        initdone = global_list.get_value('INITDONE')
        # 初始化未完成，继续等待
        if initdone == 'no':
            time.sleep(10)
            continue
        else:
            # 每6小时更新一次rbd块设备信息
            if loop_count == 0 or loop_count == 2160:
                user_data = dict()
                user_data['act'] = None
                user_data['page'] = 0
                user_data['pagesize'] = 0
                user_data['val'] = 0
                user_data['item'] = 0
                user_data['pool'] = None
                user_data['reqid'] = 0
                logger.debug("init done, do something pre-action...")
                flogger = logging.getLogger("image")

                ImageClt = ReqImage(dict(user_data), 0, flogger)
                ImageClt.getallstats()
                loop_count = 0

            # 检查ceph sender是否在线
            if zbxsender_ceph_host_db is None:
                # 获取leader mon
                try:
                    conn = db.db_get_conn()
                except Exception as e:
                    logger.debug("connect database failed")
                    time.sleep(10)
                    loop_count += 1
                    continue
                cu = None
                sql = 'select hostname,ipaddr from ' + table
                where = ('status=?', ['leader_mon_osd', ])
                try:
                    cu = db.db_get_cursor(conn, sql, where, None)
                    ret = cu.fetchall()
                except Exception as e:
                    logger.debug("get database data failed")
                    time.sleep(10)
                    loop_count += 1
                    continue
                # 获取主mon地址
                zbxsender_ceph_host_db = ret[0][0].encode('utf-8')
                zbxsender_ceph_host_local = zbxsender_ceph_host_db
                db.db_close(cu, conn)
                logger.debug("ceph leader mon in db=" + zbxsender_ceph_host_db)

            if zbxsender_ceph_host_local != zbxsender_ceph_host_db:
                # 之前更换过ceph sender的主机，需要检查原始主机是否恢复正常
                sshclient = sshc.mySSH(str(zbxsender_ceph_host_db))
                ret, err = sshclient.connect()
                if ret is False:
                    logger.debug('leader mon is still stopped')
                else:
                    sshclient.close()
                    logger.debug('leader mon is running now')
                    # 优先保留leader mon可用
                    if process_is_active(zbxsender_ceph_host_db) is True:
                        stop_process(zbxsender_ceph_host_local)
                        zbxsender_ceph_host_local = zbxsender_ceph_host_db
                    else:
                        logger.debug('but zbx sender in leader not normal')

            # 利用connect试探对端主机是否可用
            sshclient = sshc.mySSH(str(zbxsender_ceph_host_local))
            ret, err = sshclient.connect()
            if ret is False:
                logger.debug(" leader monitor not linked")
                time.sleep(10)
                loop_count += 1
                # if nolink_count == 6, then confirm this host is stopped now
                nolink_count += 1
                if nolink_count == 6:
                    # 连续6次判断为失联，则更换Ceph Sender发送主机
                    logger.debug(" now change the ceph sender")
                    mon_list = global_list.get_value('MON')
                    for name in mon_list:
                        if name == zbxsender_ceph_host_db or name == zbxsender_ceph_host_local:
                            continue
                        ret = start_process(name)
                        if ret is True:
                            logger.debug(" start zbx-ceph on host " + name)
                            zbxsender_ceph_host_local = name
                            nolink_count = 0
                            break
                        else:
                            logger.debug(" failed to start zbx-ceph on host " + name)
                            continue
                    if nolink_count != 0:
                        # 这种可能性不大
                        logger.debug(" no host can start zbx-ceph")
                        nolink_count = 0
                else:
                    continue
            else:
                sshclient.close()
                time.sleep(10)
                nolink_count = 0
                loop_count += 1


# 入口函数
if __name__ == "__main__":
    hosts = None
    monlist = None
    availmon = None
    db_table_taskinfo = 'taskinfo'
    exclude_flag = False
    full = 0
    nearfull = 0
    fields_define = ('class', 'type', 'act', 'cat', 'nextclass', 'nexttype', 'nextact', 'nextcat', 'status', 'reqid')

    try:
        # 配置日志
        logging.config.fileConfig(ROOT_PATH + 'conf/logging.conf')
    except Exception as e:
        print ('config logging failed, error is ' + str(e))
        #sys.exit("ceph_main_md.py error, exit...")
    else:
        logger = logging.getLogger("main")

    conffile = ROOT_PATH + "conf/config"
    # 物理机初始化是否完成
    init_phy_done = global_list.config_get(conffile, "init", "init_phy_done", logger)
    # 导入Ceph配置文件是否完成
    import_cephconf_done = global_list.config_get(conffile, "init", "import_cephconf_done", logger)
    # 物理机与Ceph初始化是否完成
    init_phyceph_done = global_list.config_get(conffile, "init", "init_phyceph_done", logger)
    # 运行模式，上线模式或测试模式
    run_mode = global_list.config_get(conffile, "init", "run_mode", logger)
    # 恢复流量上线
    max_rband = global_list.config_get(conffile, "init", "recover_band", logger)
    # 获取ssh连接用户
    ssh_user = global_list.config_get(conffile, "ssh", "ssh_username", logger)
    # 获取ssh连接端口
    ssh_port = int(global_list.config_get(conffile, "ssh", "ssh_port", logger))

    if init_phy_done is False or import_cephconf_done is False or init_phyceph_done is False \
            or run_mode is False or ssh_user is False or ssh_port is False:
        logger.error('get config file failed')
        #sys.exit("ceph_main_md.py error, exit...")
    else:
        logger.debug('init_done=' + str(init_phyceph_done))

    # 已导入过Ceph配置文件，则启动时尝试链接Ceph集群
    if import_cephconf_done == 'yes':
        conf_file = ROOT_PATH + 'conf/ceph/ceph.conf'
        try:
            config = ConfigParser.ConfigParser()
            with open(conf_file, str("r")) as cfgfile:
                config.readfp(cfgfile)
                monlist = config.get("global", "mon_initial_members").replace(' ', '').split(',')
                if config.has_option("global", "mon_osd_full_ratio"):
                    full = config.get("global", "mon_osd_full_ratio")
                else:
                    full = 0
                if config.has_option("global", "mon_osd_nearfull_ratio"):
                    nearfull = config.get("global", "mon_osd_nearfull_ratio")
                else:
                    nearfull = 0
            logger.info('get mon_initial_members success: ' + str(monlist))
            logger.info('get mon_osd_nearfull_ratio: ' + str(nearfull))
            logger.info('get mon_osd_full_ratio: ' + str(full))
        except Exception as e:
            logger.error('connect to ceph cluster failed, error is ' + str(e))
            sys.exit("ceph_main_md.py error, exit...")
        else:
            # 获取所有主机hosts
            for mon in monlist:
                sshclient = sshc.mySSH(mon, ssh_port, ssh_user)
                ret, err = sshclient.connect()
                if ret is False:
                    logger.error('connect to host %s failed, error is %s' % (mon, err))
                    sshclient.close()
                    continue
                cmd = "ceph osd tree 2>/dev/null | grep -w host | awk '{print $4}'"
                ret = sshclient.run_cmd(cmd)
                if ret['ret'] != 0:
                    logger.error('run command at host %s failed, error is %s' % (mon, ret['err']))
                    sshclient.close()
                    continue
                else:
                    hosts = [x for x in ret['out'].split('\n') if x]
                    logger.info('get ceph hosts success: ' + str(hosts))
                    availmon = mon
                    logger.info('change available monitor: ' + str(mon))
                    sshclient.close()
                    break
            if availmon is None:
                logger.error('get ceph hosts failed')
                sys.exit("ceph_main_md.py error, exit...")
    else:
        # 初始化未完成，还未导入Ceph配置
        logger.debug('import cephconf not done')

    # 初始化全局字典及线程锁，事件锁
    global_list._init()
    mutex = threading.Lock()
    Event = threading.Event()
    datalock = threading.Lock()
    journallock = threading.Lock()

    # hosts maybe None
    global_list.set_value('HOSTS', hosts)
    global_list.set_value('MON', monlist)
    global_list.set_value('AVAILMON', availmon)
    global_list.set_value('MUTEX', mutex)
    global_list.set_value('RESULTS', results)
    global_list.set_value('INITDONE', init_phyceph_done)
    global_list.set_value('RUNMODE', run_mode)
    global_list.set_value('EVENT', Event)
    global_list.set_value('DATALOCK', datalock)
    global_list.set_value('JOURNALLOCK', journallock)
    global_list.set_value('FULL', float(full))
    global_list.set_value('NEARFULL', float(nearfull))
    global_list.set_value('RBAND', float(max_rband))
    global_list.set_value('SSHUSER', ssh_user)
    global_list.set_value('SSHPORT', ssh_port)

    # 获取joblist，如之前创建过数据库表，证明后台进程非首次启动，需要获取
    # 当前有没有尚未结束的任务，从数据库读取后加载到global jobs字典
    try:
        conn = db.db_get_conn()
    except Exception as e:
        print e
        logger.error('database connection failed, error is ' + str(e))
        sys.exit("ceph_main_md.py error, exit...")

    # 获取所有任务列表，joblist是所有任务的一个汇总表
    joblist = getjobdict()

    """
    # 第一次启动，创建joblist表并初始化数据
    if not db.db_has_table(conn,db_table_joblist):
        fields_define=('class','type','act','cat','nextclass','nexttype','nextact','nextcat','status')
        db.db_create_table(conn,db_table_joblist,fields_define,None)
        # build all joblist
        rows=[fields_define]
        for v in joblist.values():
            rows.extend((item) for item in v)
        db.db_table_add_rows(conn,db_table_joblist,rows)
    """

    # 第一次启动，创建当前任务taskinfo，并写入首次任务信息
    # taskinfo中只保留当前的一条写任务，即正在执行的或未获取状态的一条写任务
    if not db.db_has_table(conn, db_table_taskinfo):
        logger.info('I think this is the first time to starting...')
        ret, err = db.db_create_table(conn, db_table_taskinfo, fields_define, [])
        if ret is False:
            logger.error("database table %s create failed, error is %s" % (db_table_taskinfo, str(err)))
            db.db_close(None, conn)
            sys.exit("ceph_main_md.py error, exit...")
        rows = [fields_define]
        # 写入首次任务，开始初始化
        if init_phyceph_done == 'yes':
            # 如果想跳过初始化，可直接修改config文件中的init_phyceph_done=yes，则会在首次启动时直接跳过初始化动作
            temp = (None, None, None, None, None, None, None, None, None, None)
        else:
            temp = list(joblist['init'][0])
            # append reqid
            temp.append(0)
            rows.append(temp)
            ret, err = db.db_table_add_rows(conn, db_table_taskinfo, rows)
            if ret is False:
                logger.error("database table %s add rows failed, error is %s" % (db_table_taskinfo, str(err)))
                db.db_close(None, conn)
                #sys.exit("ceph_main_md.py error, exit...")
        taskinfo = dict()
        for i in range(len(fields_define)):
            taskinfo[str(fields_define[i])] = temp[i]
        logger.info('write the first taskinfo success')
        db.db_close(None, conn)
    else:
        # 非首次启动
        logger.info('I think this is not the first time to starting...')
        count = db.db_table_get_count(conn, db_table_taskinfo, None)
        if count != 0:
            # 此任务为上次退出时未完成的任务，需要在本次启动后确认该动作状态
            sql = 'select * from ' + db_table_taskinfo
            cu = db.db_get_cursor(conn, sql, None, None)
            # 获取一条记录
            jobinfo = cu.fetchone()
            taskinfo = dict()
            for i in range(len(fields_define)):
                # reqid's index is 9, do not encode
                if jobinfo[i] is not None and i != 9:
                    taskinfo[str(fields_define[i])] = str(jobinfo[i]).encode('utf-8')
                else:
                    taskinfo[str(fields_define[i])] = jobinfo[i]
            logger.info('get last taskinfo=' + str(taskinfo))
            # job.check_task(taskinfo)
            db.db_close(cu, conn)
        else:
            # 后台无任务，继续
            taskinfo = dict()
            for i in range(len(fields_define)):
                taskinfo[str(fields_define[i])] = None
            db.db_close(None, conn)

    global_list.set_value('TASKINFO', taskinfo)
    global_list.set_value('JOBLIST', joblist)
    global_list.set_value('EXCLUDE', exclude_flag)

    # 启动一个Ceph句柄的监视线程，用于监视句柄的连接状态
    t_assit = threading.Thread(target=do_something)
    t_assit.setDaemon(True)
    t_assit.start()

    # 启动setband守护线程
    DataClt = ReqData(dict(), 1, logger)
    t_assit = threading.Thread(target=DataClt.setband_daemon)
    t_assit.setDaemon(True)
    t_assit.start()

    detect_file_update = threading.Thread(target=detect_file_change)
    detect_file_update.setDaemon(True)
    detect_file_update.start()


    detect_file_update = threading.Thread(target=get_rbd_info_period)
    detect_file_update.setDaemon(True)
    detect_file_update.start()

    app = web.application(urls, globals(), autoreload=True)
    app.run()

#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import logging
import logging.config
import global_variable
import json
import pdb
import threading
from centos_7_host_env import *
from com_utils import *
import database_api as db


class CephClusterEnv(object):
    def __init__(self, hosts=list(), os_config_dict={}, logger=None):
        """
        集群机器列表信息初始化/销毁
        :param hosts: 集群机器列表信息，各个host节点信息格式和内容如下：
        {'hostname':'hostname',
        'ips':{'manage_ip':manage_ip, 'public_network_ip':'public_network_ip', 'private_network_ip': 'private_network_ip'},
        'network':{'manage_network':'network_address', 'public_network':'', 'private_network', ''},
        'rock_id':'rock_id', 'ssh_user': 'ssh_user', 'ssh_port': 'ssh_port', 'ntp_server': 'ntp_server',
        'node_type': ['osd', 'mon', 'rgw'],
        'os':{'type':'centos', 'version':'version'},
        'op_type':'init_env/clear_env'}
        :param os_config_dict: os_config_dict: key为os_type+os_version,value为该版本类型host的环境配置，具体参考host_env_init.conf
         {'centos7':{'linux_source':{'epel_rpm_pkg':url, 'repo_file':url}, 'firewall':{}, 'kernel_param':{},...,request_pkg':['remove':[], 'install':[]]}}
        :param logger:
        注意: 1. 各个key对应value不能为'', {}, []等这样的空值
             2. 根据node_type来配置端口，不同类型节点，端口不同且固定或固定区间------一个host可以充当多个角色
                osd就是6800～7300，rgw就是80，mon的端口就是3300和6789
            3. os中version，当前版本考虑大版本号，比如：若version为6.4，那么这里version直接为6
        """
        self.host_count = len(hosts)
        self.host_list = list()
        self.host_env_updated_num = 0
        self.logger = logger
        self.cluster_op_status_dict = dict()
        self._init_cluster_status_dict()
        #self.cluster_op_mutex = threading.Lock()
        self.cluster_op_status_dict['host_num'] = self.host_count
        if self.host_count == 0:
            self.cluster_op_status_dict['result'] = 'finished'
            self.cluster_op_status_dict['success_updated_num'] = 0
            self.cluster_op_status_dict['error'] = 0
            self.cluster_op_status_dict['error_info'] = ''
            self.logger.info('cluster host_list is null')
        self._check_cluster_params(hosts)
        self.os_config_dict = os_config_dict
        self.cluster_ip = dict()
        # 存储所有主机的实例
        self.host_env_instances = dict()
        return

    def _init_cluster_status_dict(self):
        ## 初始化变量cluster_init_status_dict
        # finished and unfinished
        self.cluster_op_status_dict['result'] = 'unfinished'
        self.cluster_op_status_dict['host_num'] = 0
        # host_num = success_updated_num + failed_updated_num
        self.cluster_op_status_dict['success_updated_num'] = 0
        self.cluster_op_status_dict['failed_updated_num'] = 0
        self.cluster_op_status_dict[
            'success_updated_host_list'] = list()  # [hostname1, hostname2, hostname3,...]
        self.cluster_op_status_dict['failed_updated_host_list'] = list()
        self.cluster_op_status_dict['need_optmize_host_list'] = list()
        self.cluster_op_status_dict['error'] = 0
        self.cluster_op_status_dict['error_info'] = ''
        return

    def op_cluster_env(self):
        """
        并行初始化/销毁集群各个节点(这里考虑使用线程池，还是无限制创建线程------集群规模，机器配置)
        :return:
        """
        print "start op_cluster_env"
        if self.host_count == self.host_env_updated_num:
            self.cluster_op_status_dict['result'] = 'finished'
            self.logger.info('op_cluster_env: finished.')
            return
        self._collect_cluster_ips()
        if not self.os_config_dict:
            self.cluster_op_status_dict['result'] = 'finished'
            self.cluster_op_status_dict['host_num'] = -1
            self.cluster_op_status_dict['success_updated_num'] = -1
            self.cluster_op_status_dict['error'] = 1
            self.cluster_op_status_dict['error_info'] = 'cluster: os_config_list should not be []'
            self.logger.error('op_cluster_env: os_config_list should not be []')
            return

        # pdb.set_trace()
        for host_item in self.host_list:
            host_thread = None
            # 实例化所有host
            host_type_version_str = host_item['os']['type'] + str(host_item['os']['version'])
            if host_type_version_str not in global_variable.support_host_type_version_list or \
                    host_item['op_type'] not in global_variable.support_host_env_op_type:
                err_info = 'current support host env op type: ' + json.dumps(
                    global_variable.support_host_type_version_list) \
                           + ' op_type: ' + json.dumps(global_variable.support_host_env_op_type) \
                           + '. hostname: ' + host_item['hostname']
                self.logger.error(err_info)
                self.host_env_updated_num += 1
                self.cluster_op_status_dict['failed_updated_num'] += 1
                self.cluster_op_status_dict['failed_updated_host_list'].append(
                    host_item['hostname'])
                err_info_dict = dict()
                err_info_dict['error_info'] = err_info
                self.cluster_op_status_dict[host_item['hostname']] = err_info_dict
                continue
            if str(host_item['os']['type']) == 'centos':
                if host_item['os']['version'] == '7':
                    self.cluster_op_status_dict[host_item['hostname']] = dict()
                    self.host_env_instances[host_item['hostname']] = \
                        CentOs7HostEnv(host_item,
                                       self.os_config_dict[host_item['os']['type'] + host_item['os']['version']],
                                       self.cluster_ip,
                                       #logging.getLogger('host'),
                                       self.logger,
                                       Callback(self, self.notify_host_env_op_result.__name__))
                    if host_item['op_type'] == 'init_env':
                        #host_thread = threading.Thread(
                        #    target=self.host_env_instances[host_item['hostname']].init_host_env)
                        self.host_env_instances[host_item['hostname']].init_host_env()
                    else:
                        host_thread = threading.Thread(
                            target=self.host_env_instances[host_item['hostname']].clear_host_env)
                    #host_thread.daemon = True
                    self.logger.info('op_cluster_env: create thread for ' + host_item['hostname']
                                     + ' success to initialize env')
                else:
                    self.logger.error('op_cluster_env: current not support os_type: '
                                      + str(host_item['os']['type']) + ' os_version: ' + str(
                                        host_item['os']['version']))
            #if host_thread is not None:
            #    host_thread.start()
                # host_thread.run()
        return

    def _check_cluster_params(self, hosts):
        for host_item in hosts:
            tag = 0
            for key_item in global_variable.host_const_keys_info_keys:
                check_result = self._check_params(host_item, key_item)
                if check_result != 0:
                    self.cluster_op_status_dict['failed_updated_host_list'].append(
                        host_item['hostname'])
                    self.host_env_updated_num += 1
                    param_err_dict = dict()
                    param_err_dict['param'] = 'param check failed'
                    self.cluster_op_status_dict[host_item['hostname']] = param_err_dict
                    self.cluster_op_status_dict['failed_updated_num'] += 1
                    self.logger.error('_check_cluster_env: host item ' + key_item + 'error')
                    tag = 1
                    break
            if tag == 0:
                self.host_list.append(host_item)

    def _check_params(self, host_info, key='main'):
        """
        判断指定key参数是否符合预期
        :param host_info: 主机信息
        :param key: 指定key
        :return: 0:success 1:key error 2:value error
        """
        key_list = None
        key_values = None
        if key == 'main':
            key_list = host_info.keys()
            key_values = host_info.values()
        else:
            key_list = host_info[key].keys()
            key_values = host_info[key].values()
        if compare_list(key_list, global_variable.host_const_keys_info[key]) is False:
            self.logger.error('_check_params: item ' + key + ' not contain all keys error, host_item is '
                              + str(host_info)
                              + ', should be ' + str(global_variable.host_const_keys_info[key]))
            return 1
        if is_contain_null(key_values):
            self.logger.error(
                '_check_params: the value of ' + key + ' should not be "" or [] or {}, host_item is '
                + str(host_info))
            return 2
        return 0

    def _collect_cluster_ips(self):
        for key_item in global_variable.host_const_keys_info['ips']:
            self.cluster_ip[key_item] = list()
        for host_item in self.host_list:
            for key_item in global_variable.host_const_keys_info['ips']:
                self.cluster_ip[key_item].append(host_item['ips'][key_item])
        return

    def notify_host_env_op_result(self, host_env_init_status=dict()):
        """
        一旦某一个host初始化/清理状态发生改变，通知cluster
        :param host_env_init_status: 某host当前初始化/清理状态
        {'hostname': 'hostname',
        'result': 'finished/unfinished',
        'status': 'none/success/failed/need_optmize',
        'current_step': 1,
        'details': [],
        'need_optmize_steps': []}
        :return:
        """
        if host_env_init_status['result'] == 'finished':
            self.host_env_updated_num += 1
            #self.cluster_op_mutex.acquire()
            if host_env_init_status['status'] == 'success':
                self.cluster_op_status_dict['success_updated_num'] += 1
                self.cluster_op_status_dict['success_updated_host_list'].append(
                    host_env_init_status['hostname'])
            elif host_env_init_status['status'] == 'failed':
                self.cluster_op_status_dict['failed_updated_num'] += 1
                self.cluster_op_status_dict['failed_updated_host_list'].append(
                    host_env_init_status['hostname'])
            else:
                self.cluster_op_status_dict['success_updated_num'] += 1
                self.cluster_op_status_dict['need_optmize_host_list'].append(
                    host_env_init_status['hostname'])

            self.cluster_op_status_dict[host_env_init_status['hostname']] = host_env_init_status
            #self.cluster_op_mutex.release()
            self.logger.debug('notify_host_env_op_result: notify env op finished, hostname='
                              + host_env_init_status['hostname'])
            return
        else:
            #self.cluster_op_mutex.acquire()
            self.cluster_op_status_dict[host_env_init_status['hostname']] = host_env_init_status
            #self.cluster_op_mutex.release()
        self.logger.info('notify_host_env_op_result: notify env op process, hostname='
                         + host_env_init_status['hostname'])

    def save_cluster_env_op_result_to_db(self):
        """
        将集群初始化结果保存到数据库中
        :return: True:成功 False:失败
        """
        # connect database
        try:
            conn = db.db_get_conn()
        except Exception as e:
            self.logger.error("save_cluster_env_op_result_to_db: connect to database failed: " + str(e))
            return False

        # 验证表是否存在
        table_name = global_variable.cluster_env_op_result_table
        if not db.db_has_table(conn, table_name):
            ret, err = db.db_create_table(conn, table_name, global_variable.tables_info[table_name], [])
            if ret is False:
                self.logger.error("save_cluster_env_op_result_to_db: database table %s create failed, error is %s"
                                  % (table_name, str(err)))
                db.db_close(None, conn)
                return False
        rows = list()
        rows.append(global_variable.tables_info[table_name])
        row = list()
        row.append('')
        #self.cluster_op_mutex.acquire()
        row.append(self.cluster_op_status_dict['result'])
        row.append(str(self.cluster_op_status_dict['host_num']))
        row.append(str(self.cluster_op_status_dict['success_updated_num']))
        row.append(json.dumps(self.cluster_op_status_dict['success_updated_host_list']))
        row.append(json.dumps(self.cluster_op_status_dict['failed_updated_host_list']))
        row.append(json.dumps(self.cluster_op_status_dict['need_optmize_host_list']))
        row.append(json.dumps(self.cluster_op_status_dict))
        #self.cluster_op_mutex.release()
        row.append(get_local_time())
        rows.append(row)
        self.logger.info('save_cluster_env_op_result_to_db: rows contents: ' + json.dumps(rows))
        ret, err = db.db_table_add_rows(conn, table_name, rows)
        if ret is False:
            self.logger.error("save_cluster_env_op_result_to_db: insert data to table %s failed, err: %s"
                              % (table_name, err))
            db.db_close(None, conn)
            return False
        db.db_close(None, conn)
        return True

    def get_cluster_env_op_status(self):
        """
        获取整个集群目前操作(初始化/清理)结果
        :return:  完成的情况：{'result':'finished', 'detail':dict}
                 未完成的情况：{'result':'unfinished', 'detail':{}}
        """
        result = dict()
        self.logger.info('get_cluster_env_op_status: get current cluster env init status success')
        if self.host_env_updated_num == self.host_count:
            #self.cluster_op_mutex.acquire()
            self.cluster_op_status_dict['result'] = 'finished'
            result['detail'] = self.cluster_op_status_dict
            #self.cluster_op_mutex.release()
            result['result'] = 'finished'
            # 将结果存入数据库
            if self.save_cluster_env_op_result_to_db() is True:
                self.logger.info("get_cluster_env_op_status: save to db success.")
            else:
                self.logger.error('get_cluster_env_op_status: save to db failed.')
            return result
        result['result'] = 'unfinished'
        result['detail'] = '{}'
        return result

    def get_cluster_env_op_detail(self):
        """
        获取整个集群目前操作(初始化/清理)的详细信息
        :return: json-format结果
        """
        #self.cluster_op_mutex.acquire()
        ret = json.dumps(self.cluster_op_status_dict)
        #self.cluster_op_mutex.release()
        self.logger.info('get_cluster_env_op_detail: get current cluster env op detail success')
        return ret

    def get_one_host_env_op_status(self, hostname):
        """
        获取指定hostname机器环境初始化/清理结果
        :param hostname: 机器名称
        :return: dict类型，若完成初始化/清理，返回初始化/清理所有信息，
                 否则返回{'hostname':'hostname', 'result':'unfinished', 'current_step':current_step}
        """
        host_env_op_instance = self.host_env_instances[hostname]
        return host_env_op_instance.get_host_env_status()

    def get_one_host_env_op_detail(self, hostname):
        """
        获取指定hostname机器环境操作(初始化/清理)详情
        :param hostname: 机器名称
        :return: dict 当前初始化/清理的详细信息
        """
        host_env_op_instance = self.host_env_instances[hostname]
        return host_env_op_instance.get_host_env_detail()

    def get_cluster_env_op_failed_hosts_detail(self):
        """
        获取集群环境初始化中，初始化/清理失败的hosts详细信息
        :return: josn-format result: {'hostname1': 'details', 'hostname2': 'details',...}
        """
        result = dict()
        #self.cluster_op_mutex.acquire()
        for host_item in self.cluster_op_status_dict['failed_updated_host_list']:
            result[host_item] = self.cluster_op_status_dict[host_item]
        #self.cluster_op_mutex.release()
        self.logger.info('get_cluster_env_op_failed_hosts_detail: get current cluster env failed detail.')
        return json.dumps(result)


"""
test code
"""
if __name__ == "__main__":
    hosts = list()
    """
    {'hostname': 'hostname',
     'ips': {'manage_ip': manage_ip, 'public_network_ip': 'public_network_ip',
             'private_network_ip': 'private_network_ip'},
     'network': {'manage_network': 'network_address', 'public_network': '', 'private_network', ''},
    'rock_id': 'rock_id', 'ssh_user': 'ssh_user', 'ssh_port': 'ssh_port', 'ntp_server': 'ntp_server',
    'node_type': ['osd', 'mon', 'rgw'],
    'os': {'type': 'centos', 'version': 'version'},
    'op_type':'init_env/clear_env'}
    """
    test_host_0 = dict()
    test_host_0['hostname'] = 'test-env-js03-ceph-10e39e48e34'  # test1
    test_host_0['ips'] = dict()
    test_host_0['ips']['manage_ip'] = '10.39.56.34'
    test_host_0['ips']['public_network_ip'] = '10.39.48.34'
    test_host_0['ips']['private_network_ip'] = '10.39.101.18'
    test_host_0['network'] = dict()
    test_host_0['network']['manage_network'] = '10.39.56.34/21'
    test_host_0['network']['public_network'] = '10.39.48.34/21'
    test_host_0['network']['private_network'] = '10.39.101.18/20'
    test_host_0['rock_id'] = '1'
    #test_host_0['root_pass'] = '123qwe'
    test_host_0['ssh_user'] = 'root'
    test_host_0['ssh_port'] = 10000
    test_host_0['ntp_server'] = '10.39.111.239'
    test_host_0['node_type'] = list()
    test_host_0['node_type'].append('osd')
    test_host_0['node_type'].append('mon')
    test_host_0['os'] = dict()
    test_host_0['os']['type'] = 'centos'
    test_host_0['os']['version'] = '7'
    #test_host_0['op_type'] = 'clear_env'
    test_host_0['op_type'] = 'init_env'
    hosts.append(test_host_0)

    test_host_1 = dict()
    test_host_1['hostname'] = 'test-env-js03-ceph-10e39e48e35'  # test1
    test_host_1['ips'] = dict()
    test_host_1['ips']['manage_ip'] = '10.39.56.35'
    test_host_1['ips']['public_network_ip'] = '10.39.48.35'
    test_host_1['ips']['private_network_ip'] = '10.39.101.19'
    test_host_1['network'] = dict()
    test_host_1['network']['manage_network'] = '10.39.56.35/21'
    test_host_1['network']['public_network'] = '10.39.48.35/21'
    test_host_1['network']['private_network'] = '10.39.101.19/20'
    test_host_1['rock_id'] = '1'
    #test_host_1['root_pass'] = '123qwe'
    test_host_1['ssh_user'] = 'root'
    test_host_1['ssh_port'] = 10000
    test_host_1['ntp_server'] = '10.39.31.239'
    test_host_1['node_type'] = list()
    test_host_1['node_type'].append('osd')
    test_host_1['node_type'].append('mon')
    test_host_1['os'] = dict()
    test_host_1['os']['type'] = 'centos'
    test_host_1['os']['version'] = '7'
    #test_host_1['op_type'] = 'clear_env'
    test_host_1['op_type'] = 'init_env'
    hosts.append(test_host_1)

    test_host_2 = dict()
    test_host_2['hostname'] = 'test-env-js03-ceph-10e39e48e36'
    test_host_2['ips'] = dict()
    test_host_2['ips']['manage_ip'] = '10.39.56.36'
    test_host_2['ips']['public_network_ip'] = '10.39.48.36'
    test_host_2['ips']['private_network_ip'] = '10.39.101.20'
    test_host_2['network'] = dict()
    test_host_2['network']['manage_network'] = '10.39.56.36/21'
    test_host_2['network']['public_network'] = '10.39.48.36/21'
    test_host_2['network']['private_network'] = '10.39.101.20/20'
    test_host_2['rock_id'] = '1'
    #test_host_2['root_pass'] = '123qwe'
    test_host_2['ssh_user'] = 'root'
    test_host_2['ssh_port'] = 10000
    test_host_2['ntp_server'] = '10.39.31.239'
    test_host_2['node_type'] = list()
    test_host_2['node_type'].append('osd')
    test_host_2['node_type'].append('mon')
    test_host_2['os'] = dict()
    test_host_2['os']['type'] = 'centos'
    test_host_2['os']['version'] = '7'
    #test_host_2['op_type'] = 'clear_env'
    test_host_2['op_type'] = 'init_env'
    hosts.append(test_host_2)
    """
    {'linux_source':{'epel_rpm_pkg':url, 'repo_file':url},
        'kernel_param':[{'kernel.pid_max':'4194303', 'vm.swappiness':'0', 'file':'', 'fs.file-max':'1310710'], {'file':'', 'soft_limit':'1024000', 'hard_limit':'1024000'}]
        'request_pkg':{'remove':'pkg1 pkg2', 'install':'pkg1 pkg2 pkg3'}},
        'disk_optimize':{'source_file':'file_path', 'dest_file_path':'dest_file_path'},
        'ssd_break_bind':{'source_file':'file_path', 'dest_file_path':'dest_file_path'}
        }
    """
    os_dict = dict()
    os_dict['centos7'] = dict()
    os_dict['centos7']['linux_source'] = dict()
    # os_dict['centos7']['linux_source']['epel_rpm_pkg'] = './epel-release-7-8.noarch.rpm'
    os_dict['centos7']['linux_source']['repo_file'] = './CentOS-Base.repo'
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
    os_dict['centos7']['request_pkg']['remove'] = 'firewalld NetworkManager'
    os_dict['centos7']['request_pkg']['install'] = 'iptables-services ntp hdparm smartmontools bc gdisk nvme-cli ceph'
    os_dict['centos7']['disk_optimize'] = dict()
    os_dict['centos7']['disk_optimize']['source_file'] = './disk-optimize.sh'
    os_dict['centos7']['disk_optimize']['dest_file_path'] = '/usr/local/bin/'
    os_dict['centos7']['ssd_break_bind'] = dict()
    os_dict['centos7']['ssd_break_bind']['source_file'] = './bind_nvme_irq.sh'
    os_dict['centos7']['ssd_break_bind']['dest_file_path'] = '/usr/local/bin/'
    os_dict['centos7']['timezone'] = dict()
    os_dict['centos7']['timezone']['continent'] = 'Asia'
    os_dict['centos7']['timezone']['city'] = 'Shanghai'
    logger = None

    try:
        # 配置日志
        logging.config.fileConfig('./logging.conf')
    except Exception as e:
        print('config logging failed, error is ' + str(e))
    else:
        logger = logging.getLogger('main')
    ceph_cluster_env_init_obj = CephClusterEnv(hosts, os_dict, logger)
    ceph_cluster_env_init_obj.op_cluster_env()
    while (1):
        print("======================================================")
        ret = ceph_cluster_env_init_obj.get_cluster_env_op_status()
        # pdb.set_trace()
        if ret['result'] == 'finished':
            print(json.dumps(ret))
            break
        print("result: " + json.dumps(ret))
        print("detail: " + ceph_cluster_env_init_obj.get_cluster_env_op_detail())
        time.sleep(10)

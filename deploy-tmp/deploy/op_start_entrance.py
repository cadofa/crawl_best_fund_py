#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import pdb
import logging
import logging.config
import argparse
import xlrd
import json
import time
import sys

from ceph_cluster_env import CephClusterEnv

reload(sys)
sys.setdefaultencoding("utf-8")


def check_index(start_index, end_index, max_index):
    if start_index < 2 or end_index >= max_index:
        err_info = 'param error: start_index not smaller than two or end_index should not bigger than ' + str(max_index)
        return False, err_info
    if start_index > end_index:
        err_info = 'param error: start_index should be smaller than end_index.'
        return False, err_info
    return True, None


def check_op(op):
    tag = 0
    if int(op) == 0:
        op_type = 'init_env'
    elif int(op) == 1:
        op_type = 'clear_env'
    else:
        tag = 1
        op_type = 'none'
    if tag == 1:
        return False, 'op param should be 0 or 1, not should be ' + str(op)
    return True, op_type


def check_role(role):
    role_list = list()
    err_info_list = list()
    role_dict = dict()
    role_dict['mon'] = 0
    role_dict['osd'] = 0
    role_dict['rgw'] = 0
    for role_letter in role:
        if role_letter == 'm':
            role_dict['mon'] += 1
            if role_dict['mon'] > 1:
                continue
            role_list.append('mon')
        elif role_letter == 'o':
            role_dict['osd'] += 1
            if role_dict['osd'] > 1:
                continue
            role_list.append('osd')
        elif role_letter == 'r':
            role_dict['rgw'] += 1
            if role_dict['rgw'] > 1:
                continue
            role_list.append('rgw')
        else:
            err_info_list.append('role letter should not be ' + str(role_letter))
    if len(err_info_list) > 0:
        return False, err_info_list
    return True, role_list


def construct_host_dict(hostname, manage_ip, manage_ip_mask, public_network_ip, public_network_mask, private_network_ip,
                        private_network_mask):
    host_dict = dict()
    host_dict['hostname'] = hostname
    host_dict['ips'] = dict()
    host_dict['ips']['manage_ip'] = manage_ip
    host_dict['ips']['public_network_ip'] = public_network_ip
    host_dict['ips']['private_network_ip'] = private_network_ip
    host_dict['network'] = dict()
    host_dict['network']['manage_network'] = manage_ip_mask
    host_dict['network']['public_network'] = public_network_mask
    host_dict['network']['private_network'] = private_network_mask
    host_dict['rock_id'] = '1'
    host_dict['ssh_user'] = 'root'
    host_dict['os'] = dict()
    host_dict['os']['type'] = 'centos'
    host_dict['os']['version'] = '7'
    return host_dict


def construct_hosts_dict_list(input_hosts_file, start_index, end_index, op, role, ntp_server, ssh_port):
    host_list = list()
    work_book = xlrd.open_workbook(input_hosts_file)
    sheet_data = work_book.sheet_by_name("OpenStack平台")
    lines_num = sheet_data.nrows
    if lines_num <= 0:
        err_info = 'file: ' + input_hosts_file + ' : no hosts data. excel file rows is ' + str(lines_num)
        return False, err_info
    start_index = int(start_index)
    end_index = int(end_index)
    ret, err_info = check_index(start_index, end_index, lines_num)
    if ret is False:
        return False, err_info
    ret, info = check_op(op)
    if ret is False:
        return False, info
    op_type = info
    ret, info = check_role(role)
    if ret is False:
        return False, json.dumps(info)
    role_list = info
    if str(sheet_data.cell_value(0, 1)) == "主机位置" and str(sheet_data.cell_value(0, 4)) == '管理网段' and str(
            sheet_data.cell_value(1, 5)) == "IP地址" and str(sheet_data.cell_value(1, 6)) == '子网掩码' and str(
        sheet_data.cell_value(0, 7)) == '存储外网网段' and str(sheet_data.cell_value(1, 8)) == 'IP地址' and str(
        sheet_data.cell_value(1, 9)) == "子网掩码" and str(sheet_data.cell_value(0, 10)) == '存储内网' and str(
        sheet_data.cell_value(1, 11)) == 'IP地址' and str(sheet_data.cell_value(1, 12)) == "子网掩码":
        for i in range(start_index, end_index):
            host_dict = construct_host_dict(str(sheet_data.cell_value(i, 1)), str(sheet_data.cell_value(i, 5)),
                                            str(sheet_data.cell_value(i, 6)), str(sheet_data.cell_value(i, 8)),
                                            str(sheet_data.cell_value(i, 9)), str(sheet_data.cell_value(i, 11)),
                                            str(sheet_data.cell_value(i, 12)))
            host_dict['ssh_port'] = ssh_port
            host_dict['ntp_server'] = ntp_server
            host_dict['node_type'] = role_list
            host_dict['op_type'] = op_type
            host_list.append(host_dict)
    return True, host_list


# think about reading from config file
def config_os_env():
    os_dict = dict()
    os_dict['centos7'] = dict()
    os_dict['centos7']['linux_source'] = dict()
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
    os_dict['centos7']['request_pkg']['remove'] = 'firewalld NetworkManager chrony'
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
    return os_dict


#parser = argparse.ArgumentParser(description='ceph cluster env init or clear')
#parser.add_argument('--input_hosts_file', '-i',
#                    help='input_hosts_file attribute, xlsx format file to save hosts info, necessary param',
#                    required=True)
#parser.add_argument('--start_index', '-s',
#                    help='start_index attribute, one line indicate one host, read host info from this start '
#                         'index, necessary param,  the value is not smaller than two', required=True)
#parser.add_argument('--end_index', '-e', help='end_index attribute, the end host to init or clear, necessary param',
#                    required=True)
#parser.add_argument('--op', '-o',
#                    help='op attribute, operation, value is 0 or 1, 0 indicates "init" and 1 indicates "clear", '
#                         'necessary param', required=True)
#parser.add_argument('--role', '-r',
#                    help="role attribute, host's role, value can be m, o or r, indicate: mon, osd, rgw, also can"
#                         " be any combination of the three letters, if repeat, only use the first, necessary param",
#                    required=True)
#parser.add_argument('--ntp_server', '-n', help='ntp_server attribute, the ip address of ntp server, necessary param',
#                    required=True)
#parser.add_argument('--ssh_port', '-p', help='ssh_port attribute, access host through this port, necessary param',
#                    required=True)
#args = parser.parse_args()

if __name__ == '__main__':
    host_list = None
    logger = None
    try:
        print "get logger"
        logging.config.fileConfig('./logging.conf')
        logger = logging.getLogger('main')
        print "already get logger"
        #ret, info = construct_hosts_dict_list(args.input_hosts_file, args.start_index, args.end_index, args.op,
        #                                      args.role, args.ntp_server, args.ssh_port)
        #for test
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
        ceph_cluster_env_init_obj = CephClusterEnv(host_list, os_dict, logger)
        print "self start op_cluster_env()"
        ceph_cluster_env_init_obj.op_cluster_env()
        #while True:
        #    ret = ceph_cluster_env_init_obj.get_cluster_env_op_status()
        #    if ret['result'] == 'finished':
        #        print(json.dumps(ret))
        #        break
        #    print("result: " + json.dumps(ret))
        #    #print("detail: " + ceph_cluster_env_init_obj.get_cluster_env_op_detail())
        #    time.sleep(1)
    else:
        print('len(host_list) is zero')

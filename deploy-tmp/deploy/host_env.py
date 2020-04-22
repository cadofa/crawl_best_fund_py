#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import json
import logging
import logging.config
import os
import pdb
from subprocess import Popen, PIPE, STDOUT

import global_variable
import parse_config
import paramiko_api as sshc
from com_utils import get_local_time, get_timestamp


class HostEnv(object):
    def __init__(self, host_info, os_config=dict(), cluster_ips=dict(), logger=None, call_back_function=None):
        """
        机器环境初始化
        :param host_info: 机器信息，格式：
        {'hostname':'hostname',
        'ips':{'manage_ip':manage_ip, 'public_network_ip':'public_network_ip', 'private_network_ip': 'private_network_ip'},
        'network':{'manage_network':'network_address', 'public_network':'', 'private_network', ''},
        'rock_id':'rock_id', 'ssh_user': 'ssh_user', 'ssh_port': 'ssh_port', 'ntp_server': 'ntp_server',
        'node_type': ['osd', 'mon', 'rgw'],
        'os':{'type':'centos', 'version':'version'}}
        :param os_config: 机器初始化配置信息-json格式
        {'linux_source':{'epel_rpm_pkg':url, 'repo_file':url},
        'firewall':{},
        'kernel_param':{},...,
        'request_pkg':{'remove':'pkg1 pkg2', 'install':'pkg1 pkg2 pkg3'}},
        'disk_optimize':{'source_file':'file_path', 'dest_file_path':'dest_file_path'},
        'ssd_break_bind':{'source_file':'file_path', 'dest_file_path':'dest_file_path'}
        }
        :param call_back_function: 配置过程中，回调，一旦某个初始化状态发生改变，可立即将状态信息通知调用者
        """
        self.host_info = host_info
        self.os_config = os_config
        self.call_back_fn = call_back_function
        self.ssh_client = None
        self.cluster_ips = cluster_ips
        # host_init_status_dict对host各项环境初始化状态进行记录
        self.host_status_dict = dict()
        self.logger = logger

    def _init_system_var(self):
        """
        初始化host_init_status_dict和ssh_client
        1. 初始化变量host_init_status_dict
        {'hostname': 'hostname',
        'result': 'finished/unfinished',
        'status': 'none/success/failed/need_optmize',
        'current_step': 1,
        'details': [],
        'need_optmize_steps': []}
        2. 判断是否可以免密登录
        3. 实例化ssh_client
        :return: True or False前者表示成功，后者表示失败------ssh连接建立失败
        """
        # 初始化变量host_init_status_dict
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
                return False

        if self._get_ssh_instance() is False:
            self.logger.error("HostEnv::_init_system_var: ssh connect failed, hostname is "
                              + self.host_info['hostname'])
            return False
        self.logger.info("HostEnv::_init_system_var: get ssh_client instance success.")
        return True

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

    def _reget_ssh_instance(self):
        """
        重新获取ssh_client实例
        :return: True, None: 成功 False, err_info: 失败
        """
        self.logger.debug("HostEnv::_reget_ssh_instance: ssh_client is None.")
        if self._get_ssh_instance() is False:
            err_info = "HostEnv::_reget_ssh_instance: ssh connect failed, hostname is " \
                       + self.host_info['hostname']
            self.logger.error(err_info)
            return False, err_info
        return True, None

    def _check_network(self):
        """
        检查各个节点之间连通性
        :return: True, None 联通
                 False, dict()不连通且不连通的ip列表
        """
        err_dict = dict()
        is_error = 0
        # pdb.set_trace()
        for key_item in global_variable.host_const_keys_info['ips']:
            err_dict[key_item] = list()
            for ip_item in self.cluster_ips[key_item]:
                ret, info = self._run_command('ping -c 4 ' + ip_item)
                if ret is False:
                    info = 'HostEnv::_check_network: execute cmd failed, ' + info
                    self.logger.error(info)
                    is_error = 1
                if info.find('4 received') <= 0 and info.find('3 received') <= 0 \
                        and info.find('2 received') <= 0 and info.find('1 received') <= 0:
                    err_dict[key_item].append(ip_item)
                    is_error = 1
        if is_error is 0:
            return True, None
        else:
            return False, err_dict

    def reboot_host(self):
        """
        配置完成后，重启机器
        :return: True, None: 成功 False, err_info: 失败
        """
        err_info = None
        if self.ssh_client is None:
            ret, err_info = self._reget_ssh_instance()
            if ret is False:
                return False, err_info
        ret, err_info = self._run_command('reboot -f > /dev/null 2>&1 &')
        if ret is False:
            err_info = "HostEnv::reboot_host: execute reboot cmd error."
            self.logger.error(err_info)
            return False, err_info
        return True, err_info

    def _del_line_file(self, filename, del_str):
        """
        删除文件中包含del_str的行
        :param filename: 文件名(路径+文件名)
        :param del_str: 指定字符串
        :return: True, None成功 False, err_info失败
        """
        if del_str == "":
            err_info = "HostEnv::_del_line: del_str should not be empty. "
            self.logger.error(err_info)
            return False, err_info
        cmd = "sed -i -e '/" + del_str + "/d' " + filename
        ret, err_info = self._run_command(cmd)
        if ret is False or err_info.find("No such file or directory") >= 0:
            err_info = "ostEnvInit::_del_line: " + err_info
            self.logger.error(err_info)
            return False, err_info
        return True, None

    def _add_line_file(self, filename, add_str):
        """
        在文件filename中追加一行，其内容为add_str
        :param filename: 文件名(路径+文件名)
        :param add_str: 要追加的一行内容
        :return: True, None成功 False, err_info失败
        """
        cmd = "echo '" + add_str + "' >> " + filename
        ret, err_info = self._run_command(cmd)
        if ret is False:
            err_info = "HostEnvInit::_add_line_file: " + err_info
            self.logger.error(err_info)
            return False, err_info
        return True, None

    def check_hostname(self):
        """
        检查hostname是否与给定hostname一致
        1. 执行命令hostname，查看结果是否与给定hostname相同
        2. 执行命令cat /etc/hostname，查看结果是否与给定hostname相同
        :return: True: 一样 False: 不一样
        """
        err_info = None
        if self.ssh_client is None:
            ret, err_info = self._reget_ssh_instance()
            if ret is False:
                return False
        # execute hostname cmd
        ret, info = self._run_command('hostname')
        if ret is False:
            info = "HostEnv::check_hostname: " + info
            self.log.error(info)
            return False
        if info != self.host_info['hostname']:
            self.logger.info("HostEnv::check_hostname: need set hostname.")
            return False
        # execute cat /etc/hostname cmd
        ret, info = self._run_command('cat /etc/hostname')
        if ret is False:
            info = "HostEnv::check_hostname: " + info
            self.log.error(info)
            return False
        if info != self.host_info['hostname']:
            self.logger.info("HostEnv::check_hostname: need set hostname.")
            return False
        return True

    def set_hostname(self):
        """
        初始化机器名
        :return: True, None 成功  False, err_info: 失败
        """
        err_info = None
        if self.ssh_client is None:
            ret, err_info = self._reget_ssh_instance()
            if ret is False:
                return False, err_info
        if self.check_hostname() is False:
            cmd = 'hostname ' + self.host_info['hostname'] + ' && echo ' + self.host_info[
                'hostname'] + ' > /etc/hostname'
            ret, err_info = self._run_command(cmd)
            if ret is False:
                err_info = "HostEnv::set_hostname: " + err_info
                self.logger.error(err_info)
                return False, err_info
            self.logger.info("HostEnv::set_hostname: set hostname success.")
            return True, err_info
        self.logger.info("HostEnv::set_hostname: not need set hostname.")
        return True, err_info

    def init_linux_source(self):
        """
        yum source file or rpm package path config in os_config variable in dict.
        :return: True: success False: failed
        """
        pass

    def set_disk_optmize_script(self):
        """
        设置磁盘参数优化脚本
        'disk_optimize':{'source_file':'file_path', 'dest_file_path':'dest_file_path'}
        :return: True, None成功 False, err_info
        """
        err_info = None
        if 'disk_optimize' in self.os_config.keys():
            keys = self.os_config['disk_optimize'].keys()
            if 'source_file' not in keys or 'dest_file_path' not in keys:
                err_info = 'HostEnv::set_disk_optmize_script: keys not enough, keys= ' + str(keys)
                return False, err_info
            else:
                return self.set_hard_disk_script(self.os_config['disk_optimize']['source_file'],
                                                 self.os_config['disk_optimize']['dest_file_path'])
        else:
            self.logger.info("HostEnv::set_disk_optmize_script: not need config disk_optimize")
        return True, None

    def clear_hard_disk_script(self, filename, dest_path):
        """
        清除硬盘文件配置
        :param filename: 文件名---不包括路径
        :param dest_path: 目标路径
        :return:
        """
        if filename == '' or dest_path.endswith('/') is False \
                or dest_path.startswith('/') is False:
            self.logger.error('HostEnv::clear_hard_disk_script: params should not reasonable')
            return False, 'HostEnv::clear_hard_disk_script: params error'
        err_info = None
        if self.ssh_client is None:
            ret, err_info = self._reget_ssh_instance()
            if ret is False:
                return False, err_info
        # del config file
        dest_file = dest_path + filename
        cmd = 'rm -rf ' + dest_file
        ret, err_info = self._run_command(cmd)
        if ret is False:
            return False, err_info
        # clear config
        ret, err_info = self._del_line_file('/etc/rc.d/rc.local', filename)
        if ret is False:
            return False, err_info
        return True, None

    def clear_disk_optmize_script(self):
        if 'disk_optimize' in self.os_config.keys():
            keys = self.os_config['disk_optimize'].keys()
            if 'source_file' not in keys or 'dest_file_path' not in keys:
                err_info = 'HostEnv::clear_disk_optmize_script: keys not enough, keys= ' + str(keys)
                return False, err_info
            else:
                files = self.os_config['disk_optimize']['source_file'].split('/')
                filename = None
                if len(files) > 0:
                    filename = files[len(files) - 1]
                else:
                    filename = files[0]
                return self.clear_hard_disk_script(filename,
                                                   self.os_config['disk_optimize']['dest_file_path'])
        else:
            self.logger.info("HostEnv::clear_disk_optmize_script: not need clear disk_optimize")
        return True, None

    def set_ssd_break_bind_script(self):
        """
        设置ssd中断绑定脚本
        'ssd_break_bind':{'source_file':'file_path', 'dest_file_path':'dest_file_path'}
        :return: True, None成功 False, err_info
        """
        err_info = None
        if 'ssd_break_bind' in self.os_config.keys():
            keys = self.os_config['ssd_break_bind'].keys()
            if 'source_file' not in keys or 'dest_file_path' not in keys:
                err_info = 'HostEnv::set_ssd_break_bind_script: keys not enough, keys= ' + str(keys)
                return False, err_info
            else:
                return self.set_hard_disk_script(self.os_config['ssd_break_bind']['source_file'],
                                                 self.os_config['ssd_break_bind']['dest_file_path'])
        else:
            self.logger.info("HostEnv::set_ssd_break_bind_script: not need config ssd_break_bind")
        return True, None

    def clear_ssd_break_bind_script(self):
        self.logger.info("clear ssd break bind script success")
        if 'ssd_break_bind' in self.os_config.keys():
            keys = self.os_config['ssd_break_bind'].keys()
            if 'source_file' not in keys or 'dest_file_path' not in keys:
                err_info = 'HostEnv::clear_ssd_break_bind_script: keys not enough, keys= ' + str(keys)
                return False, err_info
            else:
                files = self.os_config['ssd_break_bind']['source_file'].split('/')
                filename = None
                if len(files) > 0:
                    filename = files[len(files) - 1]
                else:
                    filename = files[0]
                return self.clear_hard_disk_script(filename,
                                                   self.os_config['ssd_break_bind']['dest_file_path'])
        else:
            self.logger.info("HostEnv::clear_ssd_break_bind_script: not need clear ssd_break_bind")
        return True, None

    def set_hard_disk_script(self, local_path, dest_path):
        """
        配置/优化磁盘操作
        :param local_path: 本地要复制的文件路径
        :param dest_path: 将配置脚本存放的目标路径(目标),eg:/usr/local/bin/ 最后必须包含“/”
        :return: True, None:成功 False, err_info：失败
        """
        self.logger.info("HostEnv::set_hard_disk_script")
        if local_path == '' or dest_path == '' or dest_path.endswith('/') is False \
                or dest_path.startswith('/') is False:
            self.logger.error('HostEnv::set_hard_disk_script: params should not reasonable')
            return False, 'HostEnv::set_hard_disk_script: params error'
        files = local_path.split('/')
        filename = None
        if len(files) > 0:
            filename = files[len(files) - 1]
        else:
            filename = files[0]
        cmd = 'sudo scp -P ' + str(self.host_info['ssh_port']) + ' ' + local_path + ' ' + self.host_info['hostname'] \
              + ':/home/'
        com_result_list = self._run_popen_cmd(cmd)
        if len(com_result_list) > 0 and com_result_list[0].strip().find("No such file or directory") >= 0:
            err_info = "set_hard_disk_script: execute " + cmd + " error, " + com_result_list[0].strip()
            self.logger.error(err_info)
            return False, err_info 
        #ret, err_info = self._scp_file(cmd)
        #if ret is False:
        #    self.logger.error(err_info)
        #    return False, err_info

        err_info = None
        if self.ssh_client is None:
            ret, err_info = self._reget_ssh_instance()
            if ret is False:
                return False, err_info
        dest_file = dest_path + filename
        cmd = 'yes | cp /home/' + filename + ' ' + dest_path
        ret, err_info = self._run_command(cmd)
        if ret is False:
            return False, err_info
        cmd = 'chown root:root ' + dest_file + ' && chmod +x /etc/rc.d/rc.local ' + dest_file
        ret, err_info = self._run_command(cmd)
        if ret is False:
            return False, err_info
        # avoid repeat
        ret, err_info = self._del_line_file('/etc/rc.d/rc.local', filename)
        if ret is False:
            return False, err_info
        ret, err_info = self._add_line_file('/etc/rc.d/rc.local', 'sh ' + dest_file)
        if ret is False:
            return False, err_info
        # execute
        ret, err_info = self._run_command('sh ' + dest_file)
        if ret is False:
            return False, err_info
        return True, None

    def _run_command(self, cmd):
        """
        执行指定的命令
        :param cmd:
        :return: True, result:成功 False, err_info：失败
        """
        ret = self.ssh_client.run_cmd(cmd)
        if ret['ret'] == -1:
            err_info = "HostEnv::_run_command: execute cmd: " + cmd + " error."
            self.logger.error(err_info)
            return False, err_info
        return True, ret['out'].strip()

    def _multi_run_command(self, cmd):
        """
        命令执行失败时，多次执行命令
        :param cmd: 命令
        :return: True, None: 执行成功 False, err_info: 失败
        note: 这些命令执行时，首次执行容易失败
        """
        retry_times = 0
        if cmd == "":
            err_info = "cmd should not ''"
            self.logger.error(err_info)
            return False, err_info
        while True:
            ret, info = self._run_command(cmd)
            if ret is False:
                self.logger.error(info)
                return False, info
            if info.find("OK") >= 0 or info.find("enabled") >= 0:
                self.logger.info("execute " + cmd + " success")
                break
            elif info == "active":
                self.logger.info("execute " + cmd + " success")
                break
            else:
                self.logger.debug("execute " + cmd + " failed, err_info: " + info)
                self.logger.debug("retrying ...")
                retry_times += 1
                if retry_times >= global_variable.CMD_RETRY_TIMES_CONST:
                    err_info = "execute '" + cmd + "' error, retry times to max " + str(retry_times)
                    self.logger.error(err_info)
                    return False, err_info
        return True, None

    def set_selinux(self):
        """
        配置SELINUX
        :return: True, None: success False, err_info: fail
        """
        ret, err_info = self._del_line_file('/etc/selinux/config', '^SELINUX=')
        if ret is False:
            err_info = 'HostEnv::set_selinux: invoke _del_line_file error, ' + err_info
            self.logger.error(err_info)
            return False, err_info
        ret, err_info = self._add_line_file('/etc/selinux/config', 'SELINUX=disabled')
        if ret is False:
            err_info = 'HostEnv::set_selinux: invoke _add_line_file error, ' + err_info
            return False, err_info
        self.logger.info("HostEnv::set_selinux: set selinux config success.")
        return True, None

    def recover_selinux(self):
        ret, err_info = self._del_line_file('/etc/selinux/config', '^SELINUX=')
        if ret is False:
            err_info = 'HostEnv::set_selinux: invoke _del_line_file error, ' + err_info
            self.logger.error(err_info)
            return False, err_info
        ret, err_info = self._add_line_file('/etc/selinux/config', 'SELINUX=enforcing')
        if ret is False:
            err_info = 'HostEnv::set_selinux: invoke _add_line_file error, ' + err_info
            return False, err_info
        self.logger.info("HostEnv::set_selinux: set selinux config success.")
        return True, None

    def check_bandwidth(self):
        """
        检测带宽
        :return:
        """
        self.logger.info("HostEnv::check_bandwidth: check_bandwidth")
        return True, None

    def get_host_env_status(self):
        """
        获取主机环境初始化结果
        :return: dict类型
        """
        init_status = dict()
        if self.host_status_dict['result'] == 'finished':
            return self.host_status_dict
        else:
            init_status['hostname'] = self.host_info['hostname']
            init_status['result'] = 'unfinished'
            init_status['current_step'] = self.host_status_dict['current_step']
            return init_status

    def _scp_file(self, cmd):
        """
        执行scp命令，从本地拷贝文件到远程机器
        :param cmd: 命令
        :return: True, None 成功 False, err_info 失败
        """
        ret = Popen(cmd, stdout=PIPE, stderr=STDOUT, shell=True)
        cmd_result = ret.stdout.readline().strip()
        if cmd_result.find('No such file or directory') >= 0:
            ret.stdout.close()
            err_info = "HostEnv::_scp_file: " + cmd + " result: " + cmd_result
            self.logger.error(err_info)
            return False, err_info
        ret.stdout.close()
        return True, None

    def _run_popen_cmd(self, cmd):
        """
        执行popen命令
        :param cmd: 要执行的命令
        :return: 命令输出
        """
        print "cmd", cmd
        ret = Popen(cmd, stdout=PIPE, stderr=STDOUT, shell=True)
        print "ret", ret
        cmd_result_list = ret.stdout.readlines()
        print "cmd_result_list", cmd_result_list
        ret.stdout.close()
        return cmd_result_list

    def get_host_env_detail(self):
        """
        返回当前初始化详情
        :return: dict类型
        """
        return self.host_status_dict

    def _handle_result(self, step, detail, tag=0):
        """
        处理各个步骤执行结果
        :param step: 步骤号
        :param detail: 该步执行结果详情
        :param tag: 0：执行成功，1：需要优化，2：表示执行失败
        :return:
        """
        step_result = dict()
        step_result['step'] = int(step)
        step_result['result'] = 'finished'
        step_result['step_detail'] = detail
        step_result['time'] = get_local_time()
        if tag == 2:
            step_result['status'] = 'failed'
            self.host_status_dict['result'] = 'finished'
            self.host_status_dict['status'] = 'failed'
            self.ssh_client.close()
        elif tag == 1:
            step_result['status'] = 'need_optmize'
            self.host_status_dict['need_optmize_steps'].append(step_result)
        else:
            step_result['status'] = 'success'
        is_finish = (step == int(global_variable.HostEnvClearSteps.REBOOT) and self.host_info['op_type'] == 'clear_env')
        is_finish = (is_finish or step == int(global_variable.HostEnvInitSteps.REBOOT))
        if is_finish is True:
            self.host_status_dict['result'] = 'finished'
            if self.host_status_dict['status'] is not 'need_optmize':
                self.host_status_dict['status'] = 'success'
            if self.ssh_client is not None:
                self.ssh_client.close()
        self.host_status_dict['details'].append(step_result)
        self.call_back_fn(self.host_status_dict)
        return

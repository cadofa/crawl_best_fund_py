#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import pdb
import time
from subprocess import Popen, PIPE, STDOUT
import json
import logging
import logging.config
import parse_config
from com_utils import get_local_time, get_timestamp
from global_variable import HostEnvInitSteps, HostEnvClearSteps
from host_env import HostEnv
from global_variable import CMD_RETRY_TIMES_CONST


class CentOs7HostEnv(HostEnv):
    # def __init__(self):
    #    return

    def set_linux_source(self):
        """
        yum source file or rpm package path config in config file.
        {'epel_rpm_pkg':'https://dl.fedoraproject.org/pub/epel/7/x86_64/e/epel-release-7-8.noarch.rpm',
        'repo_file':'https://.../CentOS-Base.repo'}
         {'centos7':{'linux_source':{'epel_rpm_pkg':url, 'repo_file':url}...}}
        1. 复制指定机器上指定路径下的rpm安装包和yum_source文件name.repo到目标主机
        2. 安装rpm包
        3. 更新yum_source文件
        4. 调用yum makecache命令
        :return: True, None: success False, err_info: failed
        note: if cmd 'rpm -i epel_rpm_pkg' execute fail, need to optmize, it's unnecessary to break process
        """
        err_info_list = list()
        if 'linux_source' not in self.os_config.keys():
            self.logger.info("CentOs7HostEnv::set_linux_source: os_config does "
                             "not contain config item linux_source")
            return True, None
        if self.ssh_client is None:
            ret, err_info = self._reget_ssh_instance()
            print "self._reget_ssh_instance()", ret, err_info
            if ret is False:
                return False, err_info
        # copy epel_rpm_pkg to hostname:/home
        if 'epel_rpm_pkg' in self.os_config['linux_source'].keys():
            cmd = 'sudo scp -P ' + str(self.host_info['ssh_port']) + ' ' + self.os_config['linux_source'][
                'epel_rpm_pkg'] \
                  + ' ' + self.host_info['hostname'] + ':/home/'
            print "cmd", cmd
            com_result_list = self._run_popen_cmd(cmd)
            print "self._run_popen_cmd(cmd)", com_result_list
            print
            if len(com_result_list) > 0 and com_result_list[0].strip().find("No such file or directory") >= 0:
                err_info = "set_linux_source: execute " + cmd + " error, " + com_result_list[0].strip()
                self.logger.error(err_info)
                return False, err_info
            files = self.os_config['linux_source']['epel_rpm_pkg'].split('/')
            cmd = 'rpm -i /home/' + files[len(files) - 1]
            print "cmd", cmd
            ret, info = self._run_command(cmd)
            print "self._run_command(cmd)", ret, info
            print 
            if ret is False:
                self.logger.error(info)
                err_info_list.append(info)
                # return False, info
            if info.find("already installed") >= 0 or info.find("Complete!") >= 0:
                self.logger.info("CentOs7HostEnv::set_linux_source: success config epel_rpm_pkg")
        # copy repo_file to hostname:/home
        if 'repo_file' in self.os_config['linux_source'].keys():
            cmd = 'sudo scp -P ' + str(self.host_info['ssh_port']) + ' ' + self.os_config['linux_source']['repo_file'] \
                  + ' ' + self.host_info['hostname'] + ':/home/'
            print "cmd", cmd
            com_result_list = self._run_popen_cmd(cmd)
            print "self._run_popen_cmd(cmd)", com_result_list
            print 
            if len(com_result_list) > 0 and com_result_list[0].strip().find("No such file or directory") >= 0:
                err_info = "set_linux_source: execute " + cmd + " error, " + com_result_list[0].strip()
                self.logger.error(err_info)
                err_info_list.append(err_info)
                return False, json.dumps(err_info_list) 
            # cmd = 'mv /etc/yum.repos.d/CentOS-Base.repo /etc/yum.repos.d/CentOS-Base.repo.' + str(get_timestamp()) \
            #      + ' && cp /home/CentOS-Base.repo /etc/yum.repos.d/'
            cmd = 'yes|cp /home/CentOS-Base.repo /etc/yum.repos.d/'
            print "cmd", cmd
            ret, err_info = self._run_command(cmd)
            print "self._run_command(cmd)", ret, err_info
            print 
            if ret is False:
                self.logger.error(info)
                return False, json.dumps(err_info_list.append(info))
            #cmd = 'yum clean all && yum makecache'
            #print "cmd", cmd
            #ret, info = self._run_command(cmd)
            #print "self._run_command(cmd)", ret, info
            #print 
            if ret is False:
                self.logger.error(info)
                return False, json.dumps(err_info_list.append(info))
            #if info.find("Metadata Cache Created") >= 0:
            #    self.logger.info("Centos7HostEnvInit::set_linux_source: execute " + cmd + " success.")
            #else:
            #    err_info = "Centos7HostEnvInit::set_linux_source: execute " + cmd + " failed, " + info
            #    self.logger.error(err_info)
            #    return False, json.dumps(err_info_list.append(err_info))
        if len(err_info_list) == 0:
            return True, None
        else:
            return False, json.dumps(err_info_list)

    def is_active_service(self, service_name):
        """
        服务是否处于active状态
        :param service_name: 服务
        :return: result_num 其中：1表示active, 0表示unactive, 2表示执行失败
        """
        info = None
        if self.ssh_client is None:
            ret, err_info = self._reget_ssh_instance()
            if ret is False:
                return 2
        cmd = 'systemctl is-active ' + service_name + ' 2>/dev/null'
        ret, info = self._run_command(cmd)
        if ret is False:
            info = "CentOs7HostEnv::is_active_service: execute cmd error: " + info
            self.logger.error(info)
            return 2
        elif info == 'active':
            return 1
        else:
            return 0

    def set_kernel_key_value_file(self, key, value, file):
        """
        更新kernel配置文件中指定项的值
        :param key: 更改的配置项
        :param value: 更改配置项的值
        :param file: 要更改的配置文件
        :return: True, None:成功 False, err_info：失败
        """
        err_info = None
        cmd = None
        cmd = "sed -n '/^" + key + "=/p' " + file
        ret, info = self._run_command(cmd)
        if ret is False:
            info = "CentOs7HostEnv::set_kernel_key_value_file: " + info
            self.logger.error(info)
            return False, info
        if info == '':
            cmd = "echo '" + key + "=" + value + "' >> " + file
        else:
            cmd = "sed -i '/^" + key + "=/c " + key + "=" + value + "' " + file
        ret, info = self._run_command(cmd)
        if ret is False:
            info = "CentOs7HostEnv::set_kernel_key_value_file: " + info
            self.logger.error(info)
            return False, info
        return True, None

    def _set_soft_hard_limit(self, item=dict()):
        """
        设置软硬连接限制
        :param item: 软硬连接配置信息
        :return: True, None:成功 False, err_info：失败
        """
        err_info = ""
        keys = item.keys()
        if 'soft_limit' in keys:
            ret, info = self._del_line_file(item['file'], '*       soft    nofile')
            if ret is False:
                err_info += ' soft_limit ' + info
                return False, err_info
            ret, info = self._add_line_file(item['file'], '*       soft    nofile  ' + str(item['soft_limit']))
            if ret is False:
                err_info += ' soft_limit ' + info
                return False, err_info
        if 'hard_limit' in keys:
            ret, info = self._del_line_file(item['file'], '*       hard    nofile')
            if ret is False:
                err_info += ' hard_limit ' + info
                return False, err_info
            ret, info = self._add_line_file(item['file'], '*       hard    nofile  ' + str(item['hard_limit']))
            if ret is False:
                err_info += ' hard_limit ' + info
                return False, err_info
        return True, None

    def set_kernel(self):
        """
        完成配置文件中多个小节配置，包括：self.os_config['kernel_param']['']
        {'kernel_param':[{'kernel.pid_max':'4194303', 'vm.swappiness':'0', 'file':'', 'fs.file-max':'1310710'], {'file':'', 'soft_limit':'1024000', 'hard_limit':'1024000'}]}
        :return: True,None:成功 False, err_info: 需要优化
        """
        err_info = None
        if self.ssh_client is None:
            ret, err_info = self._reget_ssh_instance()
            if ret is False:
                return False, err_info
        # pdb.set_trace()
        if 'kernel_param' in self.os_config.keys():
            for item in self.os_config['kernel_param']:
                cmd = ''
                keys = item.keys()
                if 'file' not in keys:
                    err_info += ' :not file key ' + json.dumps(item)
                    continue
                # 设置软硬连接限制
                if 'hard_limit' in keys or 'soft_limit' in keys:
                    ret, info = self._set_soft_hard_limit(item)
                    if ret is False:
                        err_info += info
                    continue
                for key_item in keys:
                    if key_item == 'file':
                        continue
                    ret, info = self.set_kernel_key_value_file(key_item, item[key_item], item['file'])
                    if ret is not True:
                        err_info += info
            if err_info is not None:
                return False, err_info
        return True, None

    def _config_firewall_add_port(self, port, insert_line_num):
        """
        配置指定port可出防火墙
        :param port: str 端口号
        :param insert_line_num: str 文件中的行号-----在该行前插入
        :return: True, None：success False, err_info: fail
        """
        ret, err_info = self._del_line_file('/etc/sysconfig/iptables', 'dport ' + str(port) + ' ')
        if ret is False:
            self.logger.error(err_info)
            return False, err_info
        line_content_str = "sed -i 'N;" + insert_line_num + "i-A INPUT -p tcp -m state --state NEW -m tcp --dport " + str(
            port) + " -j ACCEPT' /etc/sysconfig/iptables"
        ret, err_info = self._run_command(line_content_str)
        if ret is False:
            self.logger.error(err_info)
            return False, err_info
        return True, None

    def restart_iptable_service(self):
        """
        重启iptables服务
        :return: True, None：success False, err_info: fail
        note: 更改iptable配置更改后，需要调用该接口
        """
        ret, err_info = self._run_command("systemctl mask firewalld")
        if ret is False:
            err_info = "CentOs7HostEnv::restart_iptable_service: " + err_info
            self.logger.error(err_info)
            return False, err_info
        elif err_info.find("Created") >= 0 or err_info == '':
            self.logger.info("cmd 'systemctl mask firewalld' execute success.")
        else:
            err_info = "CentOs7HostEnv::restart_iptable_service: " + err_info
            self.logger.error(err_info)
            return False, err_info
        # 下面命令执行有时候不成功，所以直接调用
        ret, err_info = self._multi_run_command("systemctl enable iptables && systemctl is-enabled iptables")
        if ret is False:
            self.logger.error(err_info)
            return False, err_info
        self.logger.info("execute 'systemctl enable iptables && systemctl is-enabled iptables' success")
        # ret, err_info = self._multi_run_command("service iptables save")
        ret, err_info = self._multi_run_command("systemctl restart iptables && systemctl is-active iptables")
        if ret is False:
            self.logger.error(err_info)
            return False, err_info
        self.logger.info("CentOs7HostEnv::restart_iptable_service: iptables service is active")
        return True, None

    def set_firewall_config(self, port=None, is_config_config=True):
        """
        配置iptables，包括ssh_port和配置文件中相应选项
        'node_type': ['osd', 'mon', 'rgw']
        :param port: 指定端口
        :param is_config_config: True:要配置配置中指定的iptables内容,包括ssh_port，角色端口，False: 不配置
        :return: True,None: success False,err_info: fail
        """
        err_info = None
        ports = list()
        if port is None and is_config_config is False:
            self.loggger.info("CentOs7HostEnv::firewall_config_set: success, port is None and "
                              "is_config_configfile is false, not need set firewall")
            return True, None
        if self.ssh_client is None:
            ret, err_info = self._reget_ssh_instance()
            if ret is False:
                return False, err_info
        # pdb.set_trace()
        insert_line_num = "12"
        # ret, info = self._run_command("sed -n -e '/icmp-host-prohibited/=' /etc/sysconfig/iptables")
        # if ret is False:
        #    self.logger.error(info)
        #    return False, info
        # else:
        #    num_list = info.split('\n')
        #    if len(num_list) > 0:
        #        insert_line_num = str(num_list[0])
        if is_config_config is True:
            # 设置ssh port，默认开着22端口
            if "22" != str(self.host_info['ssh_port']):
                ports.append(str(self.host_info['ssh_port']))
                cmd = "sed -i -e '/dport 22 /d' /etc/sysconfig/iptables"
                ret, err_info = self._run_command(cmd)
                if ret is False:
                    err_info = "CentOs7HostEnv::set_firewall_config: del 22 port error, " + err_info
                    self.logger.error(err_info)
                    return False, err_info
            # 配置角色端口
            for role in self.host_info['node_type']:
                if role == 'mon':
                    ports.append('3300')
                    ports.append('6789')
                elif role == 'osd':
                    ports.append('6800:7300')
                elif role == 'rgw':
                    ports.append('80')
        if port is not None:
            ports.append(str(port))
        err_info_list = list()
        tag = 0
        for port_item in ports:
            ret, err_info = self._config_firewall_add_port(port_item, insert_line_num)
            if ret is False:
                tag = 1
                self.logger.error(err_info)
                err_info_list.append(err_info)
            self.logger.info("CentOs7HostEnv::firewall_config_set: set " + port_item + " success.")
        if tag == 1:
            return False, json.dumps(err_info_list)
        ret, err_info = self.restart_iptable_service()
        if ret is False:
            err_info = "CentOs7HostEnv::firewall_config_set: restart iptable service error, " + err_info
            self.logger.error(err_info)
            return False, err_info
        self.logger.info("CentOs7HostEnv::firewall_config_set: start iptables service success")
        return True, None

    def is_remove_pkgs_success(self, pkgs_str):
        """
        检查命令yum -y remove pkg1 pkg2是否执行成功
        :param: pkgs_str 要检查的所有包，各个包之间以空格分隔
        :return: True, dict(): 成功  False, err_info_dict: 失败
        """
        err_tag = 0
        err_info_dict = dict()
        remove_pkgs = pkgs_str.split(' ')
        for remove_pkg_item in remove_pkgs:
            cmd = 'rpm -iq ' + remove_pkg_item
            ret, info = self._run_command(cmd)
            if ret is False:
                err_tag = 1
                err_info_dict[remove_pkg_item] = info
                self.logger.error("Centos7HostEnvInit::is_remove_pkgs_success: " + info)
            elif info.find("not installed") >= 0:
                self.logger.info("Centos7HostEnvInit::is_remove_pkgs_success: execute yum -y remove "
                                 + remove_pkg_item + " success.")
            else:
                err_tag = 1
                err_info_dict[remove_pkg_item] = "Centos7HostEnvInit::is_remove_pkgs_success: execute yum -y remove " \
                                                 + remove_pkg_item + " failed."
                self.logger.error(err_info_dict[remove_pkg_item])
        if err_tag == 1:
            return False, err_info_dict
        else:
            return True, err_info_dict

    def is_install_pkgs_success(self, install_pkg_list):
        """
        检查命令yum -y install pkg1 pkg2是否执行成功
        :param install_pkg_list: [pkg1,pkg2,pkg3] 要安装的pkgs
        :return: True, dict(): 成功  False, err_info_dict: 失败
        """
        err_tag = 0
        err_info_dict = dict()
        for install_pkg_item in install_pkg_list:
            ret, info = self._run_command('rpm -iq ' + install_pkg_item)
            if ret is False:
                err_tag = 1
                err_info_dict[install_pkg_item] = info
                self.logger.error("Centos7HostEnvInit::is_install_pkgs_success: " + info)
            elif info.find("not installed") >= 0:
                err_tag = 1
                err_info_dict[install_pkg_item] = info
                self.logger.error(err_info_dict[install_pkg_item])
            else:
                self.logger.info(info)
        if err_tag == 1:
            return False, err_info_dict
        return True, err_info_dict

    def remove_pkg(self, pkgs_str):
        """
        删除指定的包
        :param pkgs_str: 要删除的包列表，这里各个包名之间以空格分隔
        :return: True, None 成功 False, err_info 失败
        """
        cmd = 'yum -y remove ' + pkgs_str
        ret, err_info = self._run_command(cmd)
        if ret is False:
            self.logger.error(err_info)
            return False, err_info
        else:
            ret, err_info_dict = self.is_remove_pkgs_success(pkgs_str)
            if ret is False:
                err_info = "CentOs7HostEnv::remove_pkg: remove pkgs error, error: " \
                           + json.dumps(err_info_dict)
                self.logger.debug(err_info)
                return False, err_info
            else:
                self.logger.info("CentOs7HostEnv::remove_pkg: execute cmd " + cmd + "success.")
        return True, None

    def install_pkg(self, pkgs_str):
        """
        安装指定的包
        :param pkgs_str: 要安装的包列表，这里各个包名之间以空格分隔
        :return: True, None 成功 False, err_info 失败
        """
        err_info_list = list()
        ret, info = self._run_command('yum -y install ' + pkgs_str)
        if ret is False:
            info = "CentOs7HostEnv::install_pkg: install pkgs error, error: " + info
            self.logger.error(info)
            return info
        pkg_list = pkgs_str.split(' ')
        # validate whether pkg has beed installed
        for pkg_item in pkg_list:
            ret, info = self._run_command('rpm -iq ' + pkg_item)
            if ret is False:
                info = "CentOs7HostEnv::install_pkg: install pkgs error, error: " + info
                self.logger.error(info)
                err_info_list.append(info)
            elif info.find("not installed") >= 0:
                err_info_list.append(info)
            else:
                self.logger.info("CentOs7HostEnv::install_pkg: install pkg: " + info)
        if len(err_info_list) > 0:
            return False, json.dumps(err_info_list)
        return True, None

    def update_pkg(self, pkg_name='', is_install_requested_pkg=False):
        """
        更新package，这里包括卸载指定的包列表，安装指定的包列表
        :param pkg_name: 指定要安装的软件包名称
        :param is_install_requested_pkg: 是否安装pkg_request_file中指定的安装包
        :return: True,None：成功 False,err_info:失败
        note: remove pkg execute failed need to optmize, it's unnecessary to  break process
        """
        err_info = None
        cmd = ""
        install_pkgs = ""
        err_info_list = list()
        if self.ssh_client is None:
            ret, err_info = self._reget_ssh_instance()
            if ret is False:
                return False, err_info
        if is_install_requested_pkg is not False and 'request_pkg' in self.os_config.keys():
            if 'remove' in self.os_config['request_pkg'].keys():
                ret, err_info = self.remove_pkg(self.os_config['request_pkg']['remove'])
                if ret is False:
                    err_info_list.append(err_info)
            if 'install' in self.os_config['request_pkg'].keys():
                install_pkgs = self.os_config['request_pkg']['install']
        if pkg_name != "":
            if install_pkgs != "":
                install_pkgs = install_pkgs + ' ' + pkg_name
            else:
                install_pkgs = pkg_name
        if install_pkgs != "":
            print "install_pkgs", install_pkgs
            ret, err_info = self.install_pkg(install_pkgs)
            print "self.install_pkg(install_pkgs)", ret, err_info
            if ret is False:
                err_info = "CentOs7HostEnv::update_pkg: install pkgs error, error: " + err_info
                self.logger.error(err_info)
                return False, json.dumps(err_info_list.append(err_info))
            self.logger.info("CentOs7HostEnv::update_pkg: install pkgs " + install_pkgs + " success.")
        if len(err_info_list) == 0:
            return True, None
        else:
            print "err_info_list", err_info_list
            return True, json.dumps(err_info_list)

    def set_time_zone(self):
        """
        设置时区为亚洲上海---该时区为默认时区
        :return: True, None：success False, err_info: fail
        note: 时区中大洲和城市首字母必须大写，否则设置为默认设置
        """
        if 'timezone' in self.os_config.keys():
            keys = self.os_config['timezone'].keys()
            if 'continent' in keys and 'city' in keys:
                cmd = 'yes|cp /usr/share/zoneinfo/' + self.os_config['timezone']['continent'] + '/' \
                      + self.os_config['timezone']['city'] + ' /etc/localtime'
                ret, info = self._run_command(cmd)
                if ret is False or info.find("No such file or directory") >= 0:
                    info = "Centos7HostEnvInit::set_time_zone: execute cmd: " + cmd + ' ' + info
                    self.logger.debug(info)
                else:
                    return True, None
        cmd = "yes|cp /usr/share/zoneinfo/Asia/Shanghai /etc/localtime"
        ret, err_info = self._run_command(cmd)
        if ret is False or err_info.find("No such file or directory") >= 0:
            return False, err_info
        return True, None

    def set_ntp(self):
        """
        完成ntp相关所有配置，包括：时区、系统时间配置、硬件时间配置
        :return: True, None 成功 False, err_info 失败
        """
        self.logger.info("CentOs7HostEnv::set_ntp: ")
        cmd = None
        err_info = None
        # set ntp.conf
        ret, err_info = self._del_line_file('/etc/ntp.conf', 'server')
        if ret is False:
            err_info = "CentOs7HostEnv::set_ntp: set ntp.conf error, " + err_info
            self.logger.error(err_info)
            return False, err_info
        ret, err_info = self._add_line_file('/etc/ntp.conf', 'server ' + self.host_info['ntp_server'] + ' iburst')
        if ret is False:
            err_info = "CentOs7HostEnv::set_ntp: set ntp.conf error, " + err_info
            self.logger.error(err_info)
            return False, err_info
        # set ntpd.service
        ret, err_info = self._del_line_file('/usr/lib/systemd/system/ntpd.service', 'Restart=always')
        if ret is False:
            err_info = "CentOs7HostEnv::set_ntp: set ntpd.service error, " + err_info
            self.logger.error(err_info)
            return False, err_info
        cmd = "sed -i '/PrivateTmp=true/aRestart=always' /usr/lib/systemd/system/ntpd.service"
        ret, err_info = self._run_command(cmd)
        if ret is False:
            err_info = "CentOs7HostEnv::set_ntp: set ntpd.service error, " + err_info
            self.logger.error(err_info)
            return False, err_info
        # set ntpd
        ret, err_info = self._del_line_file('/etc/sysconfig/ntpd', 'SYNC_HWCLOCK=')
        if ret is False:
            err_info = "CentOs7HostEnv::set_ntp: set ntpd error, " + err_info
            self.logger.error(err_info)
            return False, err_info
        ret, err_info = self._add_line_file('/etc/sysconfig/ntpd', 'SYNC_HWCLOCK=yes')
        if ret is False:
            err_info = "CentOs7HostEnv::set_ntp: set ntpd error, " + err_info
            self.logger.error(err_info)
            return False, err_info

        # set timezone
        ret, err_info = self.set_time_zone()
        if ret is False:
            err_info = "CentOs7HostEnv::set_ntp: set timezone error, " + err_info
            self.logger.error(err_info)
            return False, err_info
        self.logger.info("CentOs7HostEnv::set_ntp: set timezone success")

        ret, err_info = self._run_command("systemctl enable ntpd && systemctl restart ntpd")
        if ret is False:
            return False, err_info
        ret = self.is_active_service("ntpd")
        if ret == 1:
            self.logger.info("CentOs7HostEnv::set_ntp: ntpd service is active")
        elif ret == 0:
            err_info = "CentOs7HostEnv::set_ntp: ntpd service starts failed"
            self.logger.error(err_info)
            return False, err_info
        else:
            err_info = "CentOs7HostEnv::set_ntp: execute cmd 'systemctl is-active ntpd' failed"
            self.logger.error(err_info)
            return False, err_info
        return True, None

    def clear_ntp_config(self):
        """
        清理ntp配置
        :return: True, None 成功 False, err_info 失败
        """
        cmd = None
        err_info = None
        # set ntp.conf
        ret, err_info = self._del_line_file('/etc/ntp.conf', 'server')
        if ret is False:
            err_info = "CentOs7HostEnv::clear_ntp_config: set ntp.conf error, " + err_info
            self.logger.error(err_info)
            return False, err_info

        # set ntpd.service
        ret, err_info = self._del_line_file('/usr/lib/systemd/system/ntpd.service', 'Restart=always')
        if ret is False:
            err_info = "CentOs7HostEnv::clear_ntp_config: set ntpd.service error, " + err_info
            self.logger.error(err_info)
            return False, err_info

        # set ntpd
        ret, err_info = self._del_line_file('/etc/sysconfig/ntpd', 'SYNC_HWCLOCK=')
        if ret is False:
            err_info = "CentOs7HostEnv::clear_ntp_config: set ntpd error, " + err_info
            self.logger.error(err_info)
            return False, err_info

        ret, err_info = self._run_command("systemctl stop ntpd")
        if ret is False:
            return False, err_info
        ret = self.is_active_service("ntpd")
        if ret == 0:
            self.logger.info("CentOs7HostEnv::clear_ntp_config: ntpd service stop success")
        elif ret == 1:
            err_info = "CentOs7HostEnv::clear_ntp_config: ntpd service stop failed "
            self.logger.error(err_info)
            return False, err_info
        else:
            err_info = "CentOs7HostEnv::clear_ntp_config: execute cmd 'systemctl is-active ntpd' failed"
            self.logger.error(err_info)
            return False, err_info
        self.logger.info("CentOs7HostEnv::clear_ntp_config: clear ntp config success")
        return True, None

    def init_host_env(self):
        """
        系统环境初始化-----共13步
        :return:
        """
        detail_info = None
        # 1. 初始化变量
        step = HostEnvInitSteps.INIT_VAR
        self.host_status_dict['current_step'] = step
        ret = self._init_system_var()
        if ret is False:
            detail_info = "step1 CentOs7HostEnv::init_host_env: step INIT_VAR execute failed: ssh connect error"
            print "step1 CentOs7HostEnv::init_host_env: step INIT_VAR execute failed: ssh connect error"
            self.logger.error(detail_info)
            self._handle_result(step, detail_info, 2)
            return
        else:
            print "step1 CentOs7HostEnv::init_host_env: step INIT_VAR execute success"
            detail_info = "step1 CentOs7HostEnv::init_host_env: step INIT_VAR execute success"
            self.logger.info(detail_info)
            self._handle_result(step, detail_info, 0)

        # 2. 连通性检查
        step = HostEnvInitSteps.CHECK_CONNECTION
        self.host_status_dict['current_step'] = step
        ret, err_dict = self._check_network()
        if ret is False:
            detail_info = ("step2 CentOs7HostEnv::init_host_env: step CHECK_CONNECTION execute failed," 
                           "hosts ping error, source host: " + self.host_info['hostname'] + 
                           ", destination host_list: " + json.dumps(err_dict))
            print ("step2 CentOs7HostEnv::init_host_env: step CHECK_CONNECTION execute failed," 
                   "hosts ping error, source host: " + self.host_info['hostname'] + 
                   ", destination host_list: " + json.dumps(err_dict))
            self.logger.error(detail_info)
            self._handle_result(step, detail_info, 2)
            return
        else:
            detail_info = "step2 HostEnv::_init_host_status_dict: step CHECK_CONNECTION execute success"
            print "step2 HostEnv::_init_host_status_dict: step CHECK_CONNECTION execute success"
            self.logger.info(detail_info)
            self._handle_result(step, detail_info, 0)

        #3. 更换源
        step = HostEnvInitSteps.UPDATE_SOURCE
        self.host_status_dict['current_step'] = step
        ret, err_info = self.set_linux_source()
        if ret is False:
            detail_info = "step3 CentOs7HostEnv::init_host_env: step UPDATE_SOURCE execute failed, " + err_info
            print  "step3 CentOs7HostEnv::init_host_env: step UPDATE_SOURCE execute failed, " + err_info
            self._handle_result(step, detail_info, 2)
            self.logger.error(detail_info)
            return
        else:
            if err_info is None:
                detail_info = "step3 CentOs7HostEnv::init_host_env: step UPDATE_SOURCE execute success"
                print "stet3 CentOs7HostEnv::init_host_env: step UPDATE_SOURCE execute success"
                self.logger.info(detail_info)
                self._handle_result(step, detail_info, 0)
            else:
                err_info = "step3 CentOs7HostEnv::init_host_env: step UPDATE_SOURCE need optmize " + err_info
                print "step3 CentOs7HostEnv::init_host_env: step UPDATE_SOURCE need optmize " + err_info
                self.logger.debug(err_info)
                self._handle_result(step, err_info, 1)

        # 4. 卸载/安装必备的pkg
        step = HostEnvInitSteps.REMOVE_INSTALL_PKG
        self.host_status_dict['current_step'] = step
        ret, err_info = self.update_pkg(pkg_name='', is_install_requested_pkg=True)
        if ret is False:
            detail_info = "step4 CentOs7HostEnv::init_host_env: step REMOVE_INSTALL_PKG execute failed, " + err_info
            print  "step4 CentOs7HostEnv::init_host_env: step REMOVE_INSTALL_PKG execute failed, " + err_info
            self._handle_result(step, detail_info, 2)
            self.logger.error(detail_info)
            return
        else:
            if err_info is None:
                detail_info = "step4 CentOs7HostEnv::init_host_env: step REMOVE_INSTALL_PKG execute success"
                print "step4 CentOs7HostEnv::init_host_env: step REMOVE_INSTALL_PKG execute success"
                self.logger.info(detail_info)
                self._handle_result(step, detail_info, 0)
            else:
                err_info = "step4 CentOs7HostEnv::init_host_env: step REMOVE_INSTALL_PKG need optmize " + err_info
                print "step4 CentOs7HostEnv::init_host_env: step REMOVE_INSTALL_PKG need optmize " + err_info
                self.logger.debug(err_info)
                self._handle_result(step, err_info, 1)

        # 5. 防火墙配置
        step = HostEnvInitSteps.CONFIG_FIREWALL
        self.host_status_dict['current_step'] = step
        ret, err_info = self.set_firewall_config(port=None, is_config_config=True)
        if ret is False:
            detail_info = "step5 CentOs7HostEnv::init_host_env: step CONFIG_FIREWALL execute failed, " + err_info
            print "step5 CentOs7HostEnv::init_host_env: step CONFIG_FIREWALL execute failed, " + err_info
            self._handle_result(step, detail_info, 2)
            self.logger.error(detail_info)
            return
        else:
            detail_info = "step5 CentOs7HostEnv::init_host_env: step CONFIG_FIREWALL execute success"
            print "step5 CentOs7HostEnv::init_host_env: step CONFIG_FIREWALL execute success"
            self.logger.info(detail_info)
            self._handle_result(step, detail_info, 0)

        #6. kernel参数配置
        step = HostEnvInitSteps.CONFIG_KERNEL
        self.host_status_dict['current_step'] = step
        ret, err_info = self.set_kernel()
        if ret is False:
            detail_info = "step6 CentOs7HostEnv::init_host_env: step CONFIG_KERNEL execute failed, " + err_info
            print "step6 CentOs7HostEnv::init_host_env: step CONFIG_KERNEL execute failed, " + err_info
            self._handle_result(step, detail_info, 1)
            self.logger.error(detail_info)
        else:
            detail_info = "step6 CentOs7HostEnv::init_host_env: step CONFIG_KERNEL execute success"
            print "step6 CentOs7HostEnv::init_host_env: step CONFIG_KERNEL execute success"
            self.logger.info(detail_info)
            self._handle_result(step, detail_info, 0)

        # 7. 磁盘优化配置
        step = HostEnvInitSteps.CONFIG_DISK_OPTMIZE
        self.host_status_dict['current_step'] = step
        ret, err_info = self.set_disk_optmize_script()
        if ret is False:
            detail_info = "step7 CentOs7HostEnv::init_host_env: step CONFIG_DISK_OPTMIZE execute failed, " + err_info
            print "step7 CentOs7HostEnv::init_host_env: step CONFIG_DISK_OPTMIZE execute failed, " + err_info
            self._handle_result(step, detail_info, 1)
            self.logger.error(detail_info)
            return
        else:
            detail_info = "step7 CentOs7HostEnv::init_host_env: step CONFIG_DISK_OPTMIZE execute success"
            print "step7 CentOs7HostEnv::init_host_env: step CONFIG_DISK_OPTMIZE execute success"
            self.logger.info(detail_info)
            self._handle_result(step, detail_info, 0)

        # 8. 硬盘中断绑定配置
        step = HostEnvInitSteps.CONFIG_DISK_BREAK_BIND
        self.host_status_dict['current_step'] = step
        ret, err_info = self.set_ssd_break_bind_script()
        if ret is False:
            detail_info = "step8 CentOs7HostEnv::init_host_env: step CONFIG_DISK_BREAK_BIND execute failed, " + err_info
            print "step8 CentOs7HostEnv::init_host_env: step CONFIG_DISK_BREAK_BIND execute failed, " + err_info
            self._handle_result(step, detail_info, 1)
            self.logger.error(detail_info)
            # return
        else:
            detail_info = "step8 CentOs7HostEnv::init_host_env: step CONFIG_DISK_BREAK_BIND execute success"
            print "step8 CentOs7HostEnv::init_host_env: step CONFIG_DISK_BREAK_BIND execute success"
            self.logger.info(detail_info)
            self._handle_result(step, detail_info, 0)

        # 9. ntp配置(包含时区配置)
        step = HostEnvInitSteps.CONFIG_NTP
        self.host_status_dict['current_step'] = step
        ret, err_info = self.set_ntp()
        if ret is False:
            detail_info = "step9 CentOs7HostEnv::init_host_env: step CONFIG_NTP execute failed, " + err_info
            print "step9 CentOs7HostEnv::init_host_env: step CONFIG_NTP execute failed, " + err_info
            self._handle_result(step, detail_info, 2)
            self.logger.error(detail_info)
            return
        else:
            detail_info = "step9 CentOs7HostEnv::init_host_env: step CONFIG_NTP execute success"
            print "step9 CentOs7HostEnv::init_host_env: step CONFIG_NTP execute success"
            self.logger.info(detail_info)
            self._handle_result(step, detail_info, 0)

        # 10. selinux设置
        step = HostEnvInitSteps.CONFIG_SELINUX
        self.host_status_dict['current_step'] = step
        ret, err_info = self.set_selinux()
        if ret is False:
            detail_info = "step10 CentOs7HostEnv::init_host_env: step CONFIG_SELINUX execute , " + err_info
            print "step10 CentOs7HostEnv::init_host_env: step CONFIG_SELINUX execute , " + err_info
            self._handle_result(step, detail_info, 2)
            self.logger.error(detail_info)
            return
        else:
            detail_info = "step10 CentOs7HostEnv::init_host_env: step CONFIG_SELINUX execute success"
            print "step10 CentOs7HostEnv::init_host_env: step CONFIG_SELINUX execute success"
            self.logger.info(detail_info)
            self._handle_result(step, detail_info, 0)

        # 11. 带宽检测
        step = HostEnvInitSteps.CHECK_BANDWIDTH
        self.host_status_dict['current_step'] = step
        ret = self.check_bandwidth()
        if ret is False:
            detail_info = "step11 CentOs7HostEnv::init_host_env: step CHECK_BANDWIDTH execute failed, "
            print "step11 CentOs7HostEnv::init_host_env: step CHECK_BANDWIDTH execute failed, "
            self._handle_result(step, detail_info, 2)
            self.logger.error(detail_info)
            # return
        else:
            detail_info = "step11 CentOs7HostEnv::init_host_env: step CHECK_BANDWIDTH execute success"
            print "step11 CentOs7HostEnv::init_host_env: step CHECK_BANDWIDTH execute success"
            self.logger.info(detail_info)
            self._handle_result(step, detail_info, 0)

        # 12. 配置机器名
        step = HostEnvInitSteps.CONFIG_HOSTNAME
        self.host_status_dict['current_step'] = step
        ret, err_info = self.set_hostname()
        if ret is False:
            detail_info = "step12 CentOs7HostEnv::init_host_env: step CONFIG_HOSTNAME execute failed, " + err_info
            print "step12 CentOs7HostEnv::init_host_env: step CONFIG_HOSTNAME execute failed, " + err_info
            self._handle_result(step, detail_info, 2)
            self.logger.error(detail_info)
            return
        else:
            detail_info = "step12 CentOs7HostEnv::init_host_env: step CONFIG_HOSTNAME execute success"
            print "step12 CentOs7HostEnv::init_host_env: step CONFIG_HOSTNAME execute success"
            self.logger.info(detail_info)
            self._handle_result(step, detail_info, 0)

        # 13. 重启机器
        step = HostEnvInitSteps.REBOOT
        self.host_status_dict['current_step'] = step
        ret, err_info = self.reboot_host()
        if ret is False:
            detail_info = "step13 CentOs7HostEnv::init_host_env: step REBOOT execute failed, " + err_info
            print "step13 CentOs7HostEnv::init_host_env: step REBOOT execute failed, " + err_info
            self._handle_result(step, detail_info, 2)
            self.logger.error(detail_info)
            return
        else:
            detail_info = "step13 CentOs7HostEnv::init_host_env: step REBOOT execute success"
            print "step13 CentOs7HostEnv::init_host_env: step REBOOT execute success"
            self.logger.info(detail_info)
            self._handle_result(step, detail_info, 0)
        return

    def clear_firewall_config(self, port=None, is_clear_config=True):
        """
        清空环境初始化配置(包括host角色端口清理)，并停止iptables服务
        :param port: 指定要清理的端口
        :param is_clear_config: 是否清理配置的端口，默认是True
        :return: True, None: 成功 False, err_info: 失败
        """
        err_info_list = list()
        '''
        ports = list()
        if port is None and is_clear_config is False:
            self.loggger.info("CentOs7HostEnv::clear_firewall_config: success, port is None and "
                              "is_clear_config is false, not need set firewall")
            return True, None
        if self.ssh_client is None:
            ret, err_info = self._reget_ssh_instance()
            if ret is False:
                return False, err_info
        if is_clear_config is True:
            # 配置角色端口
            for role in self.host_info['node_type']:
                if role == 'mon':
                    ports.append('3300')
                    ports.append('6789')
                elif role == 'osd':
                    ports.append('6800:7300')
                elif role == 'rgw':
                    ports.append('80')
        if port is not None:
            ports.append(str(port))
        err_info_list = list()
        for port_item in ports:
            ret, err_info = self._del_line_file('/etc/sysconfig/iptables', 'dport ' + str(port_item) + ' ')
            if ret is False:
                self.logger.error(err_info)
                err_info_list.append(err_info)
        '''
        ret, err_info = self._run_command("systemctl disable iptables && systemctl stop iptables")
        if ret is False:
            self.logger.error(err_info)
            err_info_list.append(err_info)
        ret, err_info = self.remove_pkg('iptables-services')
        if ret is False:
            self.logger.error(err_info)
            err_info_list.append(err_info)
        if len(err_info_list) > 0:
            return False, json.dumps(err_info_list)
        return True, None

    def clear_host_env(self):
        """
        清理环境-----共8步
        :return:
        """
        # 1. 初始化变量
        step = HostEnvClearSteps.INIT_VAR
        self.host_status_dict['current_step'] = step
        ret = self._init_system_var()
        if ret is False:
            detail_info = "CentOs7HostEnv::clear_host_env: step INIT_VAR execute failed: ssh connect error"
            self.logger.error(detail_info)
            self._handle_result(step, detail_info, 2)
            return
        else:
            detail_info = "CentOs7HostEnv::clear_host_env: step INIT_VAR execute success"
            self.logger.info(detail_info)
            self._handle_result(step, detail_info, 0)

        # 2. 卸载安装包ceph
        step = HostEnvClearSteps.REMOVE_PKG_CEPH
        self.host_status_dict['current_step'] = step
        ret, err_info = self.remove_pkg('ceph')
        if ret is False:
            detail_info = "CentOs7HostEnv::clear_host_env: step REMOVE_PKG_CEPH execute failed: " + err_info
            self.logger.error(detail_info)
            self._handle_result(step, detail_info, 2)
            #return
        else:
            detail_info = "CentOs7HostEnv::clear_host_env: step REMOVE_PKG_CEPH execute success"
            self.logger.info(detail_info)
            self._handle_result(step, detail_info, 0)
        # 3. 清理防火墙配置
        step = HostEnvClearSteps.CLEAR_FIREWALL
        self.host_status_dict['current_step'] = step
        ret, err_info = self.clear_firewall_config(port=None, is_clear_config=True)
        if ret is False:
            detail_info = "CentOs7HostEnv::clear_host_env: step CLEAR_FIREWALL execute failed: " + err_info
            self.logger.error(detail_info)
            self._handle_result(step, detail_info, 2)
            #return
        else:
            detail_info = "CentOs7HostEnv::clear_host_env: step CLEAR_FIREWALL execute success"
            self.logger.info(detail_info)
            self._handle_result(step, detail_info, 0)
        # 4. 清理磁盘优化配置
        step = HostEnvClearSteps.CLEAR_DISK_OPTMIZE
        self.host_status_dict['current_step'] = step
        ret, err_info = self.clear_disk_optmize_script()
        if ret is False:
            detail_info = "CentOs7HostEnv::clear_host_env: step CLEAR_DISK_OPTMIZE execute failed: " + err_info
            self.logger.error(detail_info)
            self._handle_result(step, detail_info, 2)
            #return
        else:
            detail_info = "CentOs7HostEnv::clear_host_env: step CLEAR_DISK_OPTMIZE execute success"
            self.logger.info(detail_info)
            self._handle_result(step, detail_info, 0)
        # 5. 清理硬盘中断绑定配置
        step = HostEnvClearSteps.CLEAR_DISK_BREAK_BIND
        self.host_status_dict['current_step'] = step
        ret, err_info = self.clear_ssd_break_bind_script()
        if ret is False:
            detail_info = "CentOs7HostEnv::clear_host_env: step CLEAR_DISK_BREAK_BIND execute failed: " + err_info
            self.logger.error(detail_info)
            self._handle_result(step, detail_info, 2)
            #return
        else:
            detail_info = "CentOs7HostEnv::clear_host_env: step CLEAR_DISK_BREAK_BIND execute success"
            self.logger.info(detail_info)
            self._handle_result(step, detail_info, 0)
        # 6. 清理ntp配置配置
        step = HostEnvClearSteps.CLEAR_NTP_CONFIG
        self.host_status_dict['current_step'] = step
        ret, err_info = self.clear_ntp_config()
        if ret is False:
            detail_info = "CentOs7HostEnv::clear_host_env: step CLEAR_NTP_CONFIG execute failed: " + err_info
            self.logger.error(detail_info)
            self._handle_result(step, detail_info, 1)
            #return
        else:
            detail_info = "CentOs7HostEnv::clear_host_env: step CLEAR_NTP_CONFIG execute success"
            self.logger.info(detail_info)
            self._handle_result(step, detail_info, 0)
        # 7. 还原selinux配置
        '''
        step = HostEnvClearSteps.RECOVER_SELINUX_CONFIG
        self.host_status_dict['current_step'] = step
        ret, err_info = self.recover_selinux()
        if ret is False:
            detail_info = "CentOs7HostEnv::clear_host_env: step RECOVER_SELINUX_CONFIG execute failed: " + err_info
            self.logger.error(detail_info)
            self._handle_result(step, detail_info, 2)
            #return
        else:
            detail_info = "CentOs7HostEnv::clear_host_env: step RECOVER_SELINUX_CONFIG execute success"
            self.logger.info(detail_info)
            self._handle_result(step, detail_info, 0)
        '''
        # 8. 重启机器
        step = HostEnvClearSteps.REBOOT
        self.host_status_dict['current_step'] = step
        ret, err_info = self.reboot_host()
        if ret is False:
            detail_info = "CentOs7HostEnv::clear_host_env: step REBOOT execute failed, " + err_info
            self._handle_result(step, detail_info, 2)
            self.logger.error(detail_info)
            #return
        else:
            detail_info = "CentOs7HostEnv::clear_host_env: step REBOOT execute success"
            self.logger.info(detail_info)
            self._handle_result(step, detail_info, 0)
        return

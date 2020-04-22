#!/usr/bin/python
#coding=utf-8

import ConfigParser

ROOT_PATH= '/opt/ctc/cephmon/'
CEPHCONF_PATH = ' -c /opt/ctc/cephmon/conf/ceph/ceph.conf -k /opt/ctc/cephmon/conf/ceph/ceph.client.admin.keyring'

def _init():
    global _global_dict
    _global_dict = {}

def set_value(key,value):
    #定义一个全局变量
    _global_dict[key] = value

def get_value(key,defValue=None):
    #获得一个全局变量,不存在则返回默认值
    try:
        return _global_dict[key]
    except KeyError:
        return defValue

# 配置文件的读取
def config_get(filename, section, item, logger):
    try:
        # 读取配置文件
        config = ConfigParser.ConfigParser()
        with open(filename, "r") as cfgfile:
            config.readfp(cfgfile)
            itemval = config.get(section, item)
    except Exception as e:
        logger.error('read config file failed, error is ' + str(e))
        return False
    else:
        logger.info('read config %s-%s=%s' % (str(section), str(item), str(itemval)))
        return itemval


# 配置文件的设置
def config_set(filename, section, item, value, logger):
    try:
        # 读取配置文件
        config = ConfigParser.ConfigParser()
        with open(filename, "r") as cfgfile:
            config.readfp(cfgfile)
            config.set(section, item, value)
            config.write(open(filename, "w"))
    except Exception as e:
        logger.error('write config file failed, error is ' + str(e))
        return False
    else:
        logger.info('write config %s-%s=%s' % (str(section), str(item), str(value)))
        return True

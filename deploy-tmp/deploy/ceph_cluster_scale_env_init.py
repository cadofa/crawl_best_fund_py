#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import logging
import logging.config
import global_variable
import json
import threading
from ceph_cluster_env_init import *


class CephClusterScaleEnvInit(CephClusterEnvInit):
    # 这里考虑用继承，还是实例化CephClusterEnvInit对象，然后将CephClusterEnvInit接口调用封装到CephClusterScaleEnvInit接口中
    pass




# /usr/bin/python
# coding=utf-8

import paramiko
import global_list


# SSH连接类
class mySSH:
    def __init__(self, hostip, port=None, username=None):
        self.hostip = hostip
        if port is None:
            self.port = global_list.get_value('SSHPORT')
        else:
            self.port = port
        if username is None:
            self.username = global_list.get_value('SSHUSER')
        else:
            self.username = username
        self.obj = None
        self.objsftp = None
        self.resultList = list()

    # connect to client and open sftp
    def connect_with_sftp(self):
        try:
            self.obj = paramiko.SSHClient()
            self.obj.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.obj.connect(hostname=self.hostip, port=self.port, username=self.username, timeout=20)
            self.objsftp = self.obj.open_sftp()
        except Exception as e:
            return False, str(e)
        else:
            return True, 'OK'

    # connect to client only
    def connect(self):
        try:
            self.obj = paramiko.SSHClient()
            self.obj.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.obj.connect(hostname=self.hostip, port=self.port, username=self.username, timeout=20)
        except Exception as e:
            return False, str(e)
        else:
            return True, 'OK'

    # run command on remote
    def run_cmd(self, cmd):
        respdict = dict()
        # run command with sudo
        stdin, stdout, stderr = self.obj.exec_command("sudo " + cmd)
        tempstdout = stdout.read()

        channel = stdout.channel
        status = channel.recv_exit_status()
        respdict['ret'] = status

        if len(tempstdout) == 0:
            respdict['out'] = tempstdout
        elif tempstdout[-1] == '\n':
            respdict['out'] = tempstdout[:-1]
        else:
            respdict['out'] = tempstdout
        respdict['err'] = stderr.read()
        return respdict

    # run multi-command on remote
    def run_cmdlist(self, cmdlist):
        self.resultList = []
        for cmd in cmdlist:
            stdin, stdout, stderr = self.obj.exec_command(cmd)
            self.resultList.append(stdout)
        return self.resultList

    # get remote file via sftp
    def get(self, remotepath, localpath):
        try:
            self.objsftp.get(remotepath, localpath)
        except Exception as e:
            return False, str(e)
        else:
            return True, 'OK'

    # put file to remote via sftp
    def put(self, localpath, remotepath):
        try:
            if self.username == "root":
                self.objsftp.put(localpath, remotepath)
            else:
                filename = localpath.split("/")[-1]
                home_path_list = ["/home", self.username, filename]
                homepath = "/".join(home_path_list)
                self.objsftp.put(localpath, homepath)
                cmd = " ".join(["mv", homepath, remotepath])
                self.run_cmd(cmd)
        except Exception as e:
            return False, str(e)
        else:
            return True, 'OK'

    '''
    def getTarPackage(self,path):
        list = self.objsftp.listdir(path)
        for packageName in list:
            stdin,stdout,stderr  = self.obj.exec_command("cd " + path +";"
                                                         + "tar -zvcf /tmp/" + packageName
                                                         + ".tar.gz " + packageName)
            stdout.read()
            self.objsftp.get("/tmp/" + packageName + ".tar.gz","/tmp/" + packageName + ".tar.gz")
            self.objsftp.remove("/tmp/" + packageName + ".tar.gz")
            print "get package from " + packageName + " ok......"
    '''

    # close ssh
    def close(self):
        if self.objsftp is not None:
            self.objsftp.close()
            self.objsftp = None
        if self.obj is not None:
            self.obj.close()
            self.obj = None


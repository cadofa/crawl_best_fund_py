#!/bin/bash

touch /home/chen-test
if [ -z ${1} ] ;
then
        echo "USAGE: ./disk-optimize.sh <ahead-size(kb)>"
        exit 1
fi


devsinfo=$(lsblk -d -n|awk '{print $1}')

function disk_type(){
        #echo $1
        smartctlout=$(smartctl -a ${1}|grep SATA)
        #smartctlout=$(smartctl -a ${1}|grep SSD)
        devtype='sata'
        echo $devtype

}

for devname in ${devsinfo}
do
        #echo $devname
        echo "$1" > /sys/block/${devname}/queue/read_ahead_kb
        devpath=/dev/$devname
        hdparm -W 0 $devpath 0
        devtype=$(disk_type ${devpath})
        #echo $devtype
        if [ "$devtype" == "ssd" ] ;then
                echo "noop" > /sys/block/${devname}/queue/scheduler
        else
                echo "deadline" > /sys/block/${devname}/queue/scheduler
        fi

done


#!/bin/bash
total_cpus=`nproc`
config_nvme()
{
	current_cpu=0
	for dev in /sys/bus/pci/drivers/nvme/*
	do
		if [ ! -d $dev ]
		then
			continue
		fi
		if [ ! -d $dev/msi_irqs ]
		then
			continue
		fi
		for irq_info in $dev/msi_irqs/*
		do
#			if [ ! -f $irq_info ]
#			then
#				continue
#			fi
			current_cpu=$((current_cpu % total_cpus))
			cpu_mask=`printf "%x" $((1<<current_cpu))`
			irq=$(basename $irq_info)$a
			echo Setting IRQ $irq smp_affinity_list to $current_cpu
			echo $current_cpu > /proc/irq/$irq/smp_affinity_list
			current_cpu=$((current_cpu+1))
		done
	done
}
config_nvme
echo "done"

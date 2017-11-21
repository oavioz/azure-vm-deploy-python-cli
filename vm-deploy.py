#!/usr/bin/python3

import argparse
import json
import os
import subprocess as sp
import sys
import yaml
import time

def write_json(filename, data):
	f = open(filename, 'w')
	f.write(json.dumps(data, indent=4, separators=(',', ': ')))
	f.close()

parser = argparse.ArgumentParser(description='Deploy Linux Ubuntu 16.04-LTS VM on Azure')
parser.add_argument('-s', dest='subscription_id', required=True,
	help='Azure subscription id.')
parser.add_argument('-n', dest='name', required=True,
	help='Cluster name.')
parser.add_argument('-c', dest='vms', type=int, default=1,
	help='Virtual machine count [default=1].')
parser.add_argument('-r', dest='rbac', default='rbac.json',
    help='Service principal file, relative to output dir. Will be created if it does not exist. [default=rbac.json].')
parser.add_argument('-d', dest='disks', type=int, default=2,
	help='Disk count [default=2].')
parser.add_argument('-D', dest='disk_size', type=int, default=1024,
	help='Disk size (gb) [default=1024].')
args = parser.parse_args()

# stash output data
if not os.path.exists(args.name):
	os.mkdir(args.name)
elif not os.path.isdir(args.name):
	print(args.name + " exists and is not a directory.")
	sys.exit(1)

# create an ssh keypair
ssh_key = os.path.join(args.name, 'id_rsa')
ssh_key_pub = ssh_key + '.pub'
if not os.path.exists(ssh_key):
	azcmd = ['ssh-keygen', '-t', 'rsa', '-N', '', '-f', ssh_key]
	r = sp.check_output(azcmd)
ssh_key_data = open(ssh_key_pub).read()

# make sure we're using our subscription
azcmd = ['az', 'account', 'set', '-s', args.subscription_id]
r = sp.check_output(azcmd)

# prepare az service principals
rbac_file = os.path.join(args.name, args.rbac)
if not os.path.exists(rbac_file):
	azcmd = ['az', 'ad', 'sp', 'create-for-rbac',
		'--scopes=/subscriptions/{}'.format(args.subscription_id),
		'--role=Contributor']
	rbac_s = sp.check_output(azcmd, universal_newlines=True)
	f = open(rbac_file, 'w')
	f.write(rbac_s)
	f.close()
else:
	rbac_s = open(rbac_file).read()
rbac = json.loads(rbac_s)

# Preparing config json script for disk partition using vm extentions
config_script_data = {
   "fileUris": ["https://sademodata.blob.core.windows.net/scripts/bash/prep-data-disks.sh"],
   "commandToExecute": "bash prep-data-disks.sh " + str(args.disks)
 }
script_file = os.path.join(args.name, 'config-script.json')
f = open(script_file, 'w')
f.write(json.dumps(config_script_data))
f.close()
config_setting = args.name + '/config-script.json'

# create resource group and location	
rgName= args.name + "-rg"
rglocation="westus2"

azcmd = ['az', 'group', 'create', '--name', rgName, '--location', rglocation]
r = sp.check_output(azcmd, universal_newlines=True)

# Create a public IP address resource with a static IP address using the --allocation-method Static option.
# If you do not specify this option, the address is allocated dynamically. The address is assigned to the
# resource from a pool of IP adresses unique to each Azure region. The DnsName must be unique within the
# Azure location it's created in. Download and view the file from https://www.microsoft.com/en-us/download/details.aspx?id=41653#
# that lists the ranges for each region.

pipName = "PIPMemSQL1"
dnsName = args.name

azcmd = ['az', 'network', 'public-ip', 'create', '--name', pipName, '--resource-group', rgName, '--location', rglocation, '--allocation-method', 'Static', '--dns-name', dnsName ]
pip = sp.check_output(azcmd, universal_newlines=True)


# Create a virtual network with one subnet

vnetName = args.name + "-vnet"
vnetPrefix = "192.168.0.0/16"
subnetName = "MemSQLBackEnd"
subnetPrefix = "192.168.1.0/24"

azcmd = ['az', 'network', 'vnet', 'create', '--name', vnetName, '--resource-group', rgName, '--location', rglocation, '--address-prefix', vnetPrefix, '--subnet-name', subnetName, '--subnet-prefix', subnetPrefix]
vnet = sp.check_output(azcmd, universal_newlines=True)

# Create a network security group
# To control the flow of traffic in and out of your VMs, create a network security group

nsgName = args.name + "-nsg"
azcmd = ['az', 'network', 'nsg', 'create', '--resource-group', rgName, '--name', nsgName]
nsg = sp.check_output(azcmd, universal_newlines=True)
	
# Define rules that allow or deny the specific traffic. To allow inbound connections on port 22 (to support SSH)

sshRule = "MemSQLSecurityGroupRuleSSH"
azcmd = ['az', 'network', 'nsg', 'rule', 'create', '--resource-group', rgName, '--nsg-name', nsgName, '--name', sshRule, '--protocol', 'tcp', '--priority', '1000', '--destination-port-range', '22', '--access', 'allow']
nsg = sp.check_output(azcmd, universal_newlines=True)

memSQLDashboardRule = "memSQLDashboardRule"
# Allow inbound connections on port 9000
azcmd = ['az', 'network', 'nsg', 'rule', 'create', '--resource-group', rgName, '--nsg-name', nsgName, '--name', memSQLDashboardRule, '--protocol', 'tcp', '--priority', '1001', '--destination-port-range', '9000', '--access', 'allow']
nsg = sp.check_output(azcmd, universal_newlines=True)

# Create a network interface connected to the VNet with a static private IP address and associate the public IP address
# resource to the NIC.

nicName="ClickDVMNic-0"
privateIpAddress="192.168.1.101"

azcmd = ['az', 'network', 'nic', 'create', '--name', nicName, '--resource-group', rgName, '--location', rglocation, '--subnet', subnetName, '--vnet-name', vnetName, '--private-ip-address', privateIpAddress, '--public-ip-address', pipName, '--network-security-group', nsgName]
nic = sp.check_output(azcmd, universal_newlines=True)

# Create an availability set
# Availability sets help spread your VMs across fault domains and update domains. 
# Even though you only create one VM right now, it's best practice to use availability sets to make it easier to expand in the future.

availabilitySetName = "avs-memsql"
azcmd = ['az', 'vm', 'availability-set', 'create', '--name', availabilitySetName, '--resource-group', rgName]
avs = sp.check_output(azcmd, universal_newlines=True)

#azcmd = ['az', 'network', 'vnet', 'list', '-g', args.name]
#vnet = json.loads(sp.check_output(azcmd, universal_newlines=True))
#vnet_name = vnet[0]['name']
#subnet_name = vnet[0]['subnets'][0]['name']
#subnet_address_prefix = vnet[0]['subnets'][0]['addressPrefix']

time.sleep(30)

# create VMs server
for i in range(1, args.vms + 1):
	vm_name = 'memsql-vm-' + str(i)
	if i == 1:
		azcmd = ['az', 'vm', 'create', '-n', vm_name,
			'--admin-username', 'memsqladmin',
			'--resource-group', rgName,
			'--ssh-key-value', ssh_key_pub,
			'--size', 'Standard_F4',
			'--storage-sku', 'Standard_LRS',
			'--location', rglocation,
			'--availability-set', availabilitySetName,
			'--nics', nicName,
			'--image', 'Canonical:UbuntuServer:16.04-LTS:latest']
	else:
		azcmd = ['az', 'vm', 'create', '-n', vm_name,
			'--admin-username', 'memsqladmin',
			'--resource-group', rgName,
			'--ssh-key-value', ssh_key_pub,
			'--size', 'Standard_F4',
			'--storage-sku', 'Standard_LRS',
			'--vnet-name', vnetName,
			'--subnet', subnetName,
			'--location', rglocation,
			'--availability-set', availabilitySetName,
			'--public-ip-address', '',
			'--image', 'Canonical:UbuntuServer:16.04-LTS:latest']
	vm_create = sp.check_output(azcmd, universal_newlines=True)
	write_json(os.path.join(args.name, vm_name + '.json'), vm_create)

	# create and attach disks
	for i in range(1, args.disks + 1):
		r = sp.check_output(['az', 'vm', 'disk', 'attach', '--new',
			'--disk', vm_name + '-disk' + str(i),
			'--resource-group', rgName,
			'--vm-name', vm_name,
			'--size-gb', str(args.disk_size),
			'--sku', 'Standard_LRS']) 

	# run install script
	azcmd = ['az', 'vm', 'extension', 'set',
		'--resource-group', rgName,
		'--vm-name', vm_name,
		'--name', 'customScript',
		'--publisher', 'Microsoft.Azure.Extensions',
		'--settings', config_setting]
	r = sp.check_output(azcmd, universal_newlines=True)

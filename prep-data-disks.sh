#!/bin/bash
SSD_DISKS="$1"; shift

function die() {
  echo "$@" >&2
  exit 2
}

if ! [ -n "$SSD_DISKS"  -a "$SSD_DISKS" -ge 0 ] 2>/dev/null; then
  die "usage: $0 <number of ssd data disks> " >&2
fi
for lun_id in $(ls /dev/disk/azure/scsi1/lun* | grep 'lun[0-9]*$' | grep -o '[0-9]*$' | sort -n); do
  lun_dev="/dev/disk/azure/scsi1/lun$lun_id"
  part_dev="${lun_dev}-part1"
  [ -b "$lun_dev" ] || die "Internal Error: '$lun_dev' does not exist or is not a block device" >&2
  if [ -b "$part_dev" ]; then
    echo
    echo "skipping $lun_dev, it is already partitioned"
    echo
    continue
  fi
  if [ "$lun_id" -lt "$SSD_DISKS" ]; then
    disk_type='SSD'
    mount_point="/data/ssd$lun_id"
  else
    disk_type='HDD'
    mount_point="/data/hdd$lun_id"
  fi
  label=$(printf 'DATA_%02d_%s' $lun_id $disk_type)
  
  if grep -q "$label" /etc/fstab; then
    die "ERROR: label '$label' already in fstab. Aborting."
  fi
  if grep -q "$mount_point" /etc/fstab; then
    die "ERROR: mount point '$mount_point' already in fstab. Aborting"
  fi
  
  sudo parted --script $lun_dev mklabel gpt
  sudo parted --script $lun_dev -a optimal mkpart primary xfs 1 100%
  udevadm settle
  sudo mkfs.xfs -q -L "$label" "$part_dev"
  sudo mkdir -p "$mount_point"
  printf 'LABEL=%-15s %-15s xfs defaults,noatime,nodiratime,nofail    0 0\n' "$label" "$mount_point" | sudo tee -a /etc/fstab
done  

sudo mount -a


#!/bin/bash

set -e

POOL_NAME="data"
MOUNT_POINT="/hadoop/${POOL_NAME}"

log() {
    # Un-comment the following if you would like to enable logging to a service
    #curl -X POST -H "content-type:text/plain" --data-binary "${HOSTNAME} - $1" https://logs-01.loggly.com/inputs/<key>/tag/es-extension,${HOSTNAME}
    echo "$1"
}

bare_gpt_disks() {
    # Find gpt disks without partitions;
	# Create a gpt label where there is none at all.

    declare -a RET

    block_devs=$(ls -1 /dev/sd*|egrep -v "[0-9]$")
    for bd in ${block_devs} ; do
		# What kind of partition table
		table=$(parted -m ${bd} p 2>/dev/null | grep ${bd} | cut -d: -f6)
		case $table in
			gpt) # Count the number of partitions; parted has 2 info lines
				lc=$(parted -m ${bd} p 2>/dev/null | wc -l)
				if [ $lc -eq 2 ]; then RET+=" ${bd}" ; fi
				;;
			unknown) # Create a partition table if there's none
				parted -s ${bd} mklabel gpt
				RET+=" ${bd}"
				;;
			*) continue ;;
		esac
    done
    echo "${RET}"
}

if [ "${UID}" -ne 0 ]; then
    log "Script executed without root permissions"
    echo "You must be root to run this program." >&2
    exit 3
fi

while getopts b:sho: optname; do
	log "Option $optname set with value ${OPTARG}"
	case ${optname} in
		m) MOUNT_POINT=${OPTARG} ;;
		p) POOL_NAME=${OPTARG} ;;
		\?) #unrecognized option - show help
			echo -e \\n"Option -$OPTARG not allowed."
			exit 2
			;;
	esac
done

# Main
case `uname -v` in
	*buntu*)
		apt update
		apt -y install zfsutils-linux
		;;
esac

# Get device list
disks=($(bare_gpt_disks))
num_disks=${#disks[@]}
if [ $num_disks -lt 2 ]; then
	log "Only $num_disks empty disks detected"
	echo ${disks[0]}
	zpool create -m ${MOUNT_POINT} ${POOL_NAME} ${disks[0]}
	#exit 1
else
	echo "Disks are ${disks[@]}"

	#zpool create -m ${MOUNT_POINT} ${POOL_NAME} mirror ${disks[0]} ${disks[1]}

	# Add mirrored disks in pairs
	for (( i=2; i<${num_disks} ; i+=2 )) ; do
		if [ $((i+1)) -gt $num_disks ]; then
			break # we're odd
		fi
		zpool add ${POOL_NAME} mirror ${disks[i]} ${disks[i+1]}
done
fi




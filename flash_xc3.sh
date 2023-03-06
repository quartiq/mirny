#!/bin/bash

set -e
set -x

XC3SPROG=xc3sprog
CABLE=${1-xpc}

# /sbin/fxload -t fx2 -I /opt/Xilinx/14.7/ISE_DS/ISE/bin/lin64/xusb_xp2.hex -D /dev/bus/usb/001/*`cat /sys/bus/usb/devices/1-7.1/devnum`
# sleep 7
$XC3SPROG -c $CABLE -m /opt/Xilinx/14.7/ISE_DS/ISE/xbr/data -v build/mirny.jed:w

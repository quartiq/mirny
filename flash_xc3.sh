#!/bin/bash

set -e

XC3SPROG=xc3sprog
CABLE=$([[ -z "$1" ]] && echo "xpc" || echo "$1")

set -x
$XC3SPROG -c $CABLE -m /opt/Xilinx/14.7/ISE_DS/ISE/xbr/data -v build/mirny.jed:w

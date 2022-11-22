#!/bin/bash
set -e

/sbin/ip link set can0 down
/sbin/ip link set can0 up type can bitrate 10000
/sbin/ip link set can0 txqueuelen 10000

#!/bin/bash

set -v

rm -f /dev/shm/run_params.txt
rm -f /dev/shm/*.raw
rm -f /dev/shm/tstamps.csv
rm -f /dev/shm/hd0.32k
rm -f /dev/shm/process-video.sh
cp ./process-video.sh /dev/shm/process-video.sh
/home/pi/fork-raspiraw/camera_i2c > /dev/shm/run_params.txt
echo "${1}" >> /dev/shm/run_params.txt
echo "raspiraw version:" >> /dev/shm/run_params.txt
/home/pi/fork-raspiraw/raspiraw >> /dev/shm/run_params.txt
RASPIRAW_ARGS="${1}"
eval "/home/pi/fork-raspiraw/raspiraw ${RASPIRAW_ARGS}"
echo "Here is memory usage after capture:" >> /dev/shm/run_params.txt
df /dev/shm >> /dev/shm/run_params.txt

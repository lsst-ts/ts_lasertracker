#!/bin/sh
# Do the boring setup for a LaserTracker dev container

cd /home/saluser/gitdir/ts_lasertracker
eups declare -r . -t $USER
setup ts_lasertracker -t $USER

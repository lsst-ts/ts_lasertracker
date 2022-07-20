#!/bin/sh
# Do the boring setup for a MTAlignment dev container

cd /home/saluser/gitdir/ts_MTAlignment
eups declare -r . -t $USER
setup ts_MTAlignment -t $USER
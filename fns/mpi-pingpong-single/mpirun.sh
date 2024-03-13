#!/bin/sh

export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

read line
N=`echo $line | awk ' { print $1; } '`
ITER=`echo $line | awk ' { print $2; } '`
# N=${N:-4}

echo "running mpi with -n $N and $ITER iterations"

mpirun --allow-run-as-root -n "$N" python3 /userfunc/deployarchive/pingpong.py  $ITER

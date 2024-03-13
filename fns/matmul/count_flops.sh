#!/usr/bin/env bash
#

echo "N\tthreads\tFLOPS" > flops.dat
for n in `seq 100 100 20000`
do
  echo  -n "Running with N=$n"
  for thr in `seq 1 1`
  do
    echo -n "."
    flops=`OMP_NUM_THREADS=$thr perf stat -e avx_insts.all python3 ./matmul.py $n |& grep avx_insts.all | tr -d ',' | awk ' { print($1); }'`
    echo $n,$thr,$flops >> flops.dat
  done
  echo ""
done

#!/bin/bash
# 호스트에서 GPU·컨테이너 자원 사용률 기록 (비기능 테스트 중)
OUT=$1; DK="/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe"
nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used,power.draw --format=csv,noheader,nounits -lms 500 > $OUT/gpu.csv &
GP=$!
while [ -f $OUT/running ]; do
  T=$(date +%s.%N)
  "$DK" stats --no-stream --format "{{.Name}},{{.CPUPerc}},{{.MemUsage}}" 2>/dev/null | sed "s/^/$T,/" >> $OUT/stats.csv
done
kill $GP

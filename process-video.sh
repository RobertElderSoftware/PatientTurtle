#!/bin/bash

set -v 

ls *.raw | while read i; do cat hd0.32k "$i" > "$i".all; done     # add headers
ls *.all | while read i; do ~/dcraw/dcraw -f -o 1 -v  -6 -T -q 3 -W "$i"; done # Convert to .tiff
cat << EOF > make_concat.py
# Use TS information:
import csv

slowdownx = float(50)
last_microsecond = 0
with open('tstamps.csv') as csv_file:
  csv_reader = csv.reader(csv_file, delimiter=',')
  line_count = 0
  for row in csv_reader:
    current_microsecond = int(row[2])
    if line_count > 0:
      print("file 'out.%06d.raw.tiff'\nduration %08f" % (int(row[1]), slowdownx * float(current_microsecond - last_microsecond) / float(1000000)))
    line_count += 1
    last_microsecond = current_microsecond
EOF
python make_concat.py > ffmpeg_concats.txt
ffmpeg -f concat -safe 0 -i ffmpeg_concats.txt -vcodec libx265 -x265-params lossless -crf 0 -b:v 1M -pix_fmt yuv420p -vf "pad=ceil(iw/2)*2:ceil(ih/2)*2" output.mp4

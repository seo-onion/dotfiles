#!/bin/bash
MODE=$1
FILE=$2

if [ "$MODE" = "save" ]; then
    grimblast -f --notify --wait 0.3 save area "$FILE"
else
    grimblast -f --notify --wait 0.3 copy area
fi

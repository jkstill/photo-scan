#!/usr/bin/env bash

# Usage: load-photos-walk.sh [imageLimitCount] [commitEvery]
# Defaults: imageLimitCount=50, commitEvery=25
# This script loads photos from /mnt/photos into the database using load-photos-walk.py.
# a value of 0 for imageLimitCount means no limit (load all photos).
imageLimitCount=${1:-50}
commitEvery=${2:-25}

scriptDir=$(dirname "$(realpath "$0")")
cd "$scriptDir" || exit 1
logDir="$scriptDir/logs"
mkdir -p "$logDir"
timestamp=$(date +"%Y%m%d_%H%M%S")
logFile="$logDir/photo_loader_$timestamp.log"
#exec > >(tee -a "$logFile") 2>&1

export ORACLE_DSN='oraserver/pdb1.xyz.com'
export ORACLE_USER='scott'
export ORACLE_PASS='tiger'

# Ollama host (if same box, localhost is fine)
export OLLAMA_HOST='http://oraserver:11434'

#./load-photos-walk.py /mnt/photos \
./load-photos-walk.py /mnt/photos/vacation/Lincoln-City/2021 \
  --commit-every $commitEvery \
  --limit $imageLimitCount \
  --error-log $logFile


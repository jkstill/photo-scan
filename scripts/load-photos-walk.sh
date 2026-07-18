#!/usr/bin/env bash

# Usage: load-photos-walk.sh [imageLimitCount] [commitEvery]
# Defaults: imageLimitCount=50, commitEvery=25
# This script loads photos from /mnt/photos into the database using load-photos-walk.py.
# a value of 0 for imageLimitCount means no limit (load all photos).
#
# to scan all photos in /mnt/photos, use:
# ./load-photos-walk.sh 0 100
#
imageLimitCount=${1:-50}
commitEvery=${2:-25}

set -u

[[ -z "$OLLAMA_HOST" ]] && { 
cat <<EOF	

OLLAMA_HOST is not set. Please set it to the Ollama host (e.g., http://localhost:11434)"
Example: export OLLAMA_HOST=http://localhost:11434"

if ollama is running on the same box, you can use http://localhost:11434"

if ollama is running on a different box, use the IP address of that box"

Example: export OLLAMA_HOST=http://192.168.1.100:11434"

Test it with curl:

$  curl -s $OLLAMA_HOST/api/tags | grep -Eo gemma3
gemma3
gemma3
gemma3
gemma3
	
EOF

	exit 1
}

scriptDir=$(dirname "$(realpath "$0")")
appDir=$(dirname "$scriptDir")
cd "$appDir" || exit 1
logDir="$appDir/logs"
mkdir -p "$logDir"
timestamp=$(date +"%Y%m%d_%H%M%S")
logFile="$logDir/photo_loader_$timestamp.log"
#exec > >(tee -a "$logFile") 2>&1

./load-photos-walk.py /mnt/photos \
    --ollama-host $OLLAMA_HOST \
    --vision-model gemma3:12b \
    --embed-model mxbai-embed-large \
    --db photos.db \
    --commit-every $commitEvery \
    --limit $imageLimitCount


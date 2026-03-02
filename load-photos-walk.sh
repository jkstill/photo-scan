#!/usr/bin/env bash

# Usage: load-photos-walk.sh [imageLimitCount] [commitEvery]
# Defaults: imageLimitCount=50, commitEvery=25
# This script loads photos from /mnt/photos into the database using load-photos-walk.py.
# a value of 0 for imageLimitCount means no limit (load all photos).
imageLimitCount=${1:-50}
commitEvery=${2:-25}

set -u

credsFile='oracle-creds.txt'

[[ -r $credsFile ]] || { echo "$credsFile not readable"; exit 1; }

connection=''
username=''
password=''
ollamaHost=''

getCreds () {

	connection="$(grep '^connection' $credsFile | cut -f2- -d:)"
	username="$(grep '^username' $credsFile | cut -f2- -d:)"
	password="$(grep '^password' $credsFile | cut -f2- -d:)"
	ollamaHost="$(grep '^ollama_server' $credsFile | cut -f2- -d:)"

}

getCreds

cat <<-EOF

username: $username
password: $password
connection: $connection
ollamaHost: $ollamaHost

EOF

[[ -z $username ]] || [[ -z $password ]] || [[ -z $connection ]] || [[ -z $ollamaHost ]] && {
	echo "$credsFile must contain [connection,username,password]:value"
	echo
	exit 1
}


scriptDir=$(dirname "$(realpath "$0")")
cd "$scriptDir" || exit 1
logDir="$scriptDir/logs"
mkdir -p "$logDir"
timestamp=$(date +"%Y%m%d_%H%M%S")
logFile="$logDir/photo_loader_$timestamp.log"
#exec > >(tee -a "$logFile") 2>&1

export ORACLE_DSN="$connection"
export ORACLE_USER="$username"
export ORACLE_PASS="$password"

# Ollama host (if same box, localhost is fine)
export OLLAMA_HOST="$ollamaHost"

./load-photos-walk.py /mnt/photos \
  --commit-every $commitEvery \
  --limit $imageLimitCount \
  --vision-model 'gemma3:12b' \
  --error-log $logFile


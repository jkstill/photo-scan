#!/bin/bash

export PATH=/usr/local/bin/:$PATH

APP_HOME=/opt/photo-server
cd $APP_HOME  || { echo "failed to cd $APP_HOME"; exit 1; }

# use getops to get args for db, limit and web-port
# 
DB='photos.db'
LIMIT=25
WEB_PORT=8100

while getopts "d:l:p:" opt; do
  case $opt in
	 d) DB="$OPTARG" ;;
	 l) LIMIT="$OPTARG" ;;
	 p) WEB_PORT="$OPTARG" ;;
	 *) echo "Usage: $0 [-d db] [-l limit] [-p web-port]" >&2; exit 1 ;;
  esac
done

exec ./photo-match-display-server --db $DB --limit $LIMIT --web-port $WEB_PORT


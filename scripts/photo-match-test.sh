#!/usr/bin/env bash

scriptDir=$(dirname "$(realpath "$0")")

mkdir -p $HOME/Pictures/test

while IFS= read -r photo; do
	 echo "Matched photo: $photo"
	 cp -p "$photo" "$HOME/Pictures/test/"
done < <("$scriptDir/photo-match.sh")

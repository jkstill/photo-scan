#!/usr/bin/env bash

mkdir -p $HOME/Pictures/test

while IFS= read -r photo; do
	 echo "Matched photo: $photo"
	 cp -p "$photo" "$HOME/Pictures/test/"
done < <(./photo-match.sh)

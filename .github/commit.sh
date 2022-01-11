#!/usr/bin/bash

prepare_commit() {
  git config --global user.name "eol-vl"
  git config --global user.email 'eol-uchile@users.noreply.github.com'
  git add coverage-badge.svg
  git commit -m "Update coverage badge" 2> /dev/null
  if [ $? -eq 0 ]; then
    git push https://konialtamirano:$1@github.com/eol-virtuallabx/norteamericano-zoom-xblock.git HEAD:master;
  else
    echo "Skipped";
  fi
  # Force 0 as output
  echo "Completed"
}

prepare_commit $1
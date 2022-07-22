#!/bin/bash
FILE=~/.pylero

if [ ! -f $FILE ]; then

echo "[webservice]
url=https://polarion.example.com/polarion
svn_repo=https://polarion.example.com/repo
user=automation
password=fake_password
default_project=RHELBASEOS
" >  ~/.pylero

fi

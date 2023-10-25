#!/bin/bash

# Prepare the variables
MYVAR1="MYVAR1_VALUE"
MYVAR2="MYVAR2_VALUE"

# Write the variables to the environment file
echo "MYVAR1=$MYVAR1" >> $TMT_PLAN_ENVIRONMENT_FILE
echo "MYVAR2=$MYVAR2" >> $TMT_PLAN_ENVIRONMENT_FILE

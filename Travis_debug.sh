#!/usr/bin/bash
curl -s -X POST  -H "Content-Type: application/json" -H "Accept: application/json" -H "Travis-API-Version: 3" -H "Authorization: token $TOKEN" -d '{ "quiet": true }' https://api.travis-ci.org/job/$JOBID/debug  

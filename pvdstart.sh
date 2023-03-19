#!/bin/bash

source /home/barbs/pvd-server/env/bin/activate
PVD_SERVER_ENV='development' uvicorn app.main:app --reload

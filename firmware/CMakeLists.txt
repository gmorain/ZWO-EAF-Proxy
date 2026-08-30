# ESP-IDF project. Activate the toolchain first:
#   . /path/to/esp-idf/export.sh
#   idf.py set-target esp32s3 && idf.py build
cmake_minimum_required(VERSION 3.16)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(zwoproxy)

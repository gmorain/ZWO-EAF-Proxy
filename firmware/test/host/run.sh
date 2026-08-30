#!/bin/sh
# Host-side conformance tests. No board, no ESP-IDF toolchain.
set -e
cd "$(dirname "$0")"
FLAGS="-std=c++17 -Wall -Wextra -I../../main/include"
SRC=../../main
c++ $FLAGS test_descriptors.cpp $SRC/personas/eaf_descriptors.cpp -o /tmp/eaf_desc_test
c++ $FLAGS test_protocol.cpp    $SRC/personas/eaf_protocol.cpp    -o /tmp/eaf_proto_test
c++ $FLAGS test_persona.cpp     $SRC/personas/eaf_persona.cpp $SRC/personas/eaf_protocol.cpp \
    -o /tmp/eaf_persona_test
/tmp/eaf_desc_test
echo
/tmp/eaf_proto_test
echo
/tmp/eaf_persona_test

// Descriptor bytes the real EAF presents, from captures/01-enumerate.pcap.
//
// These are the reference, mirrored in host/src/zwoproxy/personas/descriptors.py.
// Do not edit them to make something pass; the capture is the authority.
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace eaf {

extern const uint8_t kDeviceDescriptor[18];
extern const uint8_t kConfigurationDescriptor[34];
extern const uint8_t kReportDescriptor[68];

// Index 0 is the LANGID (0x0409) as raw bytes; the rest are ASCII.
extern const char* kStrings[4];
constexpr size_t kStringCount = 4;

}  // namespace eaf

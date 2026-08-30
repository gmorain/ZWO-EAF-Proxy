// Conformance test: the firmware descriptors must equal the captured bytes.
//
// Runs on the build host with no board and no ESP-IDF. The reference hex below
// is the same text that appears in host/src/zwoproxy/personas/descriptors.py,
// both taken from captures/01-enumerate.pcap.
#include <cstdio>
#include <cstring>
#include <string>

#include "personas/eaf_descriptors.h"

namespace {

int failures = 0;

std::string hex(const uint8_t* data, size_t len) {
  std::string out;
  char buf[3];
  for (size_t i = 0; i < len; ++i) {
    snprintf(buf, sizeof(buf), "%02x", data[i]);
    out += buf;
  }
  return out;
}

void expect(const char* name, const uint8_t* got, size_t len, const char* want) {
  const std::string actual = hex(got, len);
  if (actual == want) {
    printf("  ok    %s (%zu bytes)\n", name, len);
    return;
  }
  printf("  FAIL  %s\n    got  %s\n    want %s\n", name, actual.c_str(), want);
  ++failures;
}

}  // namespace

int main() {
  printf("firmware descriptors vs captures/01-enumerate.pcap\n");

  expect("device", eaf::kDeviceDescriptor, sizeof(eaf::kDeviceDescriptor),
         "1201000200000040c303101f000101020301");

  expect("configuration", eaf::kConfigurationDescriptor, sizeof(eaf::kConfigurationDescriptor),
         "09022200010100a0320904000001030000000921110100012244000705810310000a");

  expect("report", eaf::kReportDescriptor, sizeof(eaf::kReportDescriptor),
         "0600ff0901a1018501950f750826ff001500090181028502950f750826ff0015000901810285"
         "03950f750826ff001500090191028504950f750826ff00150009019102c0");

  // A mismatch here makes a host ask for the wrong number of report bytes.
  const uint16_t hid_report_length =
      eaf::kConfigurationDescriptor[25] | (eaf::kConfigurationDescriptor[26] << 8);
  if (hid_report_length == sizeof(eaf::kReportDescriptor)) {
    printf("  ok    HID wLength agrees with the report descriptor (%u)\n", hid_report_length);
  } else {
    printf("  FAIL  HID wLength %u but report descriptor is %zu bytes\n", hid_report_length,
           sizeof(eaf::kReportDescriptor));
    ++failures;
  }

  const char* strings[] = {"ZWO", "ZWO Device", "123456"};
  for (int i = 0; i < 3; ++i) {
    if (strcmp(eaf::kStrings[i + 1], strings[i]) == 0) {
      printf("  ok    string %d = \"%s\"\n", i + 1, strings[i]);
    } else {
      printf("  FAIL  string %d = \"%s\", want \"%s\"\n", i + 1, eaf::kStrings[i + 1], strings[i]);
      ++failures;
    }
  }

  printf(failures ? "\n%d FAILED\n" : "\nall passed\n", failures);
  return failures ? 1 : 0;
}

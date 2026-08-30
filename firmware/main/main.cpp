// ZWO-EAF-Proxy firmware.
//
// Presents as a ZWO EAF: descriptors from captures/01-enumerate.pcap, register
// behaviour from docs/protocol/registers.md. The focuser behind it is simulated
// for now. See specs/features/001-eaf-persona-emulator.md.

#include <string.h>

#include "backends/simulated_focuser.h"
#include "class/hid/hid_device.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "personas/eaf_descriptors.h"
#include "personas/eaf_persona.h"
#include "personas/eaf_protocol.h"
#include "tinyusb.h"

namespace {

const char* kTag = "eaf";

SimulatedFocuser focuser(CONFIG_EAF_START_POSITION, CONFIG_EAF_STEPS_PER_SECOND,
                         CONFIG_EAF_TEMPERATURE_CENTI);

// Register 0x0C, from CONFIG_EAF_SERIAL_HEX so no unit's serial is compiled in
// from this repository. Malformed configuration leaves the body zeroed.
uint8_t serial[eaf::kBodySize] = {0};

eaf::EafPersona persona(focuser, serial, CONFIG_EAF_TEMPERATURE_CENTI,
                        CONFIG_EAF_FW_MAJOR, CONFIG_EAF_FW_MINOR, CONFIG_EAF_FW_PATCH);

void LoadSerial() {
  const char* hex = CONFIG_EAF_SERIAL_HEX;
  for (size_t i = 0; i < 8 && hex[2 * i] && hex[2 * i + 1]; ++i) {
    unsigned value = 0;
    for (int nibble = 0; nibble < 2; ++nibble) {
      const char c = hex[2 * i + nibble];
      const int digit = (c >= '0' && c <= '9')   ? c - '0'
                        : (c >= 'a' && c <= 'f') ? c - 'a' + 10
                        : (c >= 'A' && c <= 'F') ? c - 'A' + 10
                                                 : -1;
      if (digit < 0) return;
      value = (value << 4) | static_cast<unsigned>(digit);
    }
    serial[i] = static_cast<uint8_t>(value);
  }
}

}  // namespace

extern "C" const uint8_t* tud_hid_descriptor_report_cb(uint8_t instance) {
  (void)instance;
  return eaf::kReportDescriptor;
}

// The real device STALLs GET_DESCRIPTOR(DEVICE_QUALIFIER), three times per
// enumeration, and the ASIAIR proceeds. Returning null stalls it deliberately
// rather than by omission: answering would advertise high speed, and the link is
// full speed. Only compiled when TinyUSB offers the hook.
#if TUD_OPT_HIGH_SPEED
extern "C" const uint8_t* tud_descriptor_device_qualifier_cb(void) {
  return nullptr;
}
#endif

// Endpoint 0x81 is declared and polled about 125 times a second, and the real
// device NAKs every one: all protocol rides control transfers. Nothing here ever
// calls tud_hid_report, so this should not fire. If it does, something started
// writing to the endpoint and the persona has diverged from the device.
extern "C" void tud_hid_report_complete_cb(uint8_t instance, uint8_t const* report,
                                           uint16_t len) {
  (void)instance;
  (void)report;
  ESP_LOGE(kTag, "wrote %u bytes to the interrupt endpoint; the real EAF never does", len);
}

extern "C" uint16_t tud_hid_get_report_cb(uint8_t instance, uint8_t report_id,
                                          hid_report_type_t report_type, uint8_t* buffer,
                                          uint16_t reqlen) {
  (void)instance;
  (void)report_id;
  if (report_type != HID_REPORT_TYPE_FEATURE || reqlen < eaf::kReportSize) return 0;

  // TinyUSB carries the report ID separately: it prepends the ID on GET_REPORT
  // and strips it on SET_REPORT. The codec speaks whole wire reports, so stage
  // a full one here and hand back everything after the ID.
  uint8_t staged[eaf::kReportSize];
  if (persona.CurrentReply(staged, sizeof(staged)) == 0) return 0;
  const size_t payload = eaf::kReportSize - 1;
  memcpy(buffer, staged + 1, payload);
  return static_cast<uint16_t>(payload);
}

extern "C" void tud_hid_set_report_cb(uint8_t instance, uint8_t report_id,
                                      hid_report_type_t report_type, uint8_t const* buffer,
                                      uint16_t bufsize) {
  (void)instance;
  if (report_type != HID_REPORT_TYPE_FEATURE) return;

  // Put the report ID back in front so the codec sees a whole wire report.
  uint8_t staged[eaf::kReportSize];
  staged[0] = report_id;
  const size_t copied = bufsize < sizeof(staged) - 1 ? bufsize : sizeof(staged) - 1;
  memcpy(staged + 1, buffer, copied);

  const eaf::Command command = eaf::ParseCommand(staged, copied + 1);
  if (command.kind == eaf::CommandKind::kMalformed) {
    ESP_LOGW(kTag, "ignoring malformed report, %u bytes", bufsize);
  }
  persona.Apply(command);
}

extern "C" void app_main(void) {
  const tinyusb_config_t config = {
      .device_descriptor = reinterpret_cast<const tusb_desc_device_t*>(eaf::kDeviceDescriptor),
      .string_descriptor = eaf::kStrings,
      .string_descriptor_count = static_cast<int>(eaf::kStringCount),
      .external_phy = false,
      .configuration_descriptor = eaf::kConfigurationDescriptor,
      .self_powered = false,
      .vbus_monitor_io = -1,
  };

  LoadSerial();
  ESP_ERROR_CHECK(tinyusb_driver_install(&config));
  ESP_LOGI(kTag, "presenting as ZWO EAF");

  // Integrate against the real clock. pdMS_TO_TICKS of anything under one
  // FreeRTOS tick rounds to zero, so a delay cannot be used to measure time.
  int64_t last_us = esp_timer_get_time();
  while (true) {
    const int64_t now_us = esp_timer_get_time();
    const int32_t elapsed_ms = static_cast<int32_t>((now_us - last_us) / 1000);
    if (elapsed_ms > 0) {
      focuser.advance(elapsed_ms);
      last_us = now_us;
    }
    vTaskDelay(pdMS_TO_TICKS(10));
  }
}

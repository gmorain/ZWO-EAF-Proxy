// ZWO EAF emulation: the register file the host reads and writes.
//
// Holds no USB. The transport hands it decoded commands and asks for the reply,
// so this layer is exercised on the build host with a fake focuser.
#pragma once

#include "focuser.h"
#include "personas/eaf_protocol.h"

namespace eaf {

class EafPersona {
 public:
  // `serial` is kBodySize bytes: 0x6000 then a six-byte MAC, zero padded.
  // `version` is the firmware triplet reported by register 0x04. Matching the
  // real release keeps the ASIAIR quiet; a lower one makes it offer an upgrade.
  EafPersona(Focuser& focuser, const uint8_t* serial, int32_t fallback_temperature_centi,
             uint8_t major, uint8_t minor, uint8_t patch);

  // Act on one decoded command and remember what to answer next.
  void Apply(const Command& command);

  // Writes a whole wire report for whichever register was last named.
  // Returns bytes written, 0 if out is too small.
  size_t CurrentReply(uint8_t* out, size_t out_size);

  uint8_t pending() const { return pending_; }

 private:
  Focuser& focuser_;
  uint8_t serial_[kBodySize];
  int32_t fallback_temperature_centi_;
  uint8_t version_[3];
  uint8_t pending_ = reg::kState;
  uint8_t settings_ = kSettingsBase;  // body byte 9: the host owns it, we store it
};

}  // namespace eaf

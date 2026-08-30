#include "personas/eaf_persona.h"

#include <string.h>

namespace eaf {

EafPersona::EafPersona(Focuser& focuser, const uint8_t* serial,
                       int32_t fallback_temperature_centi, uint8_t major, uint8_t minor,
                       uint8_t patch)
    : focuser_(focuser), fallback_temperature_centi_(fallback_temperature_centi) {
  memcpy(serial_, serial, sizeof(serial_));
  version_[0] = major;
  version_[1] = minor;
  version_[2] = patch;
}

void EafPersona::Apply(const Command& command) {
  switch (command.kind) {
    case CommandKind::kReadRegister:
      pending_ = command.reg;
      return;
    case CommandKind::kWriteState:
      pending_ = reg::kState;
      if (command.settings != kSettingsAbsent) {
        settings_ = static_cast<uint8_t>(command.settings);
      }
      if (command.go) {
        focuser_.moveTo(static_cast<int32_t>(command.position));
      } else if (command.sync) {
        // Not a halt. The device is redefined to be at this position without
        // moving, which is how the host zeroes a focuser.
        focuser_.setPosition(static_cast<int32_t>(command.position));
      } else {
        // Halt ignores the position it carries: the real device stops where it
        // is and reports where it landed.
        focuser_.halt();
      }
      return;
    case CommandKind::kMalformed:
      return;
  }
}

size_t EafPersona::CurrentReply(uint8_t* out, size_t out_size) {
  uint8_t body[kBodySize] = {0};
  switch (pending_) {
    case reg::kState: {
      int32_t centi = focuser_.temperature();
      if (centi == kUnsupported) centi = fallback_temperature_centi_;
      EncodeState(focuser_.isMoving(), static_cast<uint32_t>(focuser_.position()), centi,
                  settings_, body);
      break;
    }
    case reg::kIdentity:
      EncodeIdentity(version_[0], version_[1], version_[2], body);
      break;
    case reg::kSerial:
      memcpy(body, serial_, sizeof(body));
      break;
    default:
      // No capture shows this device refusing a register, so there is no
      // observed behaviour to copy. Answer the way 0x0D does.
      break;
  }
  return FrameReply(pending_, body, out, out_size);
}

}  // namespace eaf

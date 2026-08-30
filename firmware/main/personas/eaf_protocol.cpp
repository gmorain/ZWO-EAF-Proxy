#include "personas/eaf_protocol.h"

#include <string.h>

namespace eaf {

const uint8_t kIdentityModel[5] = {
    0x45,                    // unexplained, reproduced verbatim
    0x45, 0x41, 0x46, 0x4E,  // "EAFN"
};

void EncodeIdentity(uint8_t major, uint8_t minor, uint8_t patch, uint8_t* body) {
  memset(body, 0, kBodySize);
  body[0] = major;
  body[1] = minor;
  body[2] = patch;
  memcpy(body + 3, kIdentityModel, sizeof(kIdentityModel));
}

Command ParseCommand(const uint8_t* data, size_t length) {
  Command out;
  if (data == nullptr || length < 5) return out;
  if (data[0] != kReportOut) return out;
  if (data[1] != kMagic0 || data[2] != kMagic1) return out;

  const uint8_t target = data[3];
  if (target == reg::kRead) {
    out.kind = CommandKind::kReadRegister;
    out.reg = data[4];
    return out;
  }
  if (target == reg::kState) {
    if (length < 10) return out;  // truncated before the position
    out.kind = CommandKind::kWriteState;
    out.go = data[4] != 0;
    out.sync = length > 10 && data[10] != 0;
    out.position = (static_cast<uint32_t>(data[6]) << 24) |
                   (static_cast<uint32_t>(data[7]) << 16) |
                   (static_cast<uint32_t>(data[8]) << 8) | data[9];
    if (length > 13) out.settings = data[13];
    return out;
  }
  return out;
}

size_t FrameReply(uint8_t reg_number, const uint8_t* body, uint8_t* out, size_t out_size) {
  if (body == nullptr || out == nullptr || out_size < kReportSize) return 0;
  out[0] = kReportIn;
  out[1] = kMagic0;
  out[2] = kMagic1;
  out[3] = reg_number;
  memcpy(out + 4, body, kBodySize);
  return kReportSize;
}

void EncodeState(bool moving, uint32_t position, int32_t temperature_centi, uint8_t settings,
                 uint8_t* body) {
  int32_t raw = temperature_centi + kTemperatureBias;
  if (raw < 0) raw = 0;
  if (raw > 0xFFFF) raw = 0xFFFF;

  body[0] = moving ? 1 : 0;
  body[1] = 0;
  body[2] = static_cast<uint8_t>(position >> 24);
  body[3] = static_cast<uint8_t>(position >> 16);
  body[4] = static_cast<uint8_t>(position >> 8);
  body[5] = static_cast<uint8_t>(position);
  body[6] = 0;
  body[7] = static_cast<uint8_t>(raw >> 8);
  body[8] = static_cast<uint8_t>(raw);
  body[9] = settings;
  body[10] = static_cast<uint8_t>(kTemperatureBias >> 8);
  body[11] = static_cast<uint8_t>(kTemperatureBias);
}

}  // namespace eaf

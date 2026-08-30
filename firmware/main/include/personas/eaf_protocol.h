// EAF report codec. Mirrors host/src/zwoproxy/personas/protocol.py.
//
// Pure: no ESP-IDF, no I/O, so test/host can exercise it against the same
// captured bytes the Python side uses. Field meanings are in
// docs/protocol/registers.md.
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace eaf {

constexpr uint8_t kMagic0 = 0x7E;
constexpr uint8_t kMagic1 = 0x5A;
constexpr uint8_t kReportIn = 1;    // GET_REPORT, feature wValue 0x0301
constexpr uint8_t kReportOut = 3;   // SET_REPORT, feature wValue 0x0303
constexpr size_t kReportSize = 16;  // report id plus 15 payload bytes
constexpr size_t kBodySize = 12;    // payload after <id> 7E 5A <register>

constexpr int32_t kTemperatureBias = 30000;

// Body byte 9 of register 0x03. The host owns it, the device only stores it.
constexpr uint8_t kSettingsBase = 0x01;     // set in every capture, meaning unknown
constexpr uint8_t kSettingsReverse = 0x02;  // the ASIAIR's focuser Reverse toggle
constexpr int16_t kSettingsAbsent = -1;     // report was too short to carry it

namespace reg {
constexpr uint8_t kRead = 0x02;
constexpr uint8_t kState = 0x03;
constexpr uint8_t kIdentity = 0x04;
constexpr uint8_t kSerial = 0x0C;
constexpr uint8_t kUnknown0D = 0x0D;
}  // namespace reg

enum class CommandKind { kMalformed, kReadRegister, kWriteState };

struct Command {
  CommandKind kind = CommandKind::kMalformed;
  uint8_t reg = 0;        // kReadRegister: which register to read
  bool go = false;        // kWriteState: 1 moves
  bool sync = false;      // kWriteState: with go clear, sets the current position
  uint32_t position = 0;  // kWriteState: the target, or the position to set
  int16_t settings = kSettingsAbsent;  // kWriteState: body byte 9, or kSettingsAbsent
};

// Decodes one SET_REPORT payload. Bytes past the arguments a command defines are
// ignored: the host leaks uninitialised heap into the padding.
Command ParseCommand(const uint8_t* data, size_t length);

// Writes kReportSize bytes into out. Returns bytes written, 0 if body is wrong.
size_t FrameReply(uint8_t reg, const uint8_t* body, uint8_t* out, size_t out_size);

// Builds the register 0x03 body. Temperature is hundredths of a degree Celsius,
// matching Focuser::temperature(). `settings` is byte 9: echo back whatever the
// host last wrote, or the ASIAIR's Reverse toggle never appears to take.
void EncodeState(bool moving, uint32_t position, int32_t temperature_centi, uint8_t settings,
                 uint8_t* body);

// Byte 3 (0x45) is unexplained and reproduced verbatim, then ASCII "EAFN".
extern const uint8_t kIdentityModel[5];

// Register 0x04: version triplet then the model, zero padded.
void EncodeIdentity(uint8_t major, uint8_t minor, uint8_t patch, uint8_t* body);

}  // namespace eaf

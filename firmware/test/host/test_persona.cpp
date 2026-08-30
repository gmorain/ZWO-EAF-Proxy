// The register dispatch: which register answers what, and what a write does.
//
// This layer was silently wrong once. Every codec test passed while the persona
// answered register 0x03 to every read, because the fault was here.
#include <cstdio>
#include <cstring>
#include <string>

#include "personas/eaf_persona.h"

namespace {
int failures = 0;

std::string hex(const uint8_t* d, size_t n) {
  std::string s; char b[3];
  for (size_t i = 0; i < n; ++i) { snprintf(b, sizeof(b), "%02x", d[i]); s += b; }
  return s;
}
void check(const char* name, bool ok, const char* got = "") {
  printf(ok ? "  ok    %s\n" : "  FAIL  %s  got %s\n", name, got);
  if (!ok) ++failures;
}

class FakeFocuser : public Focuser {
 public:
  bool begin() override { return true; }
  int32_t position() override { return position_; }
  bool moveTo(int32_t t) override { target_ = t; moving_ = true; return true; }
  bool halt() override { moving_ = false; target_ = position_; return true; }
  bool setPosition(int32_t p) override { position_ = p; target_ = p; moving_ = false; return true; }
  bool isMoving() override { return moving_; }
  int32_t maxStep() override { return 0x7FFFFFFF; }
  int32_t temperature() override { return temperature_; }

  int32_t position_ = 3000, target_ = 3000, temperature_ = 2150;
  bool moving_ = false;
};

const uint8_t kSerial[eaf::kBodySize] = {0x60, 0x00, 0xAA, 0xBB, 0xCC, 0xDD,
                                         0xEE, 0xFF, 0x00, 0x00, 0x00, 0x00};

eaf::Command Read(uint8_t r) {
  eaf::Command c; c.kind = eaf::CommandKind::kReadRegister; c.reg = r; return c;
}
eaf::Command Write(bool go, uint32_t pos, bool sync = false) {
  eaf::Command c; c.kind = eaf::CommandKind::kWriteState;
  c.go = go; c.position = pos; c.sync = sync; return c;
}
}  // namespace

int main() {
  printf("register dispatch\n");
  uint8_t out[eaf::kReportSize];

  {  // Each register answers with its own content, not a neighbour's.
    FakeFocuser f;
    eaf::EafPersona p(f, kSerial, 2000, 3, 8, 2);

    p.Apply(Read(eaf::reg::kIdentity));
    p.CurrentReply(out, sizeof(out));
    check("read 0x04 answers identity", hex(out, sizeof(out)) == "017e5a04030802454541464e00000000",
          hex(out, sizeof(out)).c_str());

    // The version is configurable so the ASIAIR can be kept quiet, or made to
    // offer an upgrade by reporting a release behind the real one.
    FakeFocuser older_focuser;
    eaf::EafPersona older(older_focuser, kSerial, 2000, 3, 7, 0);
    older.Apply(Read(eaf::reg::kIdentity));
    older.CurrentReply(out, sizeof(out));
    check("version is configurable", hex(out, sizeof(out)) == "017e5a04030700454541464e00000000",
          hex(out, sizeof(out)).c_str());

    p.Apply(Read(eaf::reg::kSerial));
    p.CurrentReply(out, sizeof(out));
    check("read 0x0C answers serial", hex(out, sizeof(out)) == "017e5a0c6000aabbccddeeff00000000",
          hex(out, sizeof(out)).c_str());

    p.Apply(Read(eaf::reg::kState));
    p.CurrentReply(out, sizeof(out));
    check("read 0x03 answers state", hex(out, sizeof(out)) == "017e5a03000000000bb8007d96017530",
          hex(out, sizeof(out)).c_str());

    p.Apply(Read(eaf::reg::kUnknown0D));
    p.CurrentReply(out, sizeof(out));
    check("read 0x0D answers a zero body", hex(out, sizeof(out)) == "017e5a0d000000000000000000000000",
          hex(out, sizeof(out)).c_str());

    p.Apply(Read(0x77));
    p.CurrentReply(out, sizeof(out));
    check("unobserved register echoes itself, zero body",
          hex(out, sizeof(out)) == "017e5a77000000000000000000000000", hex(out, sizeof(out)).c_str());
  }

  {  // Writes reach the focuser, and reads afterwards report state.
    FakeFocuser f;
    eaf::EafPersona p(f, kSerial, 2000, 3, 8, 2);

    p.Apply(Write(true, 15000));
    check("move reaches the focuser", f.target_ == 15000 && f.moving_);
    check("a write leaves state pending", p.pending() == eaf::reg::kState);

    f.position_ = 9000;
    p.Apply(Write(false, 1));
    check("halt reaches the focuser", !f.moving_);
    check("halt ignores the position it carries", f.target_ == 9000);
  }

  {  // A sync redefines where the device is, without travelling there.
    FakeFocuser f;
    eaf::EafPersona p(f, kSerial, 2000, 3, 8, 2);

    p.Apply(Write(false, 0, true));
    check("zero redefines position without moving", f.position_ == 0 && !f.moving_);

    p.Apply(Write(false, 1234, true));
    check("sync sets an arbitrary position", f.position_ == 1234);
  }

  {  // A malformed command must not disturb what the host asked for.
    FakeFocuser f;
    eaf::EafPersona p(f, kSerial, 2000, 3, 8, 2);
    p.Apply(Read(eaf::reg::kIdentity));
    eaf::Command bad;  // kMalformed
    p.Apply(bad);
    check("malformed leaves the pending register alone", p.pending() == eaf::reg::kIdentity);
  }

  {  // A backend with no probe falls back rather than reporting nonsense.
    FakeFocuser f;
    f.temperature_ = kUnsupported;
    eaf::EafPersona p(f, kSerial, 2000, 3, 8, 2);
    p.Apply(Read(eaf::reg::kState));
    p.CurrentReply(out, sizeof(out));
    // temperature is report bytes 11..12, so hex offset 22
    check("unsupported temperature uses the fallback",
          hex(out, sizeof(out)).substr(22, 4) == "7d00", hex(out, sizeof(out)).c_str());
  }

  {  // Body byte 9 is the host's Reverse setting. Store it, echo it. Emitting a
     // constant makes the toggle appear to never take. See 18-reverse.pcap.
    FakeFocuser f;
    eaf::EafPersona p(f, kSerial, 2000, 3, 8, 2);
    p.Apply(Read(eaf::reg::kState));
    p.CurrentReply(out, sizeof(out));
    check("settings default to the base bit", out[13] == eaf::kSettingsBase);

    eaf::Command on;
    on.kind = eaf::CommandKind::kWriteState;
    on.position = 5000;
    on.settings = eaf::kSettingsBase | eaf::kSettingsReverse;
    p.Apply(on);
    p.CurrentReply(out, sizeof(out));
    check("reverse on is echoed back", out[13] == (eaf::kSettingsBase | eaf::kSettingsReverse));

    eaf::Command off = on;
    off.settings = eaf::kSettingsBase;
    p.Apply(off);
    p.CurrentReply(out, sizeof(out));
    check("reverse off is echoed back", out[13] == eaf::kSettingsBase);

    eaf::Command silent = on;  // a report too short to carry byte 9
    silent.settings = eaf::kSettingsAbsent;
    p.Apply(silent);
    p.CurrentReply(out, sizeof(out));
    check("an absent settings byte leaves the stored value alone",
          out[13] == eaf::kSettingsBase);
  }

  printf(failures ? "\n%d FAILED\n" : "\nall passed\n", failures);
  return failures ? 1 : 0;
}

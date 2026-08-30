// The C++ codec must agree with the wire, same reference bytes as the Python one.
#include <cstdio>
#include <cstring>
#include <string>

#include "personas/eaf_protocol.h"

namespace {
int failures = 0;

std::string hex(const uint8_t* d, size_t n) {
  std::string s; char b[3];
  for (size_t i = 0; i < n; ++i) { snprintf(b, sizeof(b), "%02x", d[i]); s += b; }
  return s;
}
void check(const char* name, bool ok, const char* detail = "") {
  printf(ok ? "  ok    %s\n" : "  FAIL  %s %s\n", name, detail);
  if (!ok) ++failures;
}
size_t unhex(const char* h, uint8_t* out) {
  size_t n = 0;
  for (; h[2 * n]; ++n) {
    unsigned v; sscanf(h + 2 * n, "%2x", &v); out[n] = static_cast<uint8_t>(v);
  }
  return n;
}
}  // namespace

int main() {
  printf("C++ codec vs captured bytes\n");
  uint8_t buf[64];

  // captures/03-move-halt.pcap and 08-fwcheck.pcap
  size_t n = unhex("037e5a02040000000000000000000000", buf);
  eaf::Command c = eaf::ParseCommand(buf, n);
  check("read 0x04", c.kind == eaf::CommandKind::kReadRegister && c.reg == 0x04);

  n = unhex("037e5a020c0000000000000000000000", buf);
  c = eaf::ParseCommand(buf, n);
  check("read 0x0C", c.kind == eaf::CommandKind::kReadRegister && c.reg == 0x0C);

  n = unhex("037e5a03010000004268000000017530", buf);
  c = eaf::ParseCommand(buf, n);
  check("move to 17000", c.kind == eaf::CommandKind::kWriteState && c.go && c.position == 17000);

  n = unhex("037e5a03000000001df7000000017530", buf);
  c = eaf::ParseCommand(buf, n);
  check("halt at 7671", c.kind == eaf::CommandKind::kWriteState && !c.go && c.position == 7671);

  // A real reply the device sent: position 1000, 28.50 C, not moving.
  uint8_t body[eaf::kBodySize], reply[eaf::kReportSize];
  eaf::EncodeState(false, 1000, 2850, eaf::kSettingsBase, body);
  eaf::FrameReply(eaf::reg::kState, body, reply, sizeof(reply));
  const std::string want = "017e5a030000000003e8008052017530";
  check("state reply byte for byte", hex(reply, sizeof(reply)) == want,
        hex(reply, sizeof(reply)).c_str());

  // Body byte 9 is the ASIAIR's Reverse toggle, not part of a constant tail.
  // Bytes from captures/18-reverse.pcap, Reverse switched on then off.
  n = unhex("037e5a0300000000138800000003" "7530", buf);
  c = eaf::ParseCommand(buf, n);
  check("reverse on is a write carrying the bit",
        c.kind == eaf::CommandKind::kWriteState && !c.go && !c.sync && c.position == 5000 &&
            (c.settings & eaf::kSettingsReverse));

  n = unhex("037e5a0300000000138800000001" "7530", buf);
  c = eaf::ParseCommand(buf, n);
  check("reverse off clears the bit", !(c.settings & eaf::kSettingsReverse));

  n = unhex("037e5a030000000013880000", buf);  // truncated before byte 9
  c = eaf::ParseCommand(buf, n);
  check("a short report reports no settings", c.settings == eaf::kSettingsAbsent);

  eaf::EncodeState(false, 5000, 2750, eaf::kSettingsBase | eaf::kSettingsReverse, body);
  eaf::FrameReply(eaf::reg::kState, body, reply, sizeof(reply));
  check("a reply echoes the settings byte",
        hex(reply, sizeof(reply)) == "017e5a0300000000138800" "7fee" "037530",
        hex(reply, sizeof(reply)).c_str());

  uint8_t identity[eaf::kBodySize];
  eaf::EncodeIdentity(3, 8, 2, identity);
  eaf::FrameReply(eaf::reg::kIdentity, identity, reply, sizeof(reply));
  check("identity reply byte for byte",
        hex(reply, sizeof(reply)) == "017e5a04030802454541464e00000000",
        hex(reply, sizeof(reply)).c_str());

  // captures/15-zero-position.pcap: the real EAF zeroed while sitting at 5000.
  n = unhex("037e5a03" "000000000000010000017530", buf);
  c = eaf::ParseCommand(buf, n);
  check("zero is a sync, not a halt",
        c.kind == eaf::CommandKind::kWriteState && !c.go && c.sync && c.position == 0);

  n = unhex("037e5a03" "000000001df7000000017530", buf);
  c = eaf::ParseCommand(buf, n);
  check("a halt has the sync flag clear",
        c.kind == eaf::CommandKind::kWriteState && !c.go && !c.sync);

  // Untrusted input: the host leaks heap into padding.
  n = unhex("037e5a020400e09763223a22322e3022", buf);
  c = eaf::ParseCommand(buf, n);
  check("junk padding ignored", c.kind == eaf::CommandKind::kReadRegister && c.reg == 0x04);

  const char* bad[] = {"", "03", "037e", "037e5a", "037e5a02"};
  bool all_rejected = true;
  for (const char* h : bad) {
    n = unhex(h, buf);
    if (eaf::ParseCommand(buf, n).kind != eaf::CommandKind::kMalformed) all_rejected = false;
  }
  check("truncated reports rejected", all_rejected);

  n = unhex("03dead02040000000000000000000000", buf);
  check("bad magic rejected", eaf::ParseCommand(buf, n).kind == eaf::CommandKind::kMalformed);

  n = unhex("017e5a02040000000000000000000000", buf);
  check("wrong report id rejected", eaf::ParseCommand(buf, n).kind == eaf::CommandKind::kMalformed);

  printf(failures ? "\n%d FAILED\n" : "\nall passed\n", failures);
  return failures ? 1 : 0;
}

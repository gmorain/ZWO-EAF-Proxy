# Backends

One file per real focuser. Each implements `Focuser` (firmware/main/include/focuser.h)
and nothing else. A backend never knows which persona is upstream.

To add one: subclass `SerialFocuser`, implement the six required methods, and
report `kUnsupported` for anything the hardware genuinely cannot answer.

Planned, in the order they are worth doing:

1. **myFocuserPro2** — your own board, protocol is open and documented, UART is
   tappable. Start here: it validates the whole chain with no unknowns on the
   backend side.
2. **Optec Gemini** — RS-232 native, needs a level shifter, ASCII protocol.
3. **Pinefeat CEF** — USB CDC only. Blocked on the USB conflict in
   docs/ARCHITECTURE.md.

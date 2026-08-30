# Optical trains

Nothing in the chain remembers these. The proxy reports what the hardware is, the
ASIAIR settings live in the app, and both change when the glass does. A zoom
needs a row per focal length, since travel and aperture range both move with it.

| Train | `a` | Travel | Infinity | Headroom | AF step | Reverse | Aperture |
|---|---|---|---|---|---|---|---|
| Canon EF 50mm f/1.8 II | `1.8-22.6` | **unusable** | — | — | — | — | — |
| Tokina 11-16 f/2.8 @ 11mm | `2.8-22.6` | 0-808 | — | — | ? | ? | f/4.0 |
| Canon EF-S 24mm f/2.8 STM | `2.8-22.6` | 0-1829 | ~1750-1780 | 50-80 | 2 | ? | f/4.0 |
| Canon EF 100mm f/2.8 Macro USM | `2.8-31.9` | 0-2530 | 2460 | 69 | 7 | ? | f/4.0 |
| Canon EF-S 18-200 3.5-5.6 IS @ 18mm | `3.5-22.6` | 0-3970 | — | — | ? | ? | f/4.4 |
| Canon EF-S 18-200 3.5-5.6 IS @ 200mm | ? | 0-3970 † | ~3800 | ~170 | 17 | ? | ? |
| Canon EF 75-300 4-5.6 IS @ 300mm | `5.6-45.2` | 0-2363 | ~2280 | ~80 | 8 | ? | f/6.3 |
| Canon EF 75-300 4-5.6 IS @ 75mm | `4.1-31.9` | 0-2363 | ~2280 | ~80 | 8 | ? | f/4.8 |

A lens marked unusable calibrates to a different travel every time, so it cannot
be positioned. Calibrate twice and compare before trusting a new one.

Infinity marked `~` is a broad plateau rather than a sharp peak. Slow lenses have
deeper focus, so the sharp point is harder to place and matters less.

The 75-300 holds focus across its whole zoom range, so both its rows share an
infinity step. Only the aperture differs. Do not assume that of another zoom.

† Travel was measured at 18mm and assumed unchanged at 200mm, on the evidence of
the 75-300 whose travel is the same across its range. `a` was never read at 200mm,
so that row's aperture default is unknown. Confirm both before trusting the row.

Two lenses share the signature `2.8-22.6`, the Tokina and the 24mm STM. Only
travel tells them apart, 808 against 1829. The Tokina is also constant aperture,
so `a` does not change when it is zoomed and nothing signals the change.

Wide lenses are hard to place. At 18mm and f/3.5 several hundred steps look
identical at infinity, so `~3800` is the middle of a plateau spanning roughly
3700 to 3860, not a peak. The width is the useful part: it is the focus tolerance
the autofocus step has to stay under.

**Reference**, read off the controller: `a`, travel, infinity, headroom.
**Set in the ASIAIR**: AF step, Reverse.
**Set by the proxy**: aperture. The default is computed; override it here once
you have tested the lens.

## Measuring a train

Attach the lens, set it to **AF**, and run the bench tool. Nothing below moves
the lens except where it says so.

```bash
cd host && uv run python tools/probe_pinefeat.py
```

- **`a` and travel** come straight out of that: the aperture range, and `0-N`
  after calibration. `0-65535` means the controller has no lens data, almost
  always the AF switch.
- **Infinity** needs your eyes. Point at something genuinely distant, then step
  down from the top of the travel and find where it is sharp:

  ```bash
  uv run python tools/probe_pinefeat.py --send "m1829,m1810,m1790,m1770,m1750"
  ```

  Cloud is a poor target, being low in contrast and soft edged. A rooftop, an
  aerial or a power line against sky is far easier to judge. Stars are best.
- **Headroom** is the end stop minus infinity. It is the room autofocus has on
  the infinity side, and it sets the AF step: the sweep has to fit inside it.
- **AF step** starts around headroom divided by ten, so a sweep places roughly
  ten samples above focus. Confirm it against a real autofocus run.
- **Reverse** is whichever way round feels right in the app. The proxy has no
  opinion and the ASIAIR handles it entirely.
- **Aperture** is the proxy's computed default until you have run the lens and
  found better. Fast glass usually wants more than the default, slow glass less.

## Why each column exists

Travel and aperture range identify the configuration and change when the lens or
the zoom does. Infinity and headroom decide whether autofocus has room to work,
which is the thing most likely to fail silently on a camera lens. AF step and
Reverse are ASIAIR settings that no part of the proxy can read or write. Aperture
is write-only on the controller and survives power cycles, so a value set once is
inherited forever with nothing able to report it.

Protocol detail is in [protocol/pinefeat.md](protocol/pinefeat.md).

# BMW NBT integrated features

Start `RUN_NBT.cmd`, then **Start BMW emulator**. The integrated profile is
selected by default when its image exists. `viewer.py --original` selects the
unmodified profile. Restart the launcher to see its updated feature checkbox.

## Verified in the running original HMI

- **Vehicle information > Sport displays** is enabled and opens the original
  BMW animated gauges. Power and torque come from `vehicle-state.json` on the
  original rendering thread. Full scales are 400 kW and 800 Nm; the native scale
  API takes an increment of one eighth of the full scale.
- **Main menu > Navigation** opens the integrated OSM map in the emulator's
  display. It uses a full-screen OEM-inspired layout with a narrow icon strip,
  direction marker, compass and metric scale. This is a host-rendered surface,
  not BMW's original navigation engine or a reproduction of BMW map assets.
- **Multimedia > External devices** contains genuine resource rows for Android
  Auto and CarPlay. The original native selection callback routes their IDs to
  the matching host transport. Bluetooth uses the existing Bluetooth row.

Navigation: OPTION sets destination latitude/longitude, up/down zooms, tilt
directions pan, select recenters, and Back returns to iDrive. OSM tiles and OSRM
driving routes require internet. The default position is a Bucharest simulation;
there is no live GPS connection. Vehicle simulator speed advances an active route.
Only visible tiles are fetched and cached, with visible OSM attribution.

`tools/RUN_CAR_SIM.cmd` publishes a one-minute vehicle demonstration. For manual
control use `vehicle_sim_cli.py --interactive --output vehicle-state.json` from
`work/graphics-port/hmi-runner`. Simulated engine data drives the native sport
gauges; this does not implement a full CAN/MOST vehicle network.

## Phone hardware and transport limits

CarPlay connection/startup work is postponed. The phone menu entries and transport
adapters remain experimental; they are not part of the verified working feature
set. Android Auto and wireless projection also remain unverified.

`projection_bridge.py` reuses the existing PlayPort session under
`G:/mibstd2-emulator/mib2emu` without changing it or exposing its credentials.
Real USB iPhone CarPlay status and decoded 800x480 frames were verified. Its
frame endpoint requires the existing PlayPort browser decoder to remain active.
The host display/input bridge does not itself add an audio decoder.

Android uses the installed ADB and Android Auto DHU, including the DHU screenshot
command and knob controls. No authorized Android phone was connected for an
end-to-end test. Wireless Android and wireless CarPlay were not verified.

Bluetooth wraps the real Windows pairing/A2DP/AVRCP backend. No available Windows
Bluetooth radio was found, so pairing and streaming could not be verified.
It does not implement HFP calls or PBAP contacts. A visible menu entry alone is
not evidence of a working physical phone connection.

## Build and safeguards

Building the integrated image requires 64-bit Python, Pillow for map rendering,
the existing original firmware image, and Zig 0.15.2 at the path used by
`work/bridge-v2/build.py`. Run `py -3.12 tools/build_native_profile.py` before
starting the launcher. Generated images, local phone state and logs are excluded
from Git. The optional static hook-contract check additionally requires Capstone
and the locally extracted HmiMain3D artifact.

`tools/build_native_profile.py` builds a separate
`work/bridge-v2/ifs/walthread_keyboard_dma_v2_native.ifs`. It verifies the exact
original HmiMain3D SHA-256
`554b67d4d6317cfb1715d544874fae8ddd2c975be503c9e2514e2dc2f3a0d693`,
preserves the shipped GLES bridge, patches the External devices resource and
preloads a standalone adapter. Original firmware files remain available.

The adapter checks instruction identities before patching private guest text
pages. Simulator values and selection events use a dedicated guest mailbox.
Host memory access validates the owned QEMU process creation time, guest RAM
bounds, mailbox magic/version and permitted write fields. Gauge updates stay on
the original UI thread. Static analysis used ELF parsing and Capstone; REA
registration and native decompiler engines were unavailable.

`tools/CHECK_HYPERVISOR.cmd` performs the read-only acceleration diagnostic.
This PC reported BIOS virtualization enabled and no active Windows hypervisor;
the actual QEMU WHPX probe failed, so it uses TCG. No Windows features were changed.

## Checks

```powershell
py -3 -m unittest discover -s work/graphics-port/hmi-runner/tests -q
py -3 tools/test_native_sports_contract.py -q
py -3 tools/test_repack_nbt_ifs.py -q
```

Runtime evidence and screenshots stay in ignored `outputs/native-integration/`
and the viewer run directories. Hardware phone/audio tests remain separate from
host unit checks and menu/gauge runtime checks.

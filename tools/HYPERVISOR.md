# Hypervisor diagnostic

Double-click `CHECK_HYPERVISOR.cmd`, or run:

```powershell
py -3 tools/check_hypervisor.py
py -3 tools/check_hypervisor.py --json --output hypervisor-report.json
```

This read-only check reports whether the Windows hypervisor is active, CPU/firmware
virtualization flags, the Windows Hypervisor Platform feature state, and each
running QEMU process's selected accelerator (`tcg` or `whpx`). It also launches a
separate paused QEMU with no guest image or disk for three seconds to check actual
WHPX initialization, then terminates and reaps only that probe. It does not stop
running emulator instances or change BIOS, Windows Features, or boot settings.

The feature-state query normally requires an administrator terminal. Other checks
still run without elevation; an inaccessible feature state is reported as unknown.
CPU virtualization flags can be masked when a hypervisor is active. A successful
probe proves QEMU accelerator initialization, not that the NBT guest can boot.

Use `--skip-probe` to avoid starting the test process, `--qemu PATH` to test another
QEMU binary, or `--probe-seconds N` for a 1–10 second observation interval. The JSON
report contains process command lines, so review it before sharing.

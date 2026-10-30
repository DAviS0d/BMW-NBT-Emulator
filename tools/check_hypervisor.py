"""Read-only Windows/WHPX diagnostics for BMW NBT Emulator (standard library)."""
import argparse
import json
import os
import platform
import re
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CREATE_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
HOST_SCRIPT = r'''
$ErrorActionPreference = 'Stop'
$report = [ordered]@{}
try {
    $computer = Get-CimInstance Win32_ComputerSystem
    $report.hypervisor_present = [bool]$computer.HypervisorPresent
} catch { $report.computer_error = $_.Exception.Message }
try {
    $report.processors = @(Get-CimInstance Win32_Processor | ForEach-Object {
        [ordered]@{
            name = $_.Name
            virtualization_firmware_enabled = $_.VirtualizationFirmwareEnabled
            vm_monitor_mode_extensions = $_.VMMonitorModeExtensions
            second_level_address_translation = $_.SecondLevelAddressTranslationExtensions
        }
    })
} catch { $report.processor_error = $_.Exception.Message }
try {
    $report.windows_hypervisor_platform = (Get-WindowsOptionalFeature -Online -FeatureName HypervisorPlatform).State.ToString()
} catch {
    $report.windows_hypervisor_platform = 'Unknown'
    $report.feature_query_error = $_.Exception.Message
}
try {
    $report.qemu_processes = @(Get-CimInstance Win32_Process | Where-Object {
        $_.Name -like 'qemu-system-*'
    } | ForEach-Object {
        [ordered]@{pid=$_.ProcessId; executable=$_.Name; command_line=$_.CommandLine}
    })
} catch { $report.process_query_error = $_.Exception.Message }
$report.os_64_bit = [Environment]::Is64BitOperatingSystem
$report | ConvertTo-Json -Depth 6 -Compress
'''


def windows_facts():
    system_dir = 'Sysnative' if struct.calcsize('P') == 4 and os.environ.get('PROCESSOR_ARCHITEW6432') else 'System32'
    powershell = Path(os.environ.get('SystemRoot', r'C:\Windows')) / system_dir / 'WindowsPowerShell/v1.0/powershell.exe'
    try:
        result = subprocess.run(
            [str(powershell), '-NoProfile', '-NonInteractive', '-Command', HOST_SCRIPT],
            capture_output=True, text=True, timeout=45, creationflags=CREATE_NO_WINDOW)
        if result.returncode:
            return {'query_error': result.stderr.strip() or f'PowerShell exit {result.returncode}'}
        facts = json.loads(result.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError) as error:
        return {'query_error': str(error)}
    for process in facts.get('qemu_processes', []):
        command = process.get('command_line') or ''
        match = re.search(r'(?:^|\s)-accel\s+["\']?([^\s,"\']+)', command)
        if not match:
            match = re.search(r'(?:^|,)accel=([^\s,"\']+)', command)
        process['accelerator'] = match.group(1) if match else 'Not specified / unreadable'
    return facts


def probe_whpx(qemu, seconds):
    """Launch a diskless, paused, device-free probe and always reap our process."""
    # WHPX requires an x86 machine. This bundled QEMU asserts on `-machine none`
    # before testing WHPX, which can leave a crash dialog and false timeout.
    command = [str(qemu), '-machine', 'pc', '-nodefaults', '-accel', 'whpx',
               '-display', 'none', '-S', '-monitor', 'none', '-serial', 'none']
    report = {'command': command, 'observation_seconds': seconds}
    if not qemu.is_file():
        return {**report, 'state': 'not_tested', 'error': 'QEMU executable not found'}
    try:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, creationflags=CREATE_NO_WINDOW)
    except OSError as error:
        return {**report, 'state': 'not_tested', 'error': str(error)}
    try:
        try:
            stdout, stderr = process.communicate(timeout=seconds)
            report.update(state='failed', exit_code=process.returncode)
        except subprocess.TimeoutExpired:
            # A running paused QEMU passed accelerator initialization. This does
            # not claim that a particular NBT guest has booted or rendered.
            process.terminate()
            try:
                stdout, stderr = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate(timeout=5)
            report.update(state='initialized', probe_process_cleaned_up=True)
        report['stdout'] = stdout.decode('utf-8', errors='replace').strip()
        report['stderr'] = stderr.decode('utf-8', errors='replace').strip()
        if any(marker in report['stderr'].lower() for marker in
               ('assertion', 'is not an instance of type', 'failed to initialize', 'no accelerator found')):
            report['state'] = 'failed'
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
    return report


def findings(report):
    facts, probe = report['windows'], report['whpx_probe']
    notes = []
    if facts.get('hypervisor_present') is False:
        notes.append('Windows reports no active hypervisor. The viewer currently falls back to TCG software CPU emulation.')
    elif facts.get('hypervisor_present') is True:
        notes.append('Windows reports an active hypervisor. The WHPX probe below determines whether this QEMU can use it.')
    if facts.get('windows_hypervisor_platform') == 'Disabled':
        notes.append('Windows Hypervisor Platform is disabled. Enable it in Windows Features, then restart Windows to use WHPX.')
    elif facts.get('windows_hypervisor_platform') == 'Unknown':
        notes.append('The Windows Hypervisor Platform feature state could not be read. Run this diagnostic as administrator to query it; no elevation is needed for the other checks.')
    cpus = facts.get('processors', [])
    if facts.get('hypervisor_present') is False and any(cpu.get('virtualization_firmware_enabled') is False for cpu in cpus):
        notes.append('CPU virtualization is reported disabled in firmware. Check Intel VT-x / AMD SVM in BIOS/UEFI. Windows may mask these CPU flags when a hypervisor is active.')
    if probe['state'] == 'initialized':
        notes.append('QEMU remained running with WHPX during the bounded paused probe. Accelerator initialization passed; a full NBT boot is a separate test.')
    elif probe['state'] == 'failed':
        notes.append('The QEMU WHPX probe exited during initialization. See its stderr for the actual failure. A DLL being present alone does not mean WHPX is usable.')
    if facts.get('hypervisor_present') is False and facts.get('windows_hypervisor_platform') != 'Disabled':
        notes.append('If virtualization and Windows Hypervisor Platform are enabled, check the Windows boot configuration hypervisorlaunchtype and restart. This script changes no settings.')
    return notes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', action='store_true', help='Print the complete JSON report')
    parser.add_argument('--output', type=Path, help='Also save the complete report at this path')
    parser.add_argument('--qemu', type=Path, default=ROOT / 'work/emulation-tools/qemu-portable/qemu-system-x86_64.exe')
    parser.add_argument('--probe-seconds', type=float, default=3, help='Paused QEMU observation interval (1..10 seconds)')
    parser.add_argument('--skip-probe', action='store_true', help='Read Windows/process state without launching a QEMU probe')
    args = parser.parse_args()
    if os.name != 'nt':
        parser.error('This diagnostic is for Windows')
    if not 1 <= args.probe_seconds <= 10:
        parser.error('--probe-seconds must be between 1 and 10')
    report = {'python_bits': struct.calcsize('P') * 8, 'python': sys.executable,
              'windows_version': platform.platform(), 'windows': windows_facts(),
              'whpx_probe': {'state': 'skipped'} if args.skip_probe else probe_whpx(args.qemu, args.probe_seconds)}
    report['findings'] = findings(report)
    serialized = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(serialized + '\n', encoding='utf-8')
    if args.json:
        print(serialized)
    else:
        facts = report['windows']
        print('BMW NBT hypervisor diagnostic (read-only)')
        print(f"Python: {report['python_bits']}-bit | OS: {report['windows_version']}")
        print('Active Windows hypervisor:', facts.get('hypervisor_present', 'Unknown'))
        print('Windows Hypervisor Platform:', facts.get('windows_hypervisor_platform', 'Unknown'))
        for cpu in facts.get('processors', []):
            print('CPU:', cpu.get('name'))
            print('  Firmware virtualization:', cpu.get('virtualization_firmware_enabled'),
                  '| VM extensions:', cpu.get('vm_monitor_mode_extensions'),
                  '| SLAT:', cpu.get('second_level_address_translation'))
        print('Running QEMU instances:')
        for process in facts.get('qemu_processes', []):
            print(f"  PID {process['pid']}: {process['accelerator']}")
        if not facts.get('qemu_processes'):
            print('  None detected')
        print('WHPX probe:', report['whpx_probe']['state'])
        detail = report['whpx_probe'].get('stderr') or report['whpx_probe'].get('error')
        if detail:
            print(detail)
        for note in report['findings']:
            print('- ' + note)
        if facts.get('query_error'):
            print('Windows query error:', facts['query_error'])
        print('Use --json for all evidence, including full QEMU command lines.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

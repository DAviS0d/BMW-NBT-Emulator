"""Run the host vehicle-data simulator and emit newline-delimited JSON.

Examples:
  py vehicle_sim_cli.py --state-json '{"ignition":true,"rpm":3500,"throttle_pct":60}'
  py vehicle_sim_cli.py --demo --seconds 60 --hz 10 --output vehicle-state.json
  py vehicle_sim_cli.py --interactive

This does not send CAN/MOST messages or change the original BMW HMI.
"""
import argparse
import json
import math
import os
from pathlib import Path
import queue
import sys
import tempfile
import threading
import time

from vehicle_sim import VehicleSimulator


def finite_number(low, high):
    def parse(value):
        try:
            number = float(value)
        except ValueError:
            raise argparse.ArgumentTypeError('must be a number') from None
        if not math.isfinite(number) or not low <= number <= high:
            raise argparse.ArgumentTypeError(f'must be a finite number in {low}..{high}')
        return number
    return parse


def atomic_json(path, payload):
    """Replace the latest state atomically, leaving no partially written JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='\n',
                                         prefix=path.name + '.', suffix='.tmp',
                                         dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def read_commands(commands):
    for line in sys.stdin:
        if line.strip():
            commands.put(line)
    commands.put(None)


def apply_command(simulator, raw):
    """Return False for quit; direct JSON objects are manual state patches."""
    if raw is None:
        return False
    message = json.loads(raw)
    if not isinstance(message, dict):
        raise ValueError('Command must be a JSON object')
    command = message.get('command')
    if command is None:
        simulator.update(message)
    elif command == 'demo':
        simulator.start_demo()
    elif command == 'stop':
        simulator.stop_demo()
    elif command == 'update':
        simulator.update(message.get('state'))
    elif command == 'quit':
        return False
    else:
        raise ValueError('command must be demo, stop, update, or quit')
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--state-json', metavar='OBJECT',
                        help='initial JSON state patch, or @path to a UTF-8 JSON patch file')
    parser.add_argument('--demo', action='store_true', help='run an automatic driving demo')
    parser.add_argument('--seconds', type=finite_number(0, 86400),
                        help='duration; default 30 for --demo, unlimited for --interactive, otherwise one sample')
    parser.add_argument('--hz', type=finite_number(.2, 50), default=10,
                        help='JSON sample rate, 0.2..50 Hz (default 10)')
    parser.add_argument('--output', type=Path, help='atomically replace this JSON file with each latest state')
    parser.add_argument('--interactive', action='store_true',
                        help='accept JSON state patches/commands on stdin; EOF exits')
    args = parser.parse_args(argv)
    duration = args.seconds
    if duration is None and not args.interactive:
        duration = 30 if args.demo else 0
    simulator = VehicleSimulator()
    try:
        if args.state_json is not None:
            try:
                raw = (Path(args.state_json[1:]).read_text(encoding='utf-8-sig')
                       if args.state_json.startswith('@') else args.state_json)
                simulator.update(json.loads(raw))
            except ValueError as error:
                parser.error(str(error))
        if args.demo:
            try:
                simulator.start_demo()
            except ValueError as error:
                parser.error(str(error))
        commands = queue.Queue()
        if args.interactive:
            print('Simulated host data only; no native CAN/MOST injection.\n'
                  'Enter JSON patches, or {"command":"demo|stop|quit"}; '
                  'manual updates exit demo mode. EOF exits.', file=sys.stderr)
            threading.Thread(target=read_commands, args=(commands,), daemon=True,
                             name='vehicle-cli-input').start()
        started = time.monotonic()
        next_sample = started
        deadline = started + duration if duration is not None else None
        active = True
        while active:
            while True:
                try:
                    command = commands.get_nowait()
                except queue.Empty:
                    break
                try:
                    active = apply_command(simulator, command)
                except (ValueError, RuntimeError) as error:
                    print('Invalid command: ' + str(error), file=sys.stderr)
                if not active:
                    break
            payload = json.dumps(simulator.snapshot(), separators=(',', ':'), allow_nan=False)
            if args.output:
                atomic_json(args.output, payload)
            print(payload, flush=True)
            now = time.monotonic()
            if not active or (deadline is not None and now >= deadline):
                break
            next_sample = max(next_sample + 1 / args.hz, now)
            wake = min(next_sample, deadline) if deadline is not None else next_sample
            time.sleep(max(0, wake - time.monotonic()))
        return 0
    except BrokenPipeError:
        return 0
    except KeyboardInterrupt:
        return 130
    except OSError as error:
        print('Vehicle simulator: ' + str(error), file=sys.stderr)
        return 1
    finally:
        simulator.close()


if __name__ == '__main__':
    raise SystemExit(main())

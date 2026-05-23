# EV3 Deployment Scripts

This directory contains scripts for deploying the robot controller to an EV3 brick.

## Quick Start

### Deploy Release Version (Recommended for Production)

```bash
./scripts/deploy_release.sh <EV3_IP>
```

### Deploy Debug Version (For Development)

```bash
./scripts/deploy_debug.sh <EV3_IP>
```

## Release vs Debug Mode

Both modes use `pybricks-micropython` as the interpreter, which is the correct
runtime for code written against the Pybricks API.  The EV3 must have
`pybricks-micropython` available on its `$PATH` (this is the case when the
brick runs ev3dev with the pybricks package installed, or a Pybricks firmware
image that provides the interpreter).

### Release Mode (`--mode release`)

- **Pybricks MicroPython optimization enabled** (`pybricks-micropython -O`)
- `__debug__` is `False`
- `assert` statements are removed
- Debug-only code blocks are skipped
- **Better performance** on resource-constrained EV3
- **Recommended for normal operation**

### Debug Mode (`--mode debug`)

- **No optimization** (`pybricks-micropython`)
- `__debug__` is `True`
- `assert` statements are active
- All debug code blocks execute
- Full error messages and stack traces
- **Useful for development and troubleshooting**

## Scripts

### `deploy_ev3.py`

The main deployment script with full options:

```bash
# Deploy release version
python3 scripts/deploy_ev3.py --host 192.168.1.100 --mode release

# Deploy debug version
python3 scripts/deploy_ev3.py --host 192.168.1.100 --mode debug

# Dry run (preview without deploying)
python3 scripts/deploy_ev3.py --host 192.168.1.100 --mode release --dry-run

# List files that would be deployed
python3 scripts/deploy_ev3.py --list-files

# Verbose output
python3 scripts/deploy_ev3.py --host 192.168.1.100 --mode release --verbose
```

### Options

| Option | Description | Default |
|--------|-------------|---------|
| `--host` | EV3 IP address or hostname | Required |
| `--mode` | `release` or `debug` | `release` |
| `--user` | SSH username | `robot` |
| `--path` | Remote path on EV3 | `/home/robot/ev3PS4Controlled` |
| `--port` | SSH port | `22` |
| `--dry-run` | Preview without deploying | - |
| `--verbose` | Detailed output | - |
| `--list-files` | List files and exit | - |
| `--no-verify` | Skip verification | - |

### `deploy_release.sh` / `deploy_debug.sh`

Convenience wrapper scripts:

```bash
# Release deployment
./scripts/deploy_release.sh 192.168.1.100

# Debug deployment
./scripts/deploy_debug.sh 192.168.1.100

# With additional options
./scripts/deploy_release.sh 192.168.1.100 --verbose --dry-run
```

## What Gets Deployed

The deployment scripts automatically exclude:

- Test files (`tests/`, `test_*.py`, `*_test.py`)
- Example files (`example_*.py`, `examples/`)
- Documentation (`*.md`, `README*`)
- Development files (`.vscode/`, `.pytest_cache/`, etc.)
- Python cache (`__pycache__/`, `*.pyc`)
- Virtual environments (`.venv/`, `venv/`)
- Git files (`.git/`, `.gitignore`)

## Running on EV3

After deployment, connect to the EV3 and run:

```bash
ssh robot@<EV3_IP>
cd /home/robot/ev3PS4Controlled
./run.sh
```

The `run.sh` script automatically uses the correct Python flags based on the deployment mode.

## Requirements

- Python 3.6+ on the **deployment machine** (to run `deploy_ev3.py`)
- `rsync` installed on the deployment machine
- SSH access to the EV3 brick
- EV3 running ev3dev with `pybricks-micropython` available on `$PATH`
  (provided by the `python3-pybricks` apt package or a Pybricks firmware image)

## Troubleshooting

### Connection Issues

1. Verify EV3 IP address: `ping <EV3_IP>`
2. Test SSH connection: `ssh robot@<EV3_IP>`
3. Check SSH key authentication is set up

### Deployment Verification Failed

The script verifies `main.py` and `run.sh` exist after deployment. If verification fails:

1. Check SSH permissions
2. Verify remote path exists
3. Use `--verbose` for detailed output

### `ImportError: No module named 'pybricks'` when running `./run.sh`

This means `run.sh` is calling the wrong Python interpreter.  The robot code
uses the Pybricks API which is **only** available via `pybricks-micropython`,
not the system `python3`.

Verify the interpreter is available on the EV3:

```bash
ssh robot@<EV3_IP> which pybricks-micropython
```

If the command is not found, install the Pybricks package on ev3dev:

```bash
ssh robot@<EV3_IP> sudo apt-get install -y python3-pybricks
```

Re-deploy after fixing the environment so that a fresh `run.sh` is generated:

```bash
./scripts/deploy_release.sh <EV3_IP>
```

### Debug Mode Not Working

Ensure you're using `./run.sh` to start the robot, not `python3 main.py`
directly.  The `run.sh` script uses the correct `pybricks-micropython`
interpreter with the right optimization flags.

## Code Changes for Debug/Release

The codebase uses `__debug__` to conditionally execute code:

```python
if __debug__:
    print("Debug: Motor speed =", speed)  # Only in debug mode
```

In release mode (`pybricks-micropython -O`), these blocks are completely removed by the interpreter.

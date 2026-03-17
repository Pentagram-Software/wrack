# Contributing to EV3 PS4 Controlled Robot

Thank you for your interest in contributing!

## Development Setup

1. Clone the repository
2. Install development dependencies:
   ```bash
   pip install -r requirements-test.txt
   ```

## Running Tests

```bash
# Run all tests
python3 tests/run_pytest.py

# Run with coverage
python3 tests/run_pytest.py --coverage

# Run specific test
python3 tests/run_pytest.py tests/test_device_manager.py
```

## Code Style

- Follow PEP 8 guidelines
- Use meaningful variable names
- Add docstrings to functions and classes
- Keep functions focused and small

## Pull Request Process

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to your branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

## Testing on EV3

Before submitting, test your changes on actual EV3 hardware:

```bash
# Deploy to EV3
scp -r ev3PS4Controlled/ robot@<EV3_IP>:/home/robot/

# Test on EV3
ssh robot@<EV3_IP>
cd /home/robot/ev3PS4Controlled
python3 main.py
```

## Reporting Issues

When reporting issues, please include:
- EV3 firmware version (ev3dev/Pybricks)
- Python version
- Steps to reproduce
- Expected vs actual behavior
- Relevant logs from EV3 console

## Questions?

Feel free to open an issue for questions or discussions!

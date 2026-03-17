# Contributing to EV3 iPhone Controller

First off, thank you for considering contributing to EV3 iPhone Controller! It's people like you that make this project better for everyone.

## Code of Conduct

This project and everyone participating in it is governed by respect and professionalism. By participating, you are expected to uphold this code.

## How Can I Contribute?

### Reporting Bugs

Before creating bug reports, please check the existing issues to avoid duplicates. When you create a bug report, include as many details as possible:

- **Use a clear and descriptive title**
- **Describe the exact steps to reproduce the problem**
- **Provide specific examples** (code snippets, screenshots, etc.)
- **Describe the behavior you observed and what you expected**
- **Include details about your environment** (iOS version, device model, Xcode version)

### Suggesting Enhancements

Enhancement suggestions are tracked as GitHub issues. When creating an enhancement suggestion:

- **Use a clear and descriptive title**
- **Provide a step-by-step description of the suggested enhancement**
- **Explain why this enhancement would be useful**
- **Include mockups or examples if applicable**

### Pull Requests

1. Fork the repository and create your branch from `main`
2. If you've added code that should be tested, add tests
3. Ensure your code follows the existing style conventions
4. Make sure your code compiles without warnings
5. Write clear, concise commit messages
6. Update documentation as needed

## Style Guidelines

### Swift Style Guide

- Follow Apple's [Swift API Design Guidelines](https://swift.org/documentation/api-design-guidelines/)
- Use descriptive variable and function names
- Prefer `let` over `var` when possible
- Use modern Swift concurrency (async/await) over older patterns
- Keep functions focused and single-purpose
- Add comments for complex logic

### Code Formatting

- Use 4 spaces for indentation (not tabs)
- Maximum line length: 120 characters
- Add whitespace for readability
- Use Swift's built-in formatting conventions

### SwiftUI Best Practices

- Break down large views into smaller, reusable components
- Use `@StateObject` for object creation, `@ObservedObject` for passed objects
- Prefer composition over inheritance
- Keep state minimal and localized

### Commit Messages

- Use present tense ("Add feature" not "Added feature")
- Use imperative mood ("Move cursor to..." not "Moves cursor to...")
- Limit first line to 72 characters
- Reference issues and pull requests when applicable

Example:
```
Add turret speed control slider

- Implement dynamic speed adjustment
- Update UI with speed indicator
- Add unit tests for speed validation

Fixes #123
```

## Development Setup

1. Clone the repository
2. Open `ev3iPhoneController.xcodeproj` in Xcode
3. Update `Config.swift` with your development credentials
4. Build and run on simulator or device

## Testing

- Write unit tests for new functionality
- Ensure all tests pass before submitting PR
- Test on both iPhone and iPad if possible
- Test in both portrait and landscape orientations

## Project Structure

```
ev3iPhoneController/
├── Views/
│   ├── ContentView.swift
│   └── VideoStreamView.swift
├── Controllers/
│   └── RobotController.swift
├── Models/
│   └── Config.swift
├── Tests/
└── Resources/
```

## Questions?

Feel free to open an issue with the tag `question` if you have any questions about contributing.

Thank you for contributing! 🎉

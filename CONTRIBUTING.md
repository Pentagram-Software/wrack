# Contributing to WRACK Control Center

Thank you for your interest in contributing to the WRACK Control Center! This document provides guidelines and information for contributors.

## Code of Conduct

This project follows a code of conduct that all contributors are expected to adhere to:
- Be respectful and inclusive
- Welcome newcomers and encourage diverse perspectives
- Focus on constructive feedback
- Respect differing opinions and experiences

## How to Contribute

### Reporting Bugs

If you find a bug, please create an issue with:
- **Clear title**: Descriptive summary of the issue
- **Description**: Detailed explanation of the problem
- **Steps to reproduce**: Exact steps to trigger the bug
- **Expected behavior**: What you expected to happen
- **Actual behavior**: What actually happened
- **Environment**: OS, browser, Node.js version, etc.
- **Screenshots**: If applicable

### Suggesting Features

Feature suggestions are welcome! Please:
- Check existing issues to avoid duplicates
- Clearly describe the feature and its benefits
- Explain the use case and why it's valuable
- Consider implementation complexity

### Pull Requests

1. **Fork the repository**
   ```bash
   git clone https://github.com/rkuklins/mindstorms-cloud-controller.git
   cd mindstorms-cloud-controller
   ```

2. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **Make your changes**
   - Follow the code style guidelines
   - Add tests if applicable
   - Update documentation as needed

4. **Commit your changes**
   ```bash
   git add .
   git commit -m "feat: add new feature"
   ```

   Use conventional commit messages:
   - `feat:` New feature
   - `fix:` Bug fix
   - `docs:` Documentation changes
   - `style:` Code style changes (formatting)
   - `refactor:` Code refactoring
   - `test:` Adding or updating tests
   - `chore:` Maintenance tasks

5. **Push to your fork**
   ```bash
   git push origin feature/your-feature-name
   ```

6. **Create a Pull Request**
   - Provide a clear description of changes
   - Reference any related issues
   - Ensure CI checks pass

## Development Setup

1. **Install dependencies**
   ```bash
   npm install
   ```

2. **Configure environment**
   ```bash
   cp .env.local.example .env.local
   # Edit .env.local with your settings
   ```

3. **Start development server**
   ```bash
   npm run dev
   ```

## Code Style Guidelines

### TypeScript
- Use TypeScript for all new code
- Define interfaces for all data structures
- Avoid `any` type - use specific types or `unknown`
- Use meaningful variable and function names

### React Components
- Use functional components with hooks
- Keep components focused and single-purpose
- Extract reusable logic into custom hooks
- Use proper TypeScript types for props

### File Structure
```typescript
// Component structure
import statements
type/interface definitions
helper functions
main component
export statement
```

### Naming Conventions
- **Components**: PascalCase (`EV3StatusPanel.tsx`)
- **Files**: kebab-case for utilities (`robot-api.ts`)
- **Variables**: camelCase (`motorSpeed`)
- **Constants**: UPPER_SNAKE_CASE (`MAX_SPEED`)
- **Interfaces/Types**: PascalCase (`EV3Status`)

### Code Formatting
- Run ESLint before committing: `npm run lint`
- Use 2 spaces for indentation
- Use single quotes for strings
- Add semicolons at end of statements
- Use trailing commas in multi-line objects/arrays

## Testing

Currently, the project doesn't have automated tests. Contributions to add tests are welcome!

When tests are added:
```bash
npm run test          # Run tests
npm run test:watch    # Watch mode
npm run test:coverage # Coverage report
```

## Documentation

When adding features or making changes:
- Update README.md if user-facing
- Update DESIGN.md for architectural changes
- Add JSDoc comments for complex functions
- Update type definitions

## Project Structure

```
src/
├── app/              # Next.js pages and layouts
├── components/       # React components
├── lib/              # Utilities and API clients
├── types/            # TypeScript type definitions
└── hooks/            # Custom React hooks
```

## Getting Help

If you need help:
- Check existing documentation (README.md, DESIGN.md)
- Search existing issues
- Create a new issue with the "question" label
- Join discussions in pull requests

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

## Recognition

Contributors will be recognized in the project README. Thank you for making WRACK Control Center better!

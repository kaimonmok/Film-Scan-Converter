# Contribution Guidelines

If you're reading this, thanks for helping me take this project further beyond what I can accomplish on my own. The analog community has long been deprived of a free, intuitive, and standalone film inversion application, and your contribution will help film photography be more accessible to many more people.

## The Vision

The Film Scan Converter's primary objective is user-friendliness, in consideration of aspiring film photographers who want to spend more time shooting film than worrying about how to invert it. The core experience of using this application involves producing consistent, pleasing, workable, and exportable scans moments after importing, with little need to fiddle around with controls beforehand. This means that your contribution should not compromise on this vision, but should instead promote the ease-of-use and instant delivery of high-quality film inversions.

You are welcome to develop more technical, niche features. However, if the feature or control is not pertinent to a novice user, efforts should be made to minimize the clutter in the main GUI, and the widgets and controls for this new feature should be moved to a separate tab/window.

## How you can contribute

If you're looking for somewhere to start, here are a few places where you can help:

- Make the application easily distributable across all platforms
- Modernize the GUI
- Improve the dust detection
- Improve the image conversion pipeline
- Optimize code readability/performance

## Suggesting New Features

- Check that somebody else has not already suggested the same feature in [Issues](https://github.com/kaimonmok/Film-Scan-Converter/issues).
- Suggest new features to add by [opening an issue](https://github.com/kaimonmok/Film-Scan-Converter/issues/new), and include a title and description that clearly articulates what you think this new feature should do, and how it may be implemented.

## Reporting Bugs

- Check that the bug has not already been reported in [Issues](https://github.com/kaimonmok/Film-Scan-Converter/issues).
- If the bug has not yet been reported, [open a new issue](https://github.com/kaimonmok/Film-Scan-Converter/issues/new), and include a title and a description that explains the issue, the expected functionality, and the steps to reproduce.
- If the bug pertains to a specific image or file, please attach a sample file to help diagnose the issue.

## Pull Requests

- Include a brief description of what changes were made, and how you tested it, if applicable.
- Include sample images especially if the change impacts the image processing pipeline.
- If the PR is fixing a bug, include the relevant issue number.

## Coding Conventions

In general, follow the coding conventions already in the code. A few conventions to highlight are:

- Use single tabs for indentation.
- Use spaces after lists and method parameters (e.g. `[1, 2, 3]`, not `[1,2,3]`), and around operators (e.g. `x += 1`, not `x+=1`).
- Methods should have a comment directly below explaining what it does, the arguments it takes, and its expected output.
- Use single quotes (`'Hello World'`) instead of double quotes (`"Hello World"`) for strings.
- Try to optimize for readability.

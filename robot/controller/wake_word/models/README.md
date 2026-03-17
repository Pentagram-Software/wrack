# Wake Word Models

This directory contains Mycroft Precise wake word models.

## Hey Wrack Model

The `hey_wrack.pb` model file should be placed in this directory for the wake word detector to function.

## Training a Custom Model

To train the "Hey Wrack" wake word model, follow these steps:

### 1. Install Mycroft Precise

```bash
pip install precise-runner precise-engine
# For training tools:
pip install mycroft-precise
```

### 2. Create Training Data

Record at least 50-100 samples of yourself saying "Hey Wrack" in various conditions:
- Different distances from microphone
- Different background noise levels
- Different speaking speeds and tones

Use the precise-collect tool:
```bash
precise-collect wake-words/hey-wrack/
```

### 3. Collect Background Noise Samples

Record or collect samples of background noise and speech that should NOT trigger the wake word.

### 4. Train the Model

```bash
precise-train hey_wrack.net wake-words/hey-wrack/
```

### 5. Convert to Protobuf Format

```bash
precise-convert hey_wrack.net
```

This creates `hey_wrack.pb` which should be placed in this directory.

## Pre-trained Models

Alternatively, you can use the Mycroft Precise web tool at:
https://mycroft.ai/wake-word/

## Model Configuration

The WakeWordDetector supports the following parameters:
- `sensitivity` (0.0-1.0): Higher values increase detection rate but may cause false positives
- `trigger_level` (1-5): Number of consecutive activations required before triggering

Recommended starting values:
- sensitivity: 0.5
- trigger_level: 3

## ADDED Requirements

### Requirement: Known-Cat Identity Prediction
For each cat crop produced by detection, the system SHALL produce a top predicted identity among the known cats: Ryfka, Chaja, or Lea.

#### Scenario: Detected cat matches a known identity most closely
- **WHEN** a cat crop is evaluated against all enrolled cat prototypes
- **THEN** the system produces a top predicted identity (Ryfka, Chaja, or Lea) based on closest match, along with an identification confidence score

### Requirement: Identity Confidence Threshold and Unknown Fallback
The system SHALL compare identification confidence against a configurable threshold to determine the final identity. When confidence is below the threshold, the final identity SHALL be `unknown`, while the top predicted identity SHALL still be preserved for later analysis.

#### Scenario: Confident match to a known cat
- **WHEN** identification confidence for the top predicted identity is at or above the configured threshold
- **THEN** the final identity equals the top predicted identity

#### Scenario: Low-confidence match falls back to unknown
- **WHEN** identification confidence for the top predicted identity is below the configured threshold
- **THEN** the final identity is `unknown`, and the top predicted identity is still recorded

### Requirement: Enrollment from Reference Photos
The system SHALL support enrolling each known cat's identity from a small set of reference photos, by deriving a per-cat reference representation (e.g. an averaged embedding) that can be compared against new detections — without requiring a full model retrain to add or update an identity.

#### Scenario: Enrolling a known cat from reference photos
- **WHEN** a set of reference photos for a known cat is provided
- **THEN** the system derives a reference representation for that cat usable by identification, without retraining any shared model component

#### Scenario: Adding a new known identity
- **WHEN** reference photos for a new cat identity are enrolled
- **THEN** the new identity becomes available for identification without requiring re-enrollment of existing known cats

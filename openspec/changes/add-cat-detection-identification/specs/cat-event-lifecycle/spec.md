## ADDED Requirements

### Requirement: Multi-Frame Event Confirmation
The system SHALL create a cat event only after cat detection is present in 3 consecutive sampled frames. Isolated or unconfirmed single-frame detections SHALL NOT create an event.

#### Scenario: Isolated single-frame detection does not create an event
- **WHEN** a cat is detected in exactly one sampled frame, with no cat detected in the immediately following sampled frame
- **THEN** no event is created

#### Scenario: Three consecutive frames confirm an event
- **WHEN** a cat is detected in 3 consecutive sampled frames
- **THEN** a new event is confirmed and becomes active

### Requirement: Active Event Persistence While Presence Continues
Once confirmed, an event SHALL remain active as long as cat presence continues to be detected.

#### Scenario: Continued presence keeps the event active
- **WHEN** an event is active and cat detections continue in subsequent sampled frames
- **THEN** the event remains active and is not ended

### Requirement: Configurable Absence Cooldown Ends Events
The system SHALL end an active event, and be eligible to start a new one, only after cat presence has been absent for a configurable cooldown duration. The cooldown value SHALL be configurable via deployment settings.

#### Scenario: Brief absence does not end the event
- **WHEN** cat presence is absent for less than the configured cooldown duration, then presence resumes
- **THEN** the original event remains active and is not split into two events

#### Scenario: Absence exceeding cooldown ends the event
- **WHEN** cat presence is absent for at least the configured cooldown duration
- **THEN** the active event ends, and a subsequent confirmed detection starts a new, separate event

"""Enumerated values shared by MAU-SOAP database models."""

from enum import Enum


class StringEnum(str, Enum):
    """Enum whose members serialize naturally as lowercase strings."""


class Role(StringEnum):
    ADMIN = "admin"


class MonitorType(StringEnum):
    FACE = "face"
    EYE_GAZE = "eye_gaze"


class ReleaseOption(StringEnum):
    IMMEDIATE = "immediate"
    SCHEDULED = "scheduled"


class QuestionType(StringEnum):
    MCQ = "mcq"
    OPEN_ENDED = "open_ended"
    SHORT_ANSWER = "short_answer"


class ViolationType(StringEnum):
    COPY_PASTE = "copy_paste"
    SCREENSHOT_ATTEMPT = "screenshot_attempt"
    FOCUS_LOSS = "focus_loss"
    FACE_NOT_DETECTED = "face_not_detected"
    GAZE_DEVIATION = "gaze_deviation"


class GradedBy(StringEnum):
    AUTOMATIC = "automatic"
    ADMIN = "admin"


class ResultStatus(StringEnum):
    PENDING_MANUAL_REVIEW = "pending_manual_review"
    COMPLETE = "complete"
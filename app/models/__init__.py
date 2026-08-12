"""Public model registry used by the application and Flask-Migrate."""

from .answer_grade import AnswerGrade
from .enums import (
    GradedBy,
    MonitorType,
    QuestionType,
    ReleaseOption,
    ResultStatus,
    Role,
    ViolationType,
)
from .exam import Exam
from .password_reset_token import PasswordResetToken
from .question import Question
from .result import Result
from .submission import Submission
from .user import User
from .verification_token import VerificationToken
from .warning_log import WarningLog

MODEL_REGISTRY = (
    User,
    Exam,
    Question,
    Submission,
    Result,
    WarningLog,
    VerificationToken,
    PasswordResetToken,
    AnswerGrade,
)

__all__ = [
    "MODEL_REGISTRY",
    "AnswerGrade",
    "Exam",
    "GradedBy",
    "MonitorType",
    "PasswordResetToken",
    "Question",
    "QuestionType",
    "ReleaseOption",
    "Result",
    "ResultStatus",
    "Role",
    "Submission",
    "User",
    "VerificationToken",
    "ViolationType",
    "WarningLog",
]
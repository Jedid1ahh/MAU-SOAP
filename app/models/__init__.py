"""Public model registry used by the application and Flask-Migrate."""

from .academic import AcademicSession, Department, Faculty, Programme, Semester
from .account_verification_token import AccountVerificationToken
from .answer_grade import AnswerGrade
from .course import Course
from .course_enrollment import CourseEnrollment
from .coursework import (
    Assignment,
    AssignmentSubmission,
    CourseAnnouncement,
    CourseMaterial,
)
from .enums import (
    DifficultyLevel,
    EnrollmentStatus,
    GradedBy,
    MonitorType,
    QuestionType,
    ReleaseOption,
    ResultStatus,
    Role,
    ViolationType,
)
from .exam import Exam
from .exam_accommodation import ExamAccommodation
from .password_reset_token import PasswordResetToken
from .question import Question
from .question_bank_item import QuestionBankItem
from .result import Result
from .submission import Submission
from .user import User
from .verification_token import VerificationToken
from .warning_log import WarningLog

MODEL_REGISTRY = (
    User,
    AcademicSession,
    Semester,
    Faculty,
    Department,
    Programme,
    Course,
    CourseEnrollment,
    AccountVerificationToken,
    Exam,
    ExamAccommodation,
    QuestionBankItem,
    Question,
    Submission,
    Result,
    WarningLog,
    VerificationToken,
    PasswordResetToken,
    AnswerGrade,
    CourseAnnouncement,
    CourseMaterial,
    Assignment,
    AssignmentSubmission,
)

__all__ = [
    "MODEL_REGISTRY",
    "AcademicSession",
    "AccountVerificationToken",
    "Assignment",
    "AssignmentSubmission",
    "AnswerGrade",
    "Course",
    "CourseAnnouncement",
    "CourseEnrollment",
    "CourseMaterial",
    "Department",
    "DifficultyLevel",
    "Exam",
    "ExamAccommodation",
    "EnrollmentStatus",
    "Faculty",
    "GradedBy",
    "MonitorType",
    "PasswordResetToken",
    "Question",
    "QuestionBankItem",
    "QuestionType",
    "ReleaseOption",
    "Result",
    "ResultStatus",
    "Role",
    "Programme",
    "Semester",
    "Submission",
    "User",
    "VerificationToken",
    "ViolationType",
    "WarningLog",
]

"""ORM model registry — imports every model so SQLAlchemy sees them."""
from app.models.tenant import Tenant, TenantInvite  # noqa: F401
from app.models.user import User, RefreshToken, Setting, AuditLog, Notification, SearchIndex, SearchHistory  # noqa: F401
from app.models.gamification import Achievement, UserAchievement, UserStreak  # noqa: F401
from app.models.finance import (  # noqa: F401
    Invoice, InvoiceLine, Expense, ExpenseCategory, PayrollRun, PayslipLine,
    BudgetPlan, BudgetItem, TaxRate, RecurringPayment, VendorPayment,
    JournalEntry, JournalLine, CurrencyRate, Customer, Vendor,
)
from app.models.finance_consolidation import (  # noqa: F401
    SubsidiaryEntity, IntercompanyTransaction, FxAdjustment,
)
from app.models.hr import (  # noqa: F401
    Employee, AttendanceRecord, LeaveRequest, PerformanceReview,
    Candidate, JobOpening, OnboardingTask, OrgUnit, TrainingRecord, DisciplinaryRecord,
)
from app.models.crm import (  # noqa: F401
    Lead, Deal, Contact, FollowUp, CommunicationEntry, Contract,
    Proposal, Quotation, EmailCampaign, CustomerSegment,
)
from app.models.projects import (  # noqa: F401
    Project, Task, Sprint, Milestone, TimeEntry, Meeting, MeetingMinute,
    Resource, ResourceAllocation, TaskDependency,
)
from app.models.inventory import (  # noqa: F401
    Product, StockMovement, Warehouse, WarehouseZone, ProductCategory,
    PurchaseOrder, PurchaseOrderLine, Supplier, Shipment, ShipmentEvent,
    ReturnRequest, StockAlert,
)
from app.models.documents import (  # noqa: F401
    Document, DocumentVersion, DocumentTag, DocumentShare, ESignature, DocumentTemplate,
)
from app.models.communication import (  # noqa: F401
    Message, MessageThread, Announcement, CalendarEvent, SharedNote, Poll, PollOption, PollVote,
    Feedback, WikiPage,
)
from app.models.security import (  # noqa: F401
    PasswordVaultEntry, BackupSchedule, LoginAttempt, ComplianceCheck,
)
from app.models.coding import (  # noqa: F401
    CodeProject, CodeSnippet, ApiRequest, GitRepo, RegexLibraryEntry, DatabaseConnection,
)
from app.models.ai import (  # noqa: F401
    AiConversation, AiMessage, AiUsageRecord, Chatbot, ChatbotMessage,
)
from app.models.knowledge import (  # noqa: F401
    KnowledgeBase, KnowledgeChunk, KnowledgeDocument, KnowledgeQuery,
)
from app.models.webchat import (  # noqa: F401
    Bot, ChatMessage, Conversation,
)
from app.models.marketing import (  # noqa: F401
    MarketingSettings, MarketingNavItem, MarketingSection, MarketingProject,
    MarketingPost, MarketingService, MarketingTestimonial, MarketingFAQ,
    MarketingTeamMember, MarketingSocialLink, MarketingUpload,
)
from app.models.academic import (  # noqa: F401
    AcademicAdvisingSession, AcademicAssignment, AcademicAssignmentSubmission,
    AcademicAttendanceRecord, AcademicClass, AcademicClassEnrollment,
    AcademicExam, AcademicGroupProject, AcademicGroupProjectAssignment,
    AcademicLabReport, AcademicLmsResource, AcademicRoom, AcademicScholarship,
    AcademicSemester, AcademicStudentFinanceRecord, AcademicStudyGroupMatch,
    AcademicStudyNote, AcademicStudyProfile, AcademicTimetableSlot,
)
from app.models.billing import (  # noqa: F401
    TenantSubscription, BillingEvent, UsageMeter,
)
from app.models.webhooks import (  # noqa: F401
    WebhookSubscription, WebhookDelivery, GdprExportJob, GdprErasureReceipt,
)
from app.models.rbac import (  # noqa: F401
    Permission, CustomRole, UserRoleAssignment,
)
from app.models.security_hardening import (  # noqa: F401
    TenantEncryptionKey, TenantSecurityPolicy, AuditStreamDestination,
)
from app.models.integrations import (  # noqa: F401
    TenantIntegration,
)
from app.models.workflows import (  # noqa: F401
    Workflow, WorkflowRun,
)
from app.models.construction import (  # noqa: F401
    ConstructionContract, ConstructionEOTRequest, ConstructionInsurance,
    ConstructionMilestone, ConstructionPermit, ConstructionProgressReport,
    ConstructionProject, ConstructionRaciEntry, ConstructionRisk,
    ConstructionScheduleDependency, ConstructionScheduleTask,
    ConstructionSiteInstruction, ConstructionToolboxTalk, ConstructionVariation,
)
from app.models.import_jobs import (  # noqa: F401
    ImportJob, ImportError,
)
from app.models.jobs import (  # noqa: F401
    Job, JobAttempt,
)
from app.models.webauthn import (  # noqa: F401
    WebAuthnCredential, WebAuthnChallenge,
)
from app.models.realtime import (  # noqa: F401
    YjsDocument,
)
# Side-effect import: registers the FTS5 ``search_index_fts`` DDL hook on
# Base.metadata so ``create_all`` (tests + fresh installs) produces the
# virtual table alongside the regular ones.
from app.models import search_index as _search_index_fts  # noqa: F401

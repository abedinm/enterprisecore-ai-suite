"""ORM model registry — imports every model so SQLAlchemy sees them."""
from app.models.user import User, RefreshToken, Setting, AuditLog, Notification, SearchIndex, SearchHistory  # noqa: F401
from app.models.finance import (  # noqa: F401
    Invoice, InvoiceLine, Expense, ExpenseCategory, PayrollRun, PayslipLine,
    BudgetPlan, BudgetItem, TaxRate, RecurringPayment, VendorPayment,
    JournalEntry, JournalLine, CurrencyRate, Customer, Vendor,
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
)
from app.models.inventory import (  # noqa: F401
    Product, StockMovement, Warehouse, PurchaseOrder, PurchaseOrderLine,
    Supplier, Shipment, ReturnRequest,
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
    CodeProject, CodeSnippet, ApiRequest, GitRepo,
)
from app.models.ai import (  # noqa: F401
    AiConversation, AiMessage, AiUsageRecord, Chatbot, ChatbotMessage,
)

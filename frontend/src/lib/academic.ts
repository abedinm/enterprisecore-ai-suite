import { api } from './api';

/* -------------------------------------------------------------------------- */
/*  Shared types                                                              */
/* -------------------------------------------------------------------------- */

export type AttendanceStatus = 'present' | 'absent' | 'late' | 'excused';

export type DayOfWeek = 0 | 1 | 2 | 3 | 4 | 5 | 6; // 0 = Monday, 6 = Sunday

/* -------------------------------------------------------------------------- */
/*  Classes & Attendance                                                      */
/* -------------------------------------------------------------------------- */

export type AcademicClass = {
  id: string;
  name: string;
  course_code: string;
  teacher_id: string | null;
  teacher_name: string | null;
  enrollment_count: number;
  credit_hours: number;
  semester_id: string | null;
  description?: string | null;
};

export type EnrolledStudent = {
  student_id: string;
  name: string;
  email?: string | null;
  enrolled_at?: string | null;
};

export type ClassDetail = AcademicClass & {
  students: EnrolledStudent[];
};

export type AttendanceRecord = {
  student_id: string;
  status: AttendanceStatus;
};

export type AttendanceSessionPayload = {
  session_date: string; // YYYY-MM-DD
  records: AttendanceRecord[];
};

export type AttendanceSessionRecord = AttendanceRecord & {
  id?: string;
  name?: string | null;
  session_date?: string;
};

export type AttendanceReportRow = {
  student_id: string;
  name: string;
  present: number;
  absent: number;
  late: number;
  excused: number;
  total: number;
  percentage: number;
};

export type StudentAttendanceSummary = {
  class_id: string;
  class_name: string;
  course_code: string;
  present: number;
  absent: number;
  late: number;
  excused: number;
  total: number;
  percentage: number;
};

/* -------------------------------------------------------------------------- */
/*  Timetable: semesters, rooms, slots                                         */
/* -------------------------------------------------------------------------- */

export type Semester = {
  id: string;
  name: string;
  start_date: string;
  end_date: string;
  is_active?: boolean;
};

export type SemesterInput = Omit<Semester, 'id'>;

export type Room = {
  id: string;
  name: string;
  building?: string | null;
  capacity?: number | null;
};

export type RoomInput = Omit<Room, 'id'>;

export type TimetableSlot = {
  id: string;
  class_id: string;
  class_name?: string | null;
  course_code?: string | null;
  room_id: string;
  room_name?: string | null;
  day_of_week: DayOfWeek;
  start_time: string; // HH:MM
  end_time: string;   // HH:MM
  semester_id: string;
};

export type TimetableSlotInput = {
  class_id: string;
  room_id: string;
  day_of_week: DayOfWeek;
  start_time: string;
  end_time: string;
  semester_id: string;
};

/* -------------------------------------------------------------------------- */
/*  LMS                                                                       */
/* -------------------------------------------------------------------------- */

export type LmsResource = {
  id: string;
  class_id?: string | null;
  title: string;
  description?: string | null;
  url?: string | null;
  kind: string; // 'video' | 'pdf' | 'slides' | 'link' | etc
  created_at?: string;
};
export type LmsResourceInput = Omit<LmsResource, 'id' | 'created_at'>;

/* -------------------------------------------------------------------------- */
/*  Lab Reports                                                               */
/* -------------------------------------------------------------------------- */

export type LabReport = {
  id: string;
  class_id?: string | null;
  title: string;
  body?: string | null;
  student_id?: string | null;
  student_name?: string | null;
  submitted_at?: string | null;
  grade?: string | number | null;
  status?: string;
};
export type LabReportInput = Omit<LabReport, 'id' | 'submitted_at' | 'student_name'>;

/* -------------------------------------------------------------------------- */
/*  Exams                                                                     */
/* -------------------------------------------------------------------------- */

export type Exam = {
  id: string;
  class_id?: string | null;
  class_name?: string | null;
  title: string;
  exam_date: string;
  duration_minutes?: number | null;
  weight?: number | null;
  notes?: string | null;
};
export type ExamInput = Omit<Exam, 'id' | 'class_name'>;

/* -------------------------------------------------------------------------- */
/*  Advising                                                                  */
/* -------------------------------------------------------------------------- */

export type AdvisingSession = {
  id: string;
  advisor_id?: string | null;
  advisor_name?: string | null;
  student_id?: string | null;
  student_name?: string | null;
  scheduled_at: string;
  duration_minutes?: number | null;
  notes?: string | null;
  status?: string;
};
export type AdvisingSessionInput = Omit<
  AdvisingSession,
  'id' | 'advisor_name' | 'student_name'
>;

/* -------------------------------------------------------------------------- */
/*  Group Projects                                                            */
/* -------------------------------------------------------------------------- */

export type GroupProject = {
  id: string;
  class_id?: string | null;
  title: string;
  description?: string | null;
  due_date?: string | null;
  member_count?: number;
};
export type GroupProjectInput = Omit<GroupProject, 'id' | 'member_count'>;

export type GroupAssignment = {
  id: string;
  project_id: string;
  student_id: string;
  student_name?: string | null;
  role?: string | null;
};
export type GroupAssignmentInput = Omit<GroupAssignment, 'id' | 'student_name'>;

/* -------------------------------------------------------------------------- */
/*  Study Aids                                                                */
/* -------------------------------------------------------------------------- */

export type StudyNote = {
  id: string;
  title: string;
  body: string;
  subject?: string | null;
  created_at?: string;
};
export type StudyNoteInput = Omit<StudyNote, 'id' | 'created_at'>;

export type Flashcard = { front: string; back: string };
export type MCQ = {
  question: string;
  options: string[];
  answer: number; // index
};

export type GeneratedAids = {
  flashcards: Flashcard[];
  mcqs: MCQ[];
};

/* -------------------------------------------------------------------------- */
/*  Study Match (study buddies)                                                */
/* -------------------------------------------------------------------------- */

export type StudyProfile = {
  id: string;
  user_id?: string;
  bio?: string | null;
  subjects: string[];
  availability?: string | null;
  preferred_style?: string | null;
};
export type StudyProfileInput = Omit<StudyProfile, 'id' | 'user_id'>;

export type StudyMatch = {
  user_id: string;
  name: string;
  shared_subjects: string[];
  score: number;
  bio?: string | null;
};

/* -------------------------------------------------------------------------- */
/*  Finance (student finance — fees & scholarships)                            */
/* -------------------------------------------------------------------------- */

export type FinanceRecord = {
  id: string;
  student_id?: string | null;
  student_name?: string | null;
  kind: string;        // 'fee' | 'payment' | 'aid'
  amount: number;
  currency?: string | null;
  due_date?: string | null;
  status?: string;
  notes?: string | null;
};
export type FinanceRecordInput = Omit<FinanceRecord, 'id' | 'student_name'>;

export type Scholarship = {
  id: string;
  name: string;
  description?: string | null;
  amount: number;
  currency?: string | null;
  deadline?: string | null;
};
export type ScholarshipInput = Omit<Scholarship, 'id'>;

/* -------------------------------------------------------------------------- */
/*  Deadlines                                                                 */
/* -------------------------------------------------------------------------- */

export type Assignment = {
  id: string;
  class_id?: string | null;
  class_name?: string | null;
  title: string;
  description?: string | null;
  due_date: string;
  weight?: number | null;
};
export type AssignmentInput = Omit<Assignment, 'id' | 'class_name'>;

export type Submission = {
  id: string;
  assignment_id: string;
  student_id?: string;
  student_name?: string | null;
  submitted_at?: string;
  grade?: string | number | null;
  notes?: string | null;
};
export type SubmissionInput = Omit<
  Submission,
  'id' | 'submitted_at' | 'student_name'
>;

/* -------------------------------------------------------------------------- */
/*  API surface                                                               */
/* -------------------------------------------------------------------------- */

const PREFIX = '/academic';

export const academicApi = {
  /* ---------- Classes + Attendance ---------- */
  listClasses: () =>
    api.get<AcademicClass[]>(`${PREFIX}/classes`).then((r) => r.data),
  getClass: (id: string) =>
    api.get<ClassDetail>(`${PREFIX}/classes/${id}`).then((r) => r.data),
  markAttendance: (classId: string, payload: AttendanceSessionPayload) =>
    api
      .post(`${PREFIX}/classes/${classId}/attendance`, payload)
      .then((r) => r.data),
  getAttendanceSession: (classId: string, date: string) =>
    api
      .get<AttendanceSessionRecord[]>(
        `${PREFIX}/classes/${classId}/attendance`,
        { params: { date } },
      )
      .then((r) => r.data),
  getAttendanceReport: (classId: string) =>
    api
      .get<AttendanceReportRow[]>(
        `${PREFIX}/classes/${classId}/attendance/report`,
      )
      .then((r) => r.data),
  getMyAttendance: () =>
    api
      .get<StudentAttendanceSummary[]>(`${PREFIX}/students/me/attendance`)
      .then((r) => r.data),

  /* ---------- Semesters ---------- */
  listSemesters: () =>
    api.get<Semester[]>(`${PREFIX}/semesters`).then((r) => r.data),
  createSemester: (body: SemesterInput) =>
    api.post<Semester>(`${PREFIX}/semesters`, body).then((r) => r.data),

  /* ---------- Timetable: rooms + slots ---------- */
  listRooms: () =>
    api.get<Room[]>(`${PREFIX}/timetable/rooms`).then((r) => r.data),
  createRoom: (body: RoomInput) =>
    api.post<Room>(`${PREFIX}/timetable/rooms`, body).then((r) => r.data),

  listSlots: (semesterId: string) =>
    api
      .get<TimetableSlot[]>(`${PREFIX}/timetable/slots`, {
        params: { semester_id: semesterId },
      })
      .then((r) => r.data),
  createSlot: (body: TimetableSlotInput) =>
    api
      .post<TimetableSlot>(`${PREFIX}/timetable/slots`, body)
      .then((r) => r.data),
  deleteSlot: (id: string) =>
    api.delete(`${PREFIX}/timetable/slots/${id}`).then(() => true),

  myStudentSchedule: (semesterId: string) =>
    api
      .get<TimetableSlot[]>(
        `${PREFIX}/timetable/students/me/schedule`,
        { params: { semester_id: semesterId } },
      )
      .then((r) => r.data),
  myTeacherSchedule: (semesterId: string) =>
    api
      .get<TimetableSlot[]>(
        `${PREFIX}/timetable/teachers/me/schedule`,
        { params: { semester_id: semesterId } },
      )
      .then((r) => r.data),
  roomSchedule: (roomId: string, semesterId: string) =>
    api
      .get<TimetableSlot[]>(
        `${PREFIX}/timetable/rooms/${roomId}/schedule`,
        { params: { semester_id: semesterId } },
      )
      .then((r) => r.data),

  /* ---------- LMS ---------- */
  listLmsResources: () =>
    api.get<LmsResource[]>(`${PREFIX}/lms/resources`).then((r) => r.data),
  createLmsResource: (body: LmsResourceInput) =>
    api.post<LmsResource>(`${PREFIX}/lms/resources`, body).then((r) => r.data),
  updateLmsResource: (id: string, body: Partial<LmsResourceInput>) =>
    api
      .patch<LmsResource>(`${PREFIX}/lms/resources/${id}`, body)
      .then((r) => r.data),
  deleteLmsResource: (id: string) =>
    api.delete(`${PREFIX}/lms/resources/${id}`).then(() => true),

  /* ---------- Lab Reports ---------- */
  listLabReports: () =>
    api.get<LabReport[]>(`${PREFIX}/lab-reports`).then((r) => r.data),
  createLabReport: (body: LabReportInput) =>
    api.post<LabReport>(`${PREFIX}/lab-reports`, body).then((r) => r.data),
  updateLabReport: (id: string, body: Partial<LabReportInput>) =>
    api.patch<LabReport>(`${PREFIX}/lab-reports/${id}`, body).then((r) => r.data),
  deleteLabReport: (id: string) =>
    api.delete(`${PREFIX}/lab-reports/${id}`).then(() => true),

  /* ---------- Exams ---------- */
  listExams: () => api.get<Exam[]>(`${PREFIX}/exams`).then((r) => r.data),
  createExam: (body: ExamInput) =>
    api.post<Exam>(`${PREFIX}/exams`, body).then((r) => r.data),
  updateExam: (id: string, body: Partial<ExamInput>) =>
    api.patch<Exam>(`${PREFIX}/exams/${id}`, body).then((r) => r.data),
  deleteExam: (id: string) =>
    api.delete(`${PREFIX}/exams/${id}`).then(() => true),

  /* ---------- Advising ---------- */
  listAdvisingSessions: () =>
    api
      .get<AdvisingSession[]>(`${PREFIX}/advising/sessions`)
      .then((r) => r.data),
  createAdvisingSession: (body: AdvisingSessionInput) =>
    api
      .post<AdvisingSession>(`${PREFIX}/advising/sessions`, body)
      .then((r) => r.data),
  updateAdvisingSession: (id: string, body: Partial<AdvisingSessionInput>) =>
    api
      .patch<AdvisingSession>(`${PREFIX}/advising/sessions/${id}`, body)
      .then((r) => r.data),
  deleteAdvisingSession: (id: string) =>
    api.delete(`${PREFIX}/advising/sessions/${id}`).then(() => true),

  /* ---------- Group Projects ---------- */
  listGroupProjects: () =>
    api.get<GroupProject[]>(`${PREFIX}/group-projects`).then((r) => r.data),
  createGroupProject: (body: GroupProjectInput) =>
    api.post<GroupProject>(`${PREFIX}/group-projects`, body).then((r) => r.data),
  updateGroupProject: (id: string, body: Partial<GroupProjectInput>) =>
    api
      .patch<GroupProject>(`${PREFIX}/group-projects/${id}`, body)
      .then((r) => r.data),
  deleteGroupProject: (id: string) =>
    api.delete(`${PREFIX}/group-projects/${id}`).then(() => true),
  listAssignments: (projectId: string) =>
    api
      .get<GroupAssignment[]>(
        `${PREFIX}/group-projects/${projectId}/assignments`,
      )
      .then((r) => r.data),
  createAssignment: (projectId: string, body: GroupAssignmentInput) =>
    api
      .post<GroupAssignment>(
        `${PREFIX}/group-projects/${projectId}/assignments`,
        body,
      )
      .then((r) => r.data),
  deleteAssignment: (projectId: string, assignmentId: string) =>
    api
      .delete(
        `${PREFIX}/group-projects/${projectId}/assignments/${assignmentId}`,
      )
      .then(() => true),

  /* ---------- Study Aids ---------- */
  listStudyNotes: () =>
    api.get<StudyNote[]>(`${PREFIX}/study-aids/notes`).then((r) => r.data),
  createStudyNote: (body: StudyNoteInput) =>
    api
      .post<StudyNote>(`${PREFIX}/study-aids/notes`, body)
      .then((r) => r.data),
  updateStudyNote: (id: string, body: Partial<StudyNoteInput>) =>
    api
      .patch<StudyNote>(`${PREFIX}/study-aids/notes/${id}`, body)
      .then((r) => r.data),
  deleteStudyNote: (id: string) =>
    api.delete(`${PREFIX}/study-aids/notes/${id}`).then(() => true),
  generateAids: (body: { text: string; count?: number }) =>
    api
      .post<GeneratedAids>(`${PREFIX}/study-aids/notes/generate`, body)
      .then((r) => r.data),

  /* ---------- Study Match ---------- */
  listStudyProfiles: () =>
    api
      .get<StudyProfile[]>(`${PREFIX}/study-match/profiles`)
      .then((r) => r.data),
  upsertStudyProfile: (body: StudyProfileInput) =>
    api
      .post<StudyProfile>(`${PREFIX}/study-match/profiles`, body)
      .then((r) => r.data),
  deleteStudyProfile: (id: string) =>
    api.delete(`${PREFIX}/study-match/profiles/${id}`).then(() => true),
  listMatches: () =>
    api.get<StudyMatch[]>(`${PREFIX}/study-match/matches`).then((r) => r.data),

  /* ---------- Finance ---------- */
  listFinanceRecords: () =>
    api.get<FinanceRecord[]>(`${PREFIX}/finance/records`).then((r) => r.data),
  createFinanceRecord: (body: FinanceRecordInput) =>
    api
      .post<FinanceRecord>(`${PREFIX}/finance/records`, body)
      .then((r) => r.data),
  updateFinanceRecord: (id: string, body: Partial<FinanceRecordInput>) =>
    api
      .patch<FinanceRecord>(`${PREFIX}/finance/records/${id}`, body)
      .then((r) => r.data),
  deleteFinanceRecord: (id: string) =>
    api.delete(`${PREFIX}/finance/records/${id}`).then(() => true),

  listScholarships: () =>
    api
      .get<Scholarship[]>(`${PREFIX}/finance/scholarships`)
      .then((r) => r.data),
  createScholarship: (body: ScholarshipInput) =>
    api
      .post<Scholarship>(`${PREFIX}/finance/scholarships`, body)
      .then((r) => r.data),
  updateScholarship: (id: string, body: Partial<ScholarshipInput>) =>
    api
      .patch<Scholarship>(`${PREFIX}/finance/scholarships/${id}`, body)
      .then((r) => r.data),
  deleteScholarship: (id: string) =>
    api.delete(`${PREFIX}/finance/scholarships/${id}`).then(() => true),

  /* ---------- Deadlines ---------- */
  listAssignments_: () =>
    api
      .get<Assignment[]>(`${PREFIX}/deadlines/assignments`)
      .then((r) => r.data),
  createAssignment_: (body: AssignmentInput) =>
    api
      .post<Assignment>(`${PREFIX}/deadlines/assignments`, body)
      .then((r) => r.data),
  updateAssignment_: (id: string, body: Partial<AssignmentInput>) =>
    api
      .patch<Assignment>(`${PREFIX}/deadlines/assignments/${id}`, body)
      .then((r) => r.data),
  deleteAssignment_: (id: string) =>
    api.delete(`${PREFIX}/deadlines/assignments/${id}`).then(() => true),

  listSubmissions: (assignmentId: string) =>
    api
      .get<Submission[]>(
        `${PREFIX}/deadlines/assignments/${assignmentId}/submissions`,
      )
      .then((r) => r.data),
  createSubmission: (assignmentId: string, body: SubmissionInput) =>
    api
      .post<Submission>(
        `${PREFIX}/deadlines/assignments/${assignmentId}/submissions`,
        body,
      )
      .then((r) => r.data),
};

/* -------------------------------------------------------------------------- */
/*  Phase 5 — workflow features layered on the academic scaffolds.            */
/*                                                                            */
/*  These wrap the real backend routes (see                                   */
/*  app/api/v1/endpoints/academic/*) so the frontend pages can call them      */
/*  directly. They use the actual API paths (e.g. /academic/lab/reports,      */
/*  not /academic/lab-reports as the legacy helpers above assumed).           */
/* -------------------------------------------------------------------------- */

export type LmsDeepResource = {
  id: string;
  title: string;
  description: string;
  department: string;
  semester: string;
  course_code: string;
  resource_type: string;
  file_path: string | null;
  url: string | null;
  uploaded_by_id: string | null;
  download_count: number;
  created_at: string;
  updated_at: string;
};

export type LmsDownloadResponse = {
  resource_id: string;
  file_path: string | null;
  url: string | null;
  download_count: number;
};

export type LabReportSummaryClass = {
  class_id: string;
  total: number;
  by_status: Record<string, number>;
  avg_numeric_grade: number | null;
};

export type LabReportStudentSummary = {
  student_id: string;
  classes: LabReportSummaryClass[];
};

export type ExamDeep = {
  id: string;
  course_code: string;
  exam_date: string;
  start_time: string;
  duration_min: number;
  room_id: string | null;
  syllabus_topics: string[];
  difficulty: string;
};

export type ExamCalendarDay = {
  exam_date: string;
  exams: ExamDeep[];
};

export type CgpaTrendPoint = {
  scheduled_at: string;
  current_cgpa: string | null;
};

export type CgpaTrend = {
  student_id: string;
  points: CgpaTrendPoint[];
};

export type AutoBalanceSuggestion = {
  student_id: string;
  role: string;
  weight: string;
};

export type AutoBalanceResult = {
  project_id: string;
  suggestions: AutoBalanceSuggestion[];
  committed: boolean;
};

export type FairnessReport = {
  project_id: string;
  balanced: boolean;
  weight_std_dev: number;
  weight_total: number;
  role_coverage: number;
  suggestions: string[];
};

export type StudyQuizQuestion = {
  index: number;
  question: string;
  options: string[];
};

export type StudyQuiz = {
  note_id: string;
  questions: StudyQuizQuestion[];
  answer_key: Record<string, number>;
};

export type StudyQuizAttempt = {
  id: string;
  note_id: string;
  student_id: string;
  score: number;
  total: number;
  taken_at: string;
};

export type StudyMatchPreview = {
  match_id: string;
  score: number;
  student_id: string;
  full_name: string;
  department: string;
  semester: string;
  shared_courses: string[];
};

export type FinanceSummary = {
  month: string;
  currency: string;
  total_allowance: string;
  total_scholarship: string;
  total_loan: string;
  total_expense: string;
  net: string;
  savings_rate: number;
  expense_by_category: { category: string; amount: string }[];
};

export type FinanceTrendPoint = {
  month: string;
  income: string;
  expense: string;
  net: string;
};

export type FinanceTrend = {
  currency: string;
  points: FinanceTrendPoint[];
};

export type StudentBudget = {
  id: string;
  student_id: string;
  category: string;
  monthly_limit: string;
  currency: string;
};

export type BudgetStatusRow = {
  category: string;
  monthly_limit: string;
  spent: string;
  remaining: string;
  over_budget: boolean;
  over_by: string;
};

export type BudgetStatus = {
  month: string;
  currency: string;
  rows: BudgetStatusRow[];
};

export type UpcomingDeadline = {
  assignment: {
    id: string;
    class_id: string;
    title: string;
    description: string;
    deadline: string;
    weight: string;
    submission_link: string;
  };
  is_overdue: boolean;
  submission_status: string;
};

export const academicDeepApi = {
  /* ---------- LMS ---------- */
  searchLmsResources: (params: {
    q?: string;
    department?: string;
    course_code?: string;
    type?: string;
    limit?: number;
  }) =>
    api
      .get<LmsDeepResource[]>(`${PREFIX}/lms/resources/search`, { params })
      .then((r) => r.data),
  popularLmsResources: (limit = 10) =>
    api
      .get<LmsDeepResource[]>(`${PREFIX}/lms/resources/popular`, {
        params: { limit },
      })
      .then((r) => r.data),
  downloadLmsResource: (id: string) =>
    api
      .post<LmsDownloadResponse>(`${PREFIX}/lms/resources/${id}/download`)
      .then((r) => r.data),

  /* ---------- Lab reports ---------- */
  submitLabReport: (id: string) =>
    api.post(`${PREFIX}/lab/reports/${id}/submit`).then((r) => r.data),
  gradeLabReport: (id: string, grade: string, feedback: string) =>
    api
      .post(`${PREFIX}/lab/reports/${id}/grade`, { grade, feedback })
      .then((r) => r.data),
  pendingLabReports: (classId: string) =>
    api
      .get(`${PREFIX}/lab/classes/${classId}/pending`)
      .then((r) => r.data),
  myLabReportSummary: () =>
    api
      .get<LabReportStudentSummary>(`${PREFIX}/lab/students/me/summary`)
      .then((r) => r.data),

  /* ---------- Exams ---------- */
  scheduleExamRoom: (examId: string, roomId: string) =>
    api
      .post(`${PREFIX}/exams/${examId}/schedule-room`, { room_id: roomId })
      .then((r) => r.data),
  upcomingExams: (days = 14) =>
    api
      .get<ExamDeep[]>(`${PREFIX}/exams/upcoming`, { params: { days } })
      .then((r) => r.data),
  examsByRoom: (roomId: string, from?: string, to?: string) =>
    api
      .get<ExamDeep[]>(`${PREFIX}/exams/by-room/${roomId}`, {
        params: { from, to },
      })
      .then((r) => r.data),
  examCalendar: (month: string) =>
    api
      .get<ExamCalendarDay[]>(`${PREFIX}/exams/calendar`, { params: { month } })
      .then((r) => r.data),

  /* ---------- Advising ---------- */
  cgpaTrend: (studentId: string) =>
    api
      .get<CgpaTrend>(`${PREFIX}/advising/students/${studentId}/cgpa-trend`)
      .then((r) => r.data),
  appendAdvisingNote: (sessionId: string, text: string) =>
    api
      .post(`${PREFIX}/advising/sessions/${sessionId}/notes`, { text })
      .then((r) => r.data),
  myUpcomingAdvising: (days = 30) =>
    api
      .get(`${PREFIX}/advising/advisors/me/upcoming`, { params: { days } })
      .then((r) => r.data),
  myAdvisingSessions: () =>
    api.get(`${PREFIX}/advising/students/me/sessions`).then((r) => r.data),

  /* ---------- Group projects ---------- */
  autoBalanceProject: (
    projectId: string,
    studentIds: string[],
    options: { roles?: string[]; commit?: boolean } = {},
  ) =>
    api
      .post<AutoBalanceResult>(
        `${PREFIX}/group/projects/${projectId}/auto-balance`,
        { student_ids: studentIds, roles: options.roles ?? [] },
        { params: { commit: options.commit ? true : undefined } },
      )
      .then((r) => r.data),
  projectFairness: (projectId: string) =>
    api
      .get<FairnessReport>(`${PREFIX}/group/projects/${projectId}/fairness`)
      .then((r) => r.data),
  activeProjects: (classId: string) =>
    api.get(`${PREFIX}/group/classes/${classId}/active`).then((r) => r.data),

  /* ---------- Study aids ---------- */
  regenerateStudyNote: (
    noteId: string,
    body: { hint?: string; provider?: string } = {},
  ) =>
    api
      .post(`${PREFIX}/study-aids/notes/${noteId}/regenerate`, body)
      .then((r) => r.data),
  studyNoteQuiz: (noteId: string) =>
    api
      .get<StudyQuiz>(`${PREFIX}/study-aids/notes/${noteId}/quiz`)
      .then((r) => r.data),
  submitStudyQuizAttempt: (noteId: string, answers: Record<string, number>) =>
    api
      .post<StudyQuizAttempt>(
        `${PREFIX}/study-aids/notes/${noteId}/quiz/attempts`,
        { answers },
      )
      .then((r) => r.data),
  myQuizHistory: () =>
    api
      .get<StudyQuizAttempt[]>(`${PREFIX}/study-aids/students/me/quiz-history`)
      .then((r) => r.data),

  /* ---------- Study match ---------- */
  refreshStudyMatches: () =>
    api
      .post(`${PREFIX}/study-match/profiles/me/refresh-matches`)
      .then((r) => r.data),
  topStudyMatches: (limit = 10) =>
    api
      .get<StudyMatchPreview[]>(
        `${PREFIX}/study-match/profiles/me/top-matches`,
        { params: { limit } },
      )
      .then((r) => r.data),
  connectMatch: (matchId: string) =>
    api
      .post(`${PREFIX}/study-match/matches/${matchId}/connect`)
      .then((r) => r.data),
  setMyCourses: (courses: string[]) =>
    api
      .post(`${PREFIX}/study-match/profiles/me/courses`, { courses })
      .then((r) => r.data),

  /* ---------- Finance ---------- */
  myFinanceSummary: (month?: string) =>
    api
      .get<FinanceSummary>(`${PREFIX}/finance/students/me/summary`, {
        params: month ? { month } : undefined,
      })
      .then((r) => r.data),
  myFinanceTrend: (months = 6) =>
    api
      .get<FinanceTrend>(`${PREFIX}/finance/students/me/trend`, {
        params: { months },
      })
      .then((r) => r.data),
  listBudgets: () =>
    api.get<StudentBudget[]>(`${PREFIX}/finance/budgets`).then((r) => r.data),
  createBudget: (body: {
    category: string;
    monthly_limit: string;
    currency?: string;
  }) =>
    api
      .post<StudentBudget>(`${PREFIX}/finance/budgets`, body)
      .then((r) => r.data),
  deleteBudget: (id: string) =>
    api.delete(`${PREFIX}/finance/budgets/${id}`).then(() => true),
  myBudgetStatus: (month?: string) =>
    api
      .get<BudgetStatus>(`${PREFIX}/finance/students/me/budget-status`, {
        params: month ? { month } : undefined,
      })
      .then((r) => r.data),
  upcomingScholarships: (days = 60) =>
    api
      .get(`${PREFIX}/finance/scholarships/upcoming`, { params: { days } })
      .then((r) => r.data),

  /* ---------- Deadlines ---------- */
  myUpcomingDeadlines: (days = 14) =>
    api
      .get<UpcomingDeadline[]>(`${PREFIX}/deadlines/students/me/upcoming`, {
        params: { days },
      })
      .then((r) => r.data),
  upsertMySubmission: (
    assignmentId: string,
    body: {
      submission_url?: string;
      notes?: string;
      word_count?: number;
      status?: string;
    },
  ) =>
    api
      .post(
        `${PREFIX}/deadlines/assignments/${assignmentId}/submissions`,
        body,
      )
      .then((r) => r.data),
  transitionSubmissionStatus: (submissionId: string, status: string) =>
    api
      .patch(`${PREFIX}/deadlines/submissions/${submissionId}/status`, {
        status,
      })
      .then((r) => r.data),
  classLateSubmissions: (classId: string) =>
    api
      .get(`${PREFIX}/deadlines/classes/${classId}/late-submissions`)
      .then((r) => r.data),
};

/* -------------------------------------------------------------------------- */
/*  Static option lists & helpers                                              */
/* -------------------------------------------------------------------------- */

export const ATTENDANCE_STATUS_OPTIONS: {
  value: AttendanceStatus;
  label: string;
  badge: string;
}[] = [
  { value: 'present', label: 'Present', badge: 'ec-badge-green' },
  { value: 'late', label: 'Late', badge: 'ec-badge-amber' },
  { value: 'excused', label: 'Excused', badge: 'ec-badge-blue' },
  { value: 'absent', label: 'Absent', badge: 'ec-badge-rose' },
];

export const DAYS_OF_WEEK: { value: DayOfWeek; label: string; short: string }[] =
  [
    { value: 0, label: 'Monday', short: 'Mon' },
    { value: 1, label: 'Tuesday', short: 'Tue' },
    { value: 2, label: 'Wednesday', short: 'Wed' },
    { value: 3, label: 'Thursday', short: 'Thu' },
    { value: 4, label: 'Friday', short: 'Fri' },
    { value: 5, label: 'Saturday', short: 'Sat' },
    { value: 6, label: 'Sunday', short: 'Sun' },
  ];

export const LMS_KINDS: { value: string; label: string }[] = [
  { value: 'video', label: 'Video' },
  { value: 'pdf', label: 'PDF' },
  { value: 'slides', label: 'Slides' },
  { value: 'link', label: 'External link' },
  { value: 'reading', label: 'Reading' },
  { value: 'dataset', label: 'Dataset' },
];

/** Returns 'YYYY-MM-DD' for today in the user's locale, with no time component. */
export function todayIso(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

/** Convert JS Date.getDay() (Sun=0..Sat=6) to our Mon=0..Sun=6 enum. */
export function jsDayToDow(jsDay: number): DayOfWeek {
  // JS: 0=Sun, 1=Mon, ..., 6=Sat. Ours: 0=Mon ... 5=Sat, 6=Sun.
  return (jsDay === 0 ? 6 : jsDay - 1) as DayOfWeek;
}

/** Compare two HH:MM strings as ascending time. */
export function compareTime(a: string, b: string): number {
  return a.localeCompare(b);
}

/** Format an attendance percentage like "92%" or "—" when no sessions yet. */
export function formatAttendancePct(total: number, percentage: number): string {
  if (!total) return '—';
  return `${Math.round(percentage)}%`;
}

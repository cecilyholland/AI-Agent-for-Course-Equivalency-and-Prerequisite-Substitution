export const mockCases = [
  {
    id: "CASE-001",
    student_id: "alj001",
    student_name: "Alice Johnson",
    course_requested: "CPSC 3400 - Data Structures",
    status: "REVIEW_PENDING",
    documents: [
      { id: "doc-001", name: "UTC_Transcript.pdf", uploaded_at: "2025-01-15T10:30:00Z" },
      { id: "doc-002", name: "CPSC301_Syllabus.pdf", uploaded_at: "2025-01-15T10:31:00Z" },
    ],
    decision_result: {
      decision: "APPROVE",
      equivalency_score: 87,
      confidence: "HIGH",
      reasons: [
        {
          text: "CPSC 301 at UTC covers 85% of the topics in CPSC 3400, including linked lists, trees, graphs, and algorithm analysis.",
          citations: [
            { doc_id: "doc-002", page: 2, snippet: "Topics: linked lists, stacks, queues, trees, graphs, sorting algorithms, Big-O analysis" },
          ],
        },
        {
          text: "Student earned an A- in the course, demonstrating strong mastery of the material.",
          citations: [
            { doc_id: "doc-001", page: 1, snippet: "CPSC 301 - Data Structures: A-" },
          ],
        },
      ],
      gaps: [
        {
          text: "UTC course does not appear to cover amortized analysis in depth.",
          severity: "FIXABLE",
          citations: [
            { doc_id: "doc-002", page: 3, snippet: "Brief introduction to amortized analysis (1 lecture)" },
          ],
        },
      ],
    },
    logs: [
      { timestamp: "2025-01-15T10:30:00Z", actor: "STUDENT", action: "UPLOAD", message: "Uploaded transcript and syllabus for CPSC 3400 equivalency request." },
      { timestamp: "2025-01-15T10:35:00Z", actor: "AGENT", action: "EXTRACT", message: "Extraction complete. Parsed 2 documents, identified course CPSC 301." },
      { timestamp: "2025-01-15T10:36:00Z", actor: "AGENT", action: "DECIDE", message: "Decision: APPROVE with 87% equivalency score (HIGH confidence). Minor gap in amortized analysis coverage." },
      { timestamp: "2025-01-15T10:36:01Z", actor: "AGENT", action: "STATUS_CHANGE", message: "Case status changed to REVIEW_PENDING." },
    ],
  },

  {
    id: "CASE-002",
    student_id: "bom002",
    student_name: "Bob Martinez",
    course_requested: "CPSC 4500 - Operating Systems",
    status: "NEEDS_INFO",
    documents: [
      { id: "doc-003", name: "Transfer_Transcript.pdf", uploaded_at: "2025-01-16T09:00:00Z" },
    ],
    decision_result: {
      decision: "NEEDS_MORE_INFO",
      equivalency_score: 45,
      confidence: "LOW",
      reasons: [
        {
          text: "Transcript shows completion of CS 420 - Systems Programming, but course content overlap is unclear without a syllabus.",
        },
      ],
      gaps: [
        {
          text: "No syllabus provided for CS 420. Cannot verify coverage of memory management, process scheduling, or file systems.",
          severity: "INFO_MISSING",
        },
        {
          text: "Transcript does not indicate a prerequisite course in computer architecture.",
          severity: "HARD",
        },
      ],
      missing_info_requests: [
        "Please upload the syllabus for CS 420 - Systems Programming.",
        "Please provide documentation of any computer architecture coursework completed.",
      ],
    },
    logs: [
      { timestamp: "2025-01-16T09:00:00Z", actor: "STUDENT", action: "UPLOAD", message: "Uploaded transcript for CPSC 4500 equivalency request." },
      { timestamp: "2025-01-16T09:05:00Z", actor: "AGENT", action: "EXTRACT", message: "Extraction complete. Parsed 1 document." },
      { timestamp: "2025-01-16T09:06:00Z", actor: "AGENT", action: "DECIDE", message: "Decision: NEEDS_MORE_INFO. Equivalency score 45% (LOW confidence). Missing syllabus and architecture prerequisite documentation." },
      { timestamp: "2025-01-16T09:06:01Z", actor: "AGENT", action: "STATUS_CHANGE", message: "Case status changed to NEEDS_INFO." },
    ],
  },

  {
    id: "CASE-003",
    student_id: "cad003",
    student_name: "Carol Davis",
    course_requested: "CPSC 2100 - Intro to Programming",
    status: "REVIEWED",
    documents: [
      { id: "doc-004", name: "CC_Transcript.pdf", uploaded_at: "2025-01-10T14:00:00Z" },
      { id: "doc-005", name: "CS101_Syllabus.pdf", uploaded_at: "2025-01-10T14:01:00Z" },
    ],
    decision_result: {
      decision: "APPROVE",
      equivalency_score: 95,
      confidence: "HIGH",
      reasons: [
        {
          text: "CS 101 at community college covers all required topics: variables, control flow, functions, arrays, and basic OOP.",
          citations: [
            { doc_id: "doc-005", page: 1, snippet: "Course covers: variables, types, control structures, functions, arrays, intro to OOP with Java" },
          ],
        },
      ],
      gaps: [],
    },
    reviewer_comment: "Straightforward equivalency. Approved.",
    logs: [
      { timestamp: "2025-01-10T14:00:00Z", actor: "STUDENT", action: "UPLOAD", message: "Uploaded transcript and syllabus for CPSC 2100 equivalency request." },
      { timestamp: "2025-01-10T14:05:00Z", actor: "AGENT", action: "EXTRACT", message: "Extraction complete. Parsed 2 documents." },
      { timestamp: "2025-01-10T14:06:00Z", actor: "AGENT", action: "DECIDE", message: "Decision: APPROVE with 95% equivalency score (HIGH confidence). Full topic coverage confirmed." },
      { timestamp: "2025-01-10T14:06:01Z", actor: "AGENT", action: "STATUS_CHANGE", message: "Case status changed to REVIEW_PENDING." },
      { timestamp: "2025-01-11T09:00:00Z", actor: "REVIEWER", action: "APPROVE", message: "Reviewer approved. Comment: Straightforward equivalency. Approved." },
      { timestamp: "2025-01-11T09:00:01Z", actor: "AGENT", action: "STATUS_CHANGE", message: "Case status changed to REVIEWED." },
    ],
  },

  {
    id: "CASE-004",
    student_id: "dak004",
    student_name: "David Kim",
    course_requested: "CPSC 3600 - Computer Networks",
    status: "REVIEW_PENDING",
    documents: [
      { id: "doc-006", name: "University_Transcript.pdf", uploaded_at: "2025-01-17T11:00:00Z" },
      { id: "doc-007", name: "NET300_Syllabus.pdf", uploaded_at: "2025-01-17T11:01:00Z" },
      { id: "doc-008", name: "NET300_LabManual.pdf", uploaded_at: "2025-01-17T11:02:00Z" },
    ],
    decision_result: {
      decision: "APPROVE_WITH_BRIDGE",
      equivalency_score: 72,
      confidence: "MEDIUM",
      reasons: [
        {
          text: "NET 300 covers TCP/IP, routing, and application layer protocols, which overlap significantly with CPSC 3600.",
          citations: [
            { doc_id: "doc-007", page: 1, snippet: "Topics: OSI model, TCP/IP stack, routing protocols, HTTP, DNS, socket programming" },
          ],
        },
      ],
      gaps: [
        {
          text: "No coverage of network security fundamentals (TLS, firewalls, VPNs).",
          severity: "FIXABLE",
          citations: [
            { doc_id: "doc-007", page: 2, snippet: "Security topics are covered in the advanced NET 400 course." },
          ],
        },
        {
          text: "Limited hands-on socket programming compared to CPSC 3600 requirements.",
          severity: "FIXABLE",
        },
      ],
      bridge_plan: [
        "Complete online module: Network Security Fundamentals (est. 2 weeks)",
        "Complete socket programming lab assignments 5-8 from CPSC 3600 (est. 1 week)",
      ],
    },
    logs: [
      { timestamp: "2025-01-17T11:00:00Z", actor: "STUDENT", action: "UPLOAD", message: "Uploaded transcript, syllabus, and lab manual for CPSC 3600 equivalency request." },
      { timestamp: "2025-01-17T11:10:00Z", actor: "AGENT", action: "EXTRACT", message: "Extraction complete. Parsed 3 documents." },
      { timestamp: "2025-01-17T11:11:00Z", actor: "AGENT", action: "DECIDE", message: "Decision: APPROVE_WITH_BRIDGE. Score 72% (MEDIUM confidence). Gaps in network security and socket programming require bridge plan." },
      { timestamp: "2025-01-17T11:11:01Z", actor: "AGENT", action: "STATUS_CHANGE", message: "Case status changed to REVIEW_PENDING." },
    ],
  },

  {
    id: "CASE-005",
    student_id: "emw005",
    student_name: "Emma Wilson",
    course_requested: "CPSC 4100 - Algorithms",
    status: "UPLOADED",
    documents: [
      { id: "doc-009", name: "State_University_Transcript.pdf", uploaded_at: "2025-01-18T08:00:00Z" },
    ],
    logs: [
      { timestamp: "2025-01-18T08:00:00Z", actor: "STUDENT", action: "UPLOAD", message: "Uploaded transcript for CPSC 4100 equivalency request." },
    ],
  },

  {
    id: "CASE-006",
    student_id: "frc006",
    student_name: "Frank Chen",
    course_requested: "CPSC 4600 - Database Systems",
    status: "DECIDED",
    documents: [
      { id: "doc-010", name: "Bootcamp_Certificate.pdf", uploaded_at: "2025-01-19T12:00:00Z" },
      { id: "doc-011", name: "Bootcamp_Curriculum.pdf", uploaded_at: "2025-01-19T12:01:00Z" },
    ],
    decision_result: {
      decision: "DENY",
      equivalency_score: 28,
      confidence: "HIGH",
      reasons: [
        {
          text: "The bootcamp curriculum covers only basic SQL queries and NoSQL introduction, which accounts for less than 30% of CPSC 4600 topics.",
          citations: [
            { doc_id: "doc-011", page: 1, snippet: "Curriculum: SQL basics (SELECT, JOIN, GROUP BY), MongoDB intro, CRUD operations" },
          ],
        },
      ],
      gaps: [
        {
          text: "No coverage of relational algebra, normalization theory, transaction management, or query optimization.",
          severity: "HARD",
        },
        {
          text: "No formal academic assessment — bootcamp uses project-based evaluation only.",
          severity: "HARD",
        },
      ],
    },
    logs: [
      { timestamp: "2025-01-19T12:00:00Z", actor: "STUDENT", action: "UPLOAD", message: "Uploaded bootcamp certificate and curriculum for CPSC 4600 equivalency request." },
      { timestamp: "2025-01-19T12:10:00Z", actor: "AGENT", action: "EXTRACT", message: "Extraction complete. Parsed 2 documents." },
      { timestamp: "2025-01-19T12:11:00Z", actor: "AGENT", action: "DECIDE", message: "Decision: DENY with 28% equivalency score (HIGH confidence). Significant gaps in relational theory, normalization, transactions, and query optimization." },
      { timestamp: "2025-01-19T12:11:01Z", actor: "AGENT", action: "STATUS_CHANGE", message: "Case status changed to DECIDED." },
    ],
  },
];

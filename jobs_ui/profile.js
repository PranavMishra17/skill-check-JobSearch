// Static dossier — what the agent is filtering against. Read-only display copy.
// Update by hand when role / preferences shift; or regenerate from ~/.job_search/state.json.
window.PROFILE_INFO = {
  identity: {
    name: "Pranav P. Mishra",
    role: "Founding LLM Engineer at alfred_",
    location: "New York City, NY",
    email: "pmishr23@uic.edu",
    phone: "773-280-4615",
    links: {
      LinkedIn: "https://linkedin.com/in/pranavgamedev",
      GitHub:   "https://github.com/PranavMishra17",
      Portfolio:"https://portfolio-pranav-mishra-paranoid.vercel.app"
    },
    work_auth: "F1-OPT STEM · valid through July 2028 · sponsorship preferred long-term"
  },

  current_role: {
    title: "Founding LLM Engineer",
    company: "alfred_",
    since: "April 2026",
    summary: "Multi-agent LLM workflows for a consumer AI executive assistant on SMS + voice surfaces. 5K+ active users. Eval harness, MCP tool execution, Cartesia TTS, deterministic risk-scoring decision layer. Techstars-backed."
  },

  education: [
    { degree: "M.S. Computer Science", school: "University of Illinois at Chicago", years: "2023 – 2025", note: "Graduate Assistant" },
    { degree: "B.S. Computer Science & Engineering", school: "Dayananda Sagar College of Engineering, Bangalore", years: "2019 – 2023" }
  ],

  signals: [
    "3 first-author research papers (1 accepted IEEE CAI 2026, 2 under review)",
    "Founding LLM Engineer @ Techstars-backed alfred_ (5K+ active users)",
    "Prior AI Engineer @ Techstars-backed WheelPrice (10–20K DAU CMS shipped)",
    "MIT XR Hackathon 2024 — Winner",
    "INFORMS Analytics+ — Speaker, 700+ professionals"
  ],

  skills: {
    languages: ["Python", "TypeScript", "JavaScript", "C++", "C#", "Java", "Rust"],
    ai_ml: ["PyTorch", "TensorFlow", "LangChain", "LibTorch", "Google ADK", "LiveKit Agents SDK", "Coqui TTS", "XTTS-v2", "HuggingFace"],
    backend: ["FastAPI", "Flask", "Node.js", "Express", "Hono", "ASP.NET Core"],
    databases: ["PostgreSQL", "MongoDB", "Redis", "Supabase", "Pinecone", "Azure Cosmos DB"],
    cloud: ["AWS (SageMaker, MLflow)", "Azure (Speech, AI, Cosmos DB)", "Docker", "CI/CD", "Vercel", "Railway", "Render", "Kubernetes"],
    voice_audio: ["Deepgram", "OpenAI TTS", "Cartesia", "Silero VAD", "WebRTC", "INT8 quantization"]
  },

  expertise: [
    "Multi-agent LLM architecture",
    "Agentic AI / tool-calling",
    "MCP (Model Context Protocol)",
    "Retrieval-augmented generation (RAG)",
    "Voice AI pipelines (STT/TTS/VAD, sub-400ms streaming)",
    "Production LLM deployment",
    "Evaluation infrastructure / LLM-as-judge / regression detection",
    "C++ ML inference (LibTorch, RAII, GPU memory)",
    "Full-stack product engineering",
    "MLOps (versioning, monitoring, CI/CD)"
  ],

  flagship_projects: [
    { name: "alfred_ Execution Decision Layer", note: "5 verdict types · MCP · Cartesia TTS · Vercel" },
    { name: "MetaRAG",                          note: "IEEE CAI 2026 (accepted) · 82.5% precision · 0.925 Hit@10 · AWS SageMaker" },
    { name: "TeamMedAgents / SLM-TeamMedAgents",note: "Multi-agent medical reasoning · 77.63% across 8 benchmarks · 3.1× speedup" },
    { name: "MockFlow-AI",                      note: "Real-time voice interview platform · sub-400ms latency · production" },
    { name: "SnakeAI-MLOps",                    note: "C++/LibTorch RL · TorchScript bridge · 50K-iter soak validated" },
    { name: "SoulEngine",                       note: "Agentic NPC framework · multi-provider LLM · MCP" },
    { name: "IVORY / MedRAG",                   note: "Production multi-modal RAG · <250ms latency · Azure" },
    { name: "WheelPrice CMS",                   note: "10–20K DAU · React/Node/Mongo/Redis · 1.5s → 300ms latency win" }
  ],

  preferences: {
    salary: "Minimum $86k base · prefer ~$125k · open to entry-level bands at strong companies",
    locations: "Remote (US) · NYC hybrid or on-site · open to relocation anywhere in the US",
    stages: "All — seed, Series A/B, growth-stage, frontier AI labs, Big Tech",
    roles_in_scope: [
      "AI Engineer", "LLM Engineer", "ML Engineer", "Agentic AI Engineer",
      "Founding Engineer", "Forward Deployed Engineer", "Applied AI Engineer",
      "Full-Stack AI Engineer", "Research Engineer", "Applied Scientist",
      "Software Engineer (AI/ML scope)"
    ],
    avoid: ["Defense", "Military", "Active-clearance roles", "Pure-frontend roles", "Contract / 1099 (W-2 FT only)"]
  },

  dealbreakers: [
    "No senior / Sr / Lead / Staff / Principal / Manager / Director / VP / Head titles — early-career only",
    "No roles requiring 4+ years of experience (heuristic flagged)",
    "No roles that explicitly exclude visa sponsorship",
    "No clearance-required / US-citizenship-gated roles",
    "No pure-frontend roles",
    "No contract / 1099 roles"
  ],

  crawl_setup: {
    job_search: {
      primary_actor: "fantastic-jobs/career-site-job-listing-api",
      coverage: "ATS direct — Workday, Greenhouse, Ashby, Lever, iCIMS, Rippling, SuccessFactors",
      cost: "~$2.40 per 200-job crawl on free tier",
      filters: "0–2 or 2–5 yrs experience, FT W-2 only, US locations only, AI/Software/Engineering taxonomies"
    },
    hire_search: {
      actors: ["apt_marble/linkedin-hiring-posts-scraper", "apt_marble/linkedIn-recruiter-scraper"],
      coverage: "LinkedIn hiring posts + standing recruiter directory",
      cost: "~$1.00 per 200-record crawl"
    }
  },

  how_it_works: [
    "Type /job-search or /hire-search in Claude Code with an optional window (1d, 7d, 14d, etc.) or label (founding, india, remote).",
    "Apify actors scrape the boards, return raw JSON.",
    "A local Python scorer filters against the dealbreakers, ranks 0–100, dedupes against past sessions.",
    "Results append to data.js (jobs) or hires.js (people) as a new session — never overwrites past ones.",
    "This static HTML reads those files on load. Toggle between scans via the SCAN selector.",
    "Source: github.com/PranavMishra17/skill-check-JobSearch"
  ]
};

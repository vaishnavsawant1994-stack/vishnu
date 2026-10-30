/* Owner-approved illustrative fixture set for Screens 11–15 only.
 * Loaded only by campaign-demo.js when ?campaignDemo=1 is present.
 * Never sent to, or persisted by, a Vishnu server. */
window.VISHNU_CAMPAIGN_DEMO_DATA = Object.freeze({
  owner: { name: 'Alex Morgan', displayName: 'Alex', presence: 'Personal · Online' },
  workspace: { id: 'demo-workspace-rudra', name: 'Rudra Health Care' },
  projects: [
    { id: 'demo-project-patient-crm', title: 'Rudra Health Care', workspace: 'Rudra Health Care', summary: 'Patient CRM implementation', status: 'Active', progress: 72, updated: '2 hours ago', kind: 'workspace' },
    { id: 'demo-project-vishnu-dev', title: 'Vishnu Development', workspace: 'Vishnu Development', summary: 'Product convergence across the Vishnu OS surfaces.', status: 'In progress', progress: 43, updated: '4 hours ago', kind: 'code' },
    { id: 'demo-project-3d', title: 'Vishnu 3D Character', workspace: '3D Studio', summary: 'Face refinement for the Vishnu digital identity.', status: 'Review required', progress: null, updated: '6 hours ago', kind: 'design' }
  ],
  conversations: [
    { id: 'demo-conv-patient-crm', title: 'Patient CRM implementation', workspace: 'Rudra Health Care', project: 'Patient CRM', preview: 'Building a complete patient CRM with profiles, appointments, doctor management, and a clean dashboard.', updated: 'Today, 10:24 AM', pinned: true, messages: 12, files: 3, agents: 3, status: 'Work active' },
    { id: 'demo-conv-convergence', title: 'Vishnu UI convergence', workspace: 'Vishnu Development', project: 'Platform', preview: 'Converging Vishnu UI design system across all platforms.', updated: '1 hour ago', pinned: true, messages: 18, files: 4, agents: 2, status: 'Active' },
    { id: 'demo-conv-face', title: '3D Vishnu face refinement', workspace: 'Vishnu Character', project: '3D Studio', preview: 'Refining the 3D face model with improved realism and expressions.', updated: '2 hours ago', pinned: false, messages: 24, files: 8, agents: 1, status: 'Active' },
    { id: 'demo-conv-repo', title: 'Repository architecture audit', workspace: 'Vishnu Development', project: 'Backend', preview: 'Reviewed repository structure, security and deployment strategy.', updated: '4 hours ago', pinned: false, messages: 9, files: 2, agents: 1, status: 'Completed' },
    { id: 'demo-conv-research', title: 'Research on healthcare regulations', workspace: 'Rudra Health Care', project: 'Research', preview: 'Research notes and citations for healthcare privacy requirements.', updated: '6 hours ago', pinned: false, messages: 16, files: 5, agents: 0, status: 'Completed' },
    { id: 'demo-conv-dating', title: 'Dating App onboarding design', workspace: 'Dating App', project: 'Product Design', preview: 'Onboarding flow, UI screens and user journey.', updated: 'Yesterday', pinned: false, messages: 14, files: 6, agents: 0, status: 'Completed' }
  ],
  historyGroups: [
    { title: 'Pinned', ids: ['demo-conv-patient-crm', 'demo-conv-convergence'] },
    { title: 'Today', ids: ['demo-conv-face', 'demo-conv-repo', 'demo-conv-research'] },
    { title: 'Yesterday', ids: ['demo-conv-dating'] }
  ],
  messages: [
    { role: 'owner', author: 'Alex', time: '10:24 AM', text: 'Build a complete patient CRM for Rudra Health Care with patient profiles, appointments, doctor management, and a clean dashboard. Use a modern stack and show me the architecture, database schema and start the implementation.', attachments: [{ name: 'PRD.pdf', detail: '1.2 MB · PDF' }, { name: 'UI Reference', detail: '4 images · ZIP' }, { name: 'Requirements.docx', detail: '320 KB · DOCX' }] },
    { role: 'vishnu', author: 'Vishnu', time: '10:24 AM', text: "I'll create a comprehensive patient CRM for Rudra Health Care. Let me break this down and start the implementation.", steps: ['Analyzing requirements', 'Creating implementation plan', 'Setting up project structure', 'Building core modules', 'Testing and validation'] }
  ],
  activities: [
    { title: 'Analyzed 12 documents', context: 'Rudra Health Care', time: '2 hours ago', kind: 'file' },
    { title: 'Updated 5 files', context: 'Vishnu Development', time: '4 hours ago', kind: 'code' },
    { title: 'Generated 3 images', context: '3D Character Studio', time: '6 hours ago', kind: 'image' }
  ],
  searchGroups: [
    { title: 'Top result', items: [{ type: 'Workspace', title: 'Rudra Health Care', detail: 'Healthcare Organization', summary: 'Complete healthcare management workspace with patient CRM, appointments, doctors, billing, and integrations.', status: 'Active', target: 'demo-workspace-rudra' }] },
    { title: 'Conversations', items: [
      { type: 'Conversation', title: 'Patient CRM implementation', detail: 'Rudra Health Care  ›  Patient CRM', summary: 'Building a complete patient CRM with profiles, appointments, doctor management…', status: 'Work active', target: 'demo-conv-patient-crm' },
      { type: 'Conversation', title: 'Patient API design discussion', detail: 'Rudra Health Care  ›  Patient CRM', summary: 'API architecture for patient management and integrations.', status: 'Completed', target: 'demo-conv-patient-crm' }
    ] },
    { title: 'Projects', items: [{ type: 'Project', title: 'Patient CRM', detail: 'Rudra Health Care  ›  Patient CRM', summary: 'Complete patient management system with appointments and doctor profiles.', status: 'Active', target: 'demo-project-patient-crm' }] },
    { title: 'Work', items: [{ type: 'Work', title: 'Patient API implementation', detail: 'Rudra Health Care  ›  Patient CRM', summary: 'Implement remaining API endpoints and integrations.', status: 'In progress · 72%', target: 'demo-project-patient-crm' }] },
    { title: 'Files', items: [{ type: 'File', title: 'Patient CRM PRD.pdf', detail: 'PDF · 2.4 MB · 5 days ago', summary: 'Product requirements document for patient CRM.', status: 'Available', target: 'demo-conv-patient-crm' }] },
    { title: 'Agents', items: [{ type: 'Agent', title: 'Healthcare Backend Agent', detail: 'Rudra Health Care  ›  Working on Patient CRM API', summary: 'Specialist agent supporting the patient API implementation.', status: 'Working', target: 'demo-conv-patient-crm' }] }
  ]
});

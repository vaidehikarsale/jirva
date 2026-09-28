// Frontend-only FAQ / sample question content, grouped by the same
// knowledge-base categories JIRVA actually has documentation for. Not
// pulled from the backend - just representative examples of what JIRVA
// can help with, shown on the Ask JIRVA page so a first-time user isn't
// staring at a blank form with no idea what to type.
//
// `title` pre-fills the Query title field; `question` pre-fills the
// Problem description field, when a question is clicked.
export const SAMPLE_QUESTION_GROUPS = [
  {
    category: "Workflows",
    questions: [
      { title: "Issue won't move to Done", question: "Why can't I move my issue to Done?" },
      { title: "Add a workflow status", question: "How do I add a new status to our workflow?" },
      { title: "New project workflow", question: "How do I create a workflow for a new project?" },
    ],
  },
  {
    category: "Permissions",
    questions: [
      { title: "Grant project access", question: "How do I give someone edit access to issues?" },
      { title: "Teammate can't see project", question: "Why can't my teammate see this project?" },
      { title: "Create a permission scheme", question: "How do I create a new permission scheme?" },
    ],
  },
  {
    category: "Issues",
    questions: [
      { title: "Create a subtask", question: "How do I create a subtask under an existing issue?" },
      { title: "Change issue type", question: "Can I change an issue's type after creating it?" },
      { title: "Bulk edit issues", question: "How do I bulk edit multiple issues at once?" },
    ],
  },
  {
    category: "Projects",
    questions: [
      { title: "Team vs. company-managed", question: "What's the difference between a team-managed and company-managed project?" },
      { title: "Identify project type", question: "How do I find out what type of project I'm working in?" },
      { title: "Archive a project", question: "How do I archive a project I no longer need?" },
    ],
  },
  {
    category: "Fields",
    questions: [
      { title: "Add a custom field", question: "How do I add a custom field to my issue form?" },
      { title: "Field not showing up", question: "Why isn't a field showing up on my screen?" },
      { title: "Field-level security", question: "How do I set field-level security so only admins can see a field?" },
    ],
  },
  {
    category: "Search",
    questions: [
      { title: "JQL for assigned issues", question: "How do I write a JQL query to find my assigned issues?" },
      { title: "Reusable saved search", question: "How do I save a search so I can reuse it later?" },
      { title: "Saved filters after leaving", question: "What happens to my saved filters if I leave the project?" },
    ],
  },
  {
    category: "Boards",
    questions: [
      { title: "Kanban board setup", question: "How do I set up a Kanban board for my team?" },
      { title: "Issues missing from board", question: "Why aren't my issues showing up on the board?" },
      { title: "Add a board column", question: "How do I add a new column to my board?" },
    ],
  },
  {
    category: "Notifications",
    questions: [
      { title: "Missing email alerts", question: "Why am I not getting emails when issues are updated?" },
      { title: "Turn off project notifications", question: "How do I turn off notifications for a specific project?" },
      { title: "No comment notifications", question: "Why don't I get email notifications when someone comments on my issue?" },
    ],
  },
  {
    category: "Service Management",
    questions: [
      { title: "What is a queue", question: "What is a queue and how do I set one up?" },
      { title: "SLA configuration", question: "How do I configure SLA goals for support requests?" },
      { title: "Customer portal setup", question: "How do I set up a customer portal for my service project?" },
    ],
  },
  {
    category: "Troubleshooting",
    questions: [
      { title: "Blank page on load", question: "My browser shows a blank page when I open Jira." },
      { title: "Customers missing updates", question: "Customers aren't getting notified when their ticket updates." },
      { title: "Jira running slowly", question: "Why is Jira running slowly for my team?" },
    ],
  },
];

// Flat list, same order, for callers (like the collapsed preview) that
// don't need the grouping.
export const SAMPLE_QUESTIONS = SAMPLE_QUESTION_GROUPS.flatMap((g) => g.questions);

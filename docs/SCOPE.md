The app is built for the owner as its only user. This replaces the earlier owner-and-manager decision wherever the two disagree.
Removed
• The manager role, the role field and every role-based permission check.
• Any screen, setting or report that exists only to supervise another person.
• Multi-user account management (no user list, no invites, no per-user permissions).
Kept, now owner-first
• Login: one password-protected owner account, to keep rent and tenant data private on the PC. It locks automatically after a period of inactivity (default 15 minutes, set in Settings) and asks for the password again.
• Activity log: stays as a history of what changed and when, useful for tracing mistakes and for the accountant. It is append-only.
• Themes: stored on the single owner account, with the same options as section 13.
• Everything else in sections 3 to 12 is unchanged. Every screen is designed around the owner's questions: what is due, what has been paid, who is late, what do I owe in tax, and what is vacant.
Updated rules for the build
1.  One user row. The first-run wizard creates the owner account and there is no sign-up screen afterwards.
2.  Password reset is done by a local recovery step (a recovery code shown once at setup), because there is no admin to reset it.
3.  Audit entries do not need a user column beyond the single owner, but keep the field so a second user could be added later without a data migration.

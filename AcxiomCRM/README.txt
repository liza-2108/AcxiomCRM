ACXIOMCRM - QUICK START
========================

1) Open this folder in VS Code.
2) Open a terminal in this folder.
3) Create and activate a virtual environment:

   py -m venv venv
   venv\Scripts\activate

4) Install dependencies:

   pip install -r requirements.txt

5) Run the app:

   python app.py

6) Open http://127.0.0.1:5000

Initial demo admin:
   Email: admin@acxiomcrm.local
   Password: Admin@123

IMPORTANT:
- Change SECRET_KEY and the demo admin password before deployment.
- This is a time-boxed Flask/SQLite demonstration MVP, not a production-hardened CRM.
- The assignment document specifies ASP.NET Core Identity and Entity Framework Core.
  Confirm with the company that an alternative Python implementation is acceptable.
- Current MVP includes login/register/logout, password hashing, 5-attempt/10-minute
  lockout, role checks, core CRM create/list/delete workflows, follow-ups, audit logs,
  basic reports, dashboard charts, an Activity database entity and JSON APIs for customers/leads/opportunities.
- For a production version, add edit/detail workflows, complete Manager team hierarchy,
  full activity management, pagination/filtering across every module, robust API token
  authentication, secure deployment configuration, backups, tests and stronger validation.
- Registering from the public form always creates a SalesExecutive. Only Admin can create
  Manager/Admin accounts.

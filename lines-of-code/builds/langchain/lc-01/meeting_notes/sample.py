"""Bundled synthetic transcript used when no transcript is supplied.

Replace by passing --file / stdin / a positional argument to the CLI.
"""

SAMPLE_TRANSCRIPT = """\
Q3 Product Planning Sync — June 16, 2026
Attendees: Sarah (Product Manager), James (Engineering Lead), Priya (Design Lead), Marcus (Sales)

Sarah: Thanks everyone for joining. Main goal today is to lock the beta launch scope and timeline. Let's start with where engineering stands.

James: The core notes pipeline is stable. We could ship a limited beta, but the analytics dashboard isn't ready — it needs at least three more weeks. I'd rather not block the beta on it.

Sarah: Agreed. Let's decouple them. Decision: we ship the beta without the analytics dashboard, and we push the dashboard to Q3 proper. Marcus, how many customers do you want in the beta?

Marcus: I have a waitlist of about 120, but I'd start with 50 hand-picked ones so support stays manageable. If it goes well we widen it.

Sarah: Good. Decision: beta opens to 50 selected customers. Target date — let's say next Friday, June 26. James, is that realistic?

James: Yes, if we freeze scope now. I'll need design sign-off on the onboarding flow by Wednesday the 24th though.

Priya: I can have the onboarding screens finalized by Tuesday the 23rd. I'll also prep a short in-app walkthrough.

Sarah: Perfect. Action item: Priya delivers final onboarding designs by Tuesday June 23. James, you own the beta cut and deploy for Friday June 26.

James: Got it. One risk — we're short one engineer for QA. I think we should bring in a contractor for two weeks.

Sarah: Approved. Decision: we hire a QA contractor for a two-week engagement. James, please kick off the contractor search this week and have someone onboarded by Monday June 22.

Marcus: I'll draft the customer invite list and send it to Sarah for approval by Thursday June 25, so we're ready to email customers Friday morning.

Sarah: Great. Let's also schedule a go/no-go check the morning of the 26th. I'll send the invite. Anything else? ... Okay, thanks everyone.
"""

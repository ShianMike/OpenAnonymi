"""Capture synthetic delivery at the mail transport boundary, never bypass code proof."""


class Mailbox:
    def __init__(self):
        self.messages = []
        self.notices = []

    def send_registration_code(self, recipient, code):
        self.messages.append(("registration", recipient, code))

    def send_email_verification_code(self, recipient, code):
        self.messages.append(("verification", recipient, code))

    def send_recovery_code(self, recipient, code):
        self.messages.append(("recovery", recipient, code))

    def send_invitation_code(self, recipient, code):
        self.messages.append(("invitation", recipient, code))

    def send_security_notice(self, recipient, event, at):
        from app.accounts.security_notices import notice_body

        self.notices.append((recipient, event, notice_body(event, at)))

    def latest(self, recipient):
        return next(code for _, email, code in reversed(self.messages) if email == recipient)

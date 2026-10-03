"""Report legacy syntax failures without disclosing stored addresses."""

import argparse
import json

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import load_settings
from app.db.models import User


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--list-ids", action="store_true")
    args = parser.parse_args()
    settings = load_settings()
    engine = create_engine(settings.database_url, hide_parameters=True)
    failures, total = [], 0
    try:
        with Session(engine) as session:
            for user in session.scalars(select(User).order_by(User.id)).yield_per(500):
                total += 1
                try:
                    validate_email(user.email, allow_smtputf8=False, check_deliverability=False)
                except EmailNotValidError:
                    failures.append(str(user.id))
        report = {"total_accounts": total, "syntax_failures": len(failures)}
        if args.list_ids:
            report["user_ids"] = failures
        print(json.dumps(report))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

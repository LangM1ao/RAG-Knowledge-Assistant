"""Run once: python -m app.bootstrap_admin --username admin (interactive password)."""
import argparse
import getpass
from pathlib import Path
from app.db.database import init_db
from app.services.auth_service import create_user, secret_key

def main():
    parser=argparse.ArgumentParser(description='Create the first administrator; never overwrite accounts.')
    parser.add_argument('--username',default='admin')
    parser.add_argument('--password-file',type=Path,help='Optional private local file; never commit this file.')
    args=parser.parse_args()
    secret_key()
    password=args.password_file.read_text(encoding='utf8').strip() if args.password_file else getpass.getpass('New admin password (12+ characters): ')
    if not args.password_file and password!=getpass.getpass('Repeat password: '):
        raise SystemExit('Passwords do not match.')
    init_db()
    user=create_user(args.username,password,'admin',bootstrap=True)
    print('Administrator created. User ID:',user['id'])

if __name__=='__main__':
    main()

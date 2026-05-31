#!/usr/bin/env python3
"""
Utility script to manage encrypted credentials.
Usage:
    python credentials_cli.py encrypt-env     # Encrypt all credentials from .env file
    python credentials_cli.py encrypt <key> <value>  # Encrypt and save a single credential
    python credentials_cli.py decrypt <key>   # Decrypt and display a credential
    python credentials_cli.py list            # List all encrypted credential keys
"""

import sys
import os
from config.credentials import get_credentials_manager, encrypt_all_from_env


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]
    manager = get_credentials_manager()

    if command == "encrypt-env":
        print("Encrypting all credentials from environment variables...")
        encrypt_all_from_env()

    elif command == "encrypt" and len(sys.argv) >= 4:
        key = sys.argv[2]
        value = sys.argv[3]
        encrypted = manager.encrypt_value(value)
        
        # Save to encrypted credentials file
        creds = manager.load_encrypted_credentials()
        creds[key] = encrypted
        manager.save_encrypted_credentials(creds)
        print(f"✓ Encrypted and saved: {key}")

    elif command == "decrypt" and len(sys.argv) >= 3:
        key = sys.argv[2]
        creds = manager.load_encrypted_credentials()
        if key in creds:
            decrypted = manager.decrypt_value(creds[key])
            print(f"{key}={decrypted}")
        else:
            print(f"✗ Credential '{key}' not found")
            sys.exit(1)

    elif command == "list":
        creds = manager.load_encrypted_credentials()
        if not creds:
            print("No encrypted credentials found")
        else:
            print("Encrypted credentials:")
            for key in sorted(creds.keys()):
                print(f"  - {key}")

    elif command == "show-key":
        print(f"Encryption key location: {manager.key_path}")
        if os.path.exists(manager.key_path):
            print(f"✓ Key file exists")
        else:
            print(f"✗ Key file not found (will be created on first use)")

    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()

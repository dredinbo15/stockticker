"""
Credentials management with encryption support.
Handles encryption/decryption of sensitive API keys and database passwords.
"""

import os
import json
from typing import Optional, Dict
from cryptography.fernet import Fernet


class CredentialsManager:
    """
    Manages encrypted credentials storage and retrieval.
    Uses Fernet symmetric encryption for sensitive data.
    """

    def __init__(self, key_path: Optional[str] = None):
        """
        Initialize the credentials manager.
        
        Args:
            key_path: Path to the encryption key file. If not provided,
                     uses CREDENTIALS_KEY_PATH env var or generates default.
        """
        self.key_path = key_path or os.getenv('CREDENTIALS_KEY_PATH', '.credentials_key')
        self.encrypted_creds_path = '.encrypted_credentials.json'
        self._cipher = None

    def _get_cipher(self, *, create_if_missing: bool) -> Fernet:
        """Load the encryption key lazily so imports do not write local files."""
        if self._cipher is not None:
            return self._cipher

        if os.path.exists(self.key_path):
            with open(self.key_path, 'rb') as f:
                key = f.read()
        elif create_if_missing:
            key = Fernet.generate_key()
            with open(self.key_path, 'wb') as f:
                f.write(key)
            print(f"Generated new encryption key at {self.key_path}")
            print("Keep this file safe! It's required to decrypt all credentials.")
        else:
            raise FileNotFoundError(
                f"Encryption key not found at {self.key_path}. "
                "Set CREDENTIALS_KEY_PATH or create the key before loading encrypted credentials."
            )

        self._cipher = Fernet(key)
        return self._cipher

    def encrypt_value(self, value: str) -> str:
        """Encrypt a single value."""
        if not value:
            return ""
        return self._get_cipher(create_if_missing=True).encrypt(value.encode()).decode()

    def decrypt_value(self, encrypted_value: str) -> str:
        """Decrypt a single value."""
        if not encrypted_value:
            return ""
        try:
            return self._get_cipher(create_if_missing=False).decrypt(encrypted_value.encode()).decode()
        except Exception as e:
            raise ValueError(f"Failed to decrypt value: {e}")

    def encrypt_credentials(self, creds_dict: Dict[str, str]) -> Dict[str, str]:
        """Encrypt all credentials in a dictionary."""
        return {k: self.encrypt_value(v) for k, v in creds_dict.items() if v}

    def decrypt_credentials(self, creds_dict: Dict[str, str]) -> Dict[str, str]:
        """Decrypt all credentials in a dictionary."""
        return {k: self.decrypt_value(v) for k, v in creds_dict.items() if v}

    def save_encrypted_credentials(self, creds_dict: Dict[str, str]):
        """
        Save encrypted credentials to a JSON file.
        
        Args:
            creds_dict: Dictionary of credentials to encrypt and save
        """
        encrypted = self.encrypt_credentials(creds_dict)
        with open(self.encrypted_creds_path, 'w') as f:
            json.dump(encrypted, f, indent=2)
        print(f"Encrypted credentials saved to {self.encrypted_creds_path}")

    def load_encrypted_credentials(self) -> Dict[str, str]:
        """Load and decrypt credentials from JSON file."""
        if not os.path.exists(self.encrypted_creds_path):
            return {}
        
        with open(self.encrypted_creds_path, 'r') as f:
            encrypted = json.load(f)
        
        return self.decrypt_credentials(encrypted)

    def get_credential(self, key: str, env_var: Optional[str] = None, 
                      default: Optional[str] = None) -> Optional[str]:
        """
        Get a credential, checking in order:
        1. Encrypted credentials file
        2. Environment variable
        3. Default value
        
        Args:
            key: Key to look up in encrypted credentials
            env_var: Environment variable name to check
            default: Default value if credential not found
            
        Returns:
            The credential value or default
        """
        # Try encrypted credentials first
        creds = self.load_encrypted_credentials()
        if key in creds:
            return creds[key]
        
        # Try environment variable
        if env_var:
            value = os.getenv(env_var)
            if value:
                return value
        
        # Return default
        return default


# Global instance
_credentials_manager = None


def get_credentials_manager() -> CredentialsManager:
    """Get or create the global credentials manager instance."""
    global _credentials_manager
    if _credentials_manager is None:
        _credentials_manager = CredentialsManager()
    return _credentials_manager


def encrypt_all_from_env():
    """
    Encrypt all credentials from environment variables.
    Use this to bootstrap the encrypted credentials file.
    """
    manager = get_credentials_manager()
    
    credentials = {
        'NEO4J_URI': os.getenv('NEO4J_URI', ''),
        'NEO4J_USER': os.getenv('NEO4J_USER', ''),
        'NEO4J_PASSWORD': os.getenv('NEO4J_PASSWORD', ''),
        'OPENAI_API_KEY': os.getenv('OPENAI_API_KEY', ''),
        'NEWS_API_KEY': os.getenv('NEWS_API_KEY', ''),
        'OPENWEATHER_API_KEY': os.getenv('OPENWEATHER_API_KEY', ''),
        'REDIS_URL': os.getenv('REDIS_URL', ''),
        'SEC_USER_AGENT': os.getenv('SEC_USER_AGENT', ''),
    }
    
    # Filter out empty values
    credentials = {k: v for k, v in credentials.items() if v}
    
    if not credentials:
        print("No credentials found in environment variables!")
        return
    
    manager.save_encrypted_credentials(credentials)
    print(f"Encrypted {len(credentials)} credentials")

# Credential Encryption System Documentation

## Overview

This application uses **Fernet symmetric encryption** (from the `cryptography` library) to securely store sensitive credentials like API keys and database passwords. This prevents plain-text credentials from being exposed in version control or configuration files.

## How It Works

### Components

1. **`config/credentials.py`**: Core credential management module
   - `CredentialsManager`: Main class for encrypt/decrypt operations
   - `get_credentials_manager()`: Global singleton instance
   - `encrypt_all_from_env()`: Bootstrap function to encrypt credentials from env vars

2. **`credentials_cli.py`**: Command-line tool for managing credentials
   - Encrypt/decrypt operations
   - List and inspect credentials
   - Key management

3. **`.credentials_key`**: Encryption key file (auto-generated, keep secret!)
   - 32-byte Fernet key
   - DO NOT commit to version control
   - Required to decrypt all credentials

4. **`.encrypted_credentials.json`**: Encrypted credentials storage
   - JSON file containing encrypted credential values
   - Safe to commit to version control (encrypted)
   - Can be shared across environments with same key

### Encryption Flow

```
Plain-text credential
         ↓
   [Fernet cipher]
         ↓
  Encrypted value
         ↓
Store in .encrypted_credentials.json
```

### Decryption Flow

```
Read .encrypted_credentials.json
         ↓
Load .credentials_key
         ↓
   [Fernet cipher]
         ↓
Plain-text credential
         ↓
Use in application
```

## Setup Instructions

### Initial Setup

1. **Install dependencies**:
```bash
pip install -r requirements.txt
```

2. **Prepare your credentials**:
   - Option A: Set all credentials in `.env` file
   - Option B: Export as environment variables
   - Option C: Provide them when running CLI commands

3. **Encrypt credentials**:

**Option A - From .env file** (recommended):
```bash
# Create .env with all your credentials
cat > .env << EOF
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_actual_password
OPENAI_API_KEY=sk-...
NEWS_API_KEY=your_news_key
OPENWEATHER_API_KEY=your_weather_key
REDIS_URL=redis://localhost:6379/0
EOF

# Encrypt all at once
python credentials_cli.py encrypt-env
```

**Option B - One by one**:
```bash
python credentials_cli.py encrypt NEO4J_PASSWORD your_actual_password
python credentials_cli.py encrypt OPENAI_API_KEY sk-...
python credentials_cli.py encrypt NEWS_API_KEY your_news_key
python credentials_cli.py encrypt OPENWEATHER_API_KEY your_weather_key
python credentials_cli.py encrypt REDIS_URL redis://localhost:6379/0
```

4. **Verify encryption**:
```bash
# List all encrypted credentials
python credentials_cli.py list

# Decrypt and verify (should show the plain value)
python credentials_cli.py decrypt NEO4J_PASSWORD
```

5. **Secure the encryption key**:
```bash
# Check key location
python credentials_cli.py show-key

# On Unix/Linux: set restrictive permissions
chmod 600 .credentials_key

# Back up the key in a secure location
cp .credentials_key ~/secure_backup/stockticker_key
```

### Usage in Application

All modules automatically use the `CredentialsManager` to retrieve credentials:

```python
from config.credentials import get_credentials_manager

creds = get_credentials_manager()

# Get a credential (checks encrypted creds, then env vars, then default)
api_key = creds.get_credential('OPENAI_API_KEY', 'OPENAI_API_KEY')
password = creds.get_credential('NEO4J_PASSWORD', 'NEO4J_PASSWORD')
```

## CLI Reference

### Encrypt Environment Variables
```bash
python credentials_cli.py encrypt-env
```
Encrypts all credentials found in environment variables or `.env` file.

### Encrypt Single Credential
```bash
python credentials_cli.py encrypt <KEY> <VALUE>
```
Example: `python credentials_cli.py encrypt OPENAI_API_KEY sk-abc123`

### Decrypt Credential
```bash
python credentials_cli.py decrypt <KEY>
```
Example: `python credentials_cli.py decrypt NEO4J_PASSWORD`
Output: `NEO4J_PASSWORD=my_secret_password`

### List Encrypted Credentials
```bash
python credentials_cli.py list
```
Shows all keys in encrypted credentials (values are not displayed).

### Show Encryption Key Location
```bash
python credentials_cli.py show-key
```

## Security Considerations

### ✅ Best Practices

- **Keep `.credentials_key` secure**: Treat it like a password
- **Use environment variables in production**: Let your deployment platform manage the key
- **Rotate credentials regularly**: Re-encrypt with new values
- **Different credentials per environment**: Dev, staging, and prod should have separate keys
- **Backup the key**: Store in a secure location or vault
- **Use strong API keys**: Generate long, random keys from providers
- **Monitor credential access**: Log who accesses encrypted credentials

### ⚠️ What Not To Do

- Don't commit `.credentials_key` to version control
- Don't share the encryption key via email or chat
- Don't store credentials in plain text
- Don't commit `.env` files with real credentials
- Don't use weak or shared API keys

## Environment-Specific Configuration

### Development

```bash
# Generate local key and encrypt dev credentials
python credentials_cli.py encrypt-env
# Key is stored locally in .credentials_key
```

### Staging

```bash
# Use a different encryption key for staging
CREDENTIALS_KEY_PATH=.credentials_key_staging python credentials_cli.py encrypt-env
```

### Production

**Option 1: Environment Variable Fallback**
```bash
# Don't store .credentials_key in repo
# Instead, let the app use environment variables directly
# (system will fall back to env vars if encrypted file not found)
```

**Option 2: Secure Key Management**
```bash
# Store key in AWS Secrets Manager / HashiCorp Vault / etc.
# Retrieve at runtime and pass to CredentialsManager
```

## Troubleshooting

### Error: "NEO4J_PASSWORD not found"

**Cause**: Credentials haven't been encrypted or environment variable isn't set

**Solution**:
```bash
# Check if credentials are encrypted
python credentials_cli.py list

# If not, encrypt them
python credentials_cli.py encrypt NEO4J_PASSWORD your_password

# Or set environment variable
export NEO4J_PASSWORD=your_password
```

### Error: "Failed to decrypt value"

**Cause**: The `.credentials_key` file is corrupted or was changed

**Solution**:
- Restore `.credentials_key` from backup
- Or delete `.encrypted_credentials.json` and `.credentials_key` and re-encrypt
- Note: You'll need the original credentials to re-encrypt

### Error: "Encryption key not found"

**Cause**: `.credentials_key` doesn't exist

**Solution**:
```bash
# On first run, the key is auto-generated
python credentials_cli.py list

# Or explicitly create:
python credentials_cli.py encrypt NEW_KEY value
```

## Migration from Plain-Text Credentials

If you're upgrading from a system using plain-text credentials:

1. **Set all credentials as environment variables**:
```bash
export NEO4J_PASSWORD=your_password
export OPENAI_API_KEY=sk-...
# ... etc
```

2. **Run encryption**:
```bash
python credentials_cli.py encrypt-env
```

3. **Verify encryption worked**:
```bash
python credentials_cli.py list
```

4. **Remove `.env` file** (or move it to `.env.backup`):
```bash
mv .env .env.backup
```

5. **Test the application**:
```bash
python main.py
# Should work with encrypted credentials
```

## Integration with Deployment Platforms

### Docker

```dockerfile
# Dockerfile
FROM python:3.11
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .

# Mount or provide credentials key at runtime
VOLUME ["/app/.credentials_key"]

CMD ["python", "main.py"]
```

Usage:
```bash
# Build
docker build -t stockticker .

# Run with mounted key
docker run -v /path/to/.credentials_key:/app/.credentials_key stockticker
```

### AWS Lambda / Serverless

```python
# Use AWS Secrets Manager instead of local files
import boto3

def get_credentials_from_aws():
    client = boto3.client('secretsmanager')
    secret = client.get_secret_value(SecretId='stockticker-credentials')
    return json.loads(secret['SecretString'])
```

### Kubernetes

```yaml
# Store key as a secret
apiVersion: v1
kind: Secret
metadata:
  name: stockticker-creds
type: Opaque
data:
  credentials_key: <base64-encoded-key>
---
# Mount as volume in pod
apiVersion: v1
kind: Pod
metadata:
  name: stockticker
spec:
  containers:
  - name: app
    image: stockticker:latest
    volumeMounts:
    - name: creds
      mountPath: /app/.credentials_key
      subPath: credentials_key
  volumes:
  - name: creds
    secret:
      secretName: stockticker-creds
```

## Implementation Details

### Encryption Algorithm

- **Cipher**: Fernet (symmetric encryption)
- **Algorithm**: AES-128 in CBC mode
- **Authentication**: HMAC using SHA256
- **Encoding**: Base64 (compatible with JSON storage)

### Key Structure

```
.credentials_key file:
|--- 44-byte Fernet key (32 bytes random + 12 bytes metadata) encoded in base64
```

### Encrypted Data Format

```
.encrypted_credentials.json:
{
  "NEO4J_PASSWORD": "gAAAAABnK...",  // Encrypted value
  "OPENAI_API_KEY": "gAAAAABlM...",  // Encrypted value
  ...
}
```

## Performance Notes

- Encryption/decryption is fast (<1ms per operation)
- Keys are loaded once into memory
- Minimal performance impact on application startup

## References

- [Cryptography Library Docs](https://cryptography.io/en/latest/)
- [Fernet Specification](https://cryptography.io/en/latest/fernet/)
- [NIST Encryption Guidelines](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-175B.pdf)

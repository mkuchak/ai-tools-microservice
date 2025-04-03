"""
Utility functions for encrypting and decrypting data.
These functions use AES-GCM algorithm for encryption, compatible with the TypeScript Web Crypto API implementation.
"""

import os
import sys
import base64
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Must match the salt used in TypeScript implementation
SALT = b"cloudflare-workers-salt"

def derive_key(secret_key: str) -> bytes:
    """
    Derives a cryptographic key from a secret key
    
    Args:
        secret_key: The secret key to derive from
        
    Returns:
        Derived key as bytes
    """
    if not secret_key:
        raise ValueError("Secret key cannot be empty")
    
    # Convert string to bytes if it isn't already
    if isinstance(secret_key, str):
        secret_key = secret_key.encode('utf-8')
    
    # Use PBKDF2 to derive a key - matching TypeScript parameters
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,  # 256 bits
        salt=SALT,
        iterations=100000,  # Same as TypeScript
    )
    
    return kdf.derive(secret_key)

def encrypt(text: str, secret_key: str) -> str:
    """
    Encrypts a string using AES-GCM
    
    Args:
        text: The text to encrypt
        secret_key: The secret key for encryption
        
    Returns:
        Encrypted text as a base64 string with IV or None if input is empty
    """
    # Handle empty text
    if not text or text.strip() == "":
        return None
    
    # Derive key from secret
    key = derive_key(secret_key)
    
    # Generate a random 96-bit IV (12 bytes)
    iv = os.urandom(12)
    
    # Create an AESGCM instance with the derived key
    aesgcm = AESGCM(key)
    
    # Encrypt the data
    data = text.encode('utf-8')
    encrypted_data = aesgcm.encrypt(iv, data, None)
    
    # Combine IV and encrypted data
    result = iv + encrypted_data
    
    # Convert to base64
    return base64.b64encode(result).decode('utf-8')

def decrypt(encrypted_text: str, secret_key: str) -> str:
    """
    Decrypts a string that was encrypted with AES-GCM from the TypeScript implementation
    
    Args:
        encrypted_text: The encrypted text as a base64 string with IV
        secret_key: The secret key for decryption
        
    Returns:
        Decrypted text
    """
    # Handle empty encrypted text
    if not encrypted_text:
        return ""
    
    # Derive key from secret - using same params as TypeScript
    key = derive_key(secret_key)
    
    try:
        # Decode base64
        encrypted_data = base64.b64decode(encrypted_text)
        
        # Extract IV (first 12 bytes)
        iv = encrypted_data[:12]
        ciphertext = encrypted_data[12:]
        
        # Create an AESGCM instance with the derived key
        aesgcm = AESGCM(key)
        
        # Decrypt the data
        decrypted_data = aesgcm.decrypt(iv, ciphertext, None)
        return decrypted_data.decode('utf-8')
    except Exception as e:
        # Log the error but don't expose details in the returned message
        print(f"Decryption error: {str(e)}")
        sys.stdout.flush()
        return "" 
import hashlib
import getpass

def generate_admin_hash():
    print("--- Admin Password Hash Generator ---")
    password = getpass.getpass("Enter the admin password to hash: ")
    confirm = getpass.getpass("Confirm password: ")
    
    if password != confirm:
        print("Error: Passwords do not match.")
        return

    password_hash = hashlib.sha256(password.encode()).hexdigest()
    
    print("\nSuccess! Your SHA-256 hash is:")
    print(f"\033[1m{password_hash}\033[0m")
    print("\nTo use this, add it to your .streamlit/secrets.toml file:")
    print('ADMIN_PASSWORD_HASH = "your_generated_hash_here"')

if __name__ == "__main__":
    generate_admin_hash()

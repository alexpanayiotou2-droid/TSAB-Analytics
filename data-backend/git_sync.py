# data-backend/git_sync.py
import subprocess
import os

def find_git():
    import shutil
    git_path = shutil.which("git")
    if git_path:
        return git_path
    
    # Common Windows installation paths
    common_paths = [
        r"C:\Program Files\Git\cmd\git.exe",
        r"C:\Program Files\Git\bin\git.exe",
        r"C:\Users\alexp\AppData\Local\Programs\Git\cmd\git.exe",
        r"C:\Users\alexp\AppData\Local\Programs\Git\bin\git.exe",
    ]
    for path in common_paths:
        if os.path.exists(path):
            return path
    return "git"  # Fallback

def sync_repo():
    # Capture the original working directory so we can return to it later
    original_cwd = os.getcwd()
    git_cmd = find_git()
    
    try:
        # Resolve the repository root relative to this script's location
        script_dir = os.path.dirname(os.path.abspath(__file__))
        repo_root = os.path.abspath(os.path.join(script_dir, ".."))
        os.chdir(repo_root) 
        
        print(f"Syncing from root: {os.getcwd()} using {git_cmd}")
        
        # Git commands at the root level
        subprocess.run([git_cmd, "pull", "origin", "main"], check=True)
        subprocess.run([git_cmd, "add", "."], check=True) # Adds frontend AND backend
        subprocess.run([git_cmd, "commit", "-m", "auto-sync: update frontend and backend assets"], check=True)
        subprocess.run([git_cmd, "push", "origin", "main"], check=True)
        
        print("Successfully synced all project folders with GitHub.")
        
    except subprocess.CalledProcessError as e:
        print(f"Git sync failed: {e}")
    finally:
        # Return the agent to its original folder so it doesn't get lost
        os.chdir(original_cwd)

if __name__ == "__main__":
    sync_repo()
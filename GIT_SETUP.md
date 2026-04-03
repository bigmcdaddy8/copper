# Git Setup Guide

Quick reference for initializing a local repository and pushing to GitHub with `master` as the default branch.

## Quick Start (TL;DR)

```bash
# Initialize local repository with master as default branch
git init -b master
git add .
git commit -m "Initial commit"

# Create GitHub repository (choose one method below)
# Method 1: Using GitHub CLI
gh repo create copper --public --source=. --remote=origin --push

# Method 2: Create via web, then:
git remote add origin git@github.com:YOUR_USERNAME/copper.git
git push -u origin master
```

---

## Detailed Steps

### Step 1: Initialize Local Repository

Navigate to your project directory and initialize git with `master` as the default branch:

```bash
cd copper

# Initialize with master as default branch
git init -b master

# Configure user (if not set globally)
git config user.name "Todd McKee"
git config user.email "your-email@example.com"

# Check status
git status
```

### Step 2: Initial Commit

Add all files and create your first commit:

```bash
# Stage all files
git add .

# Review what will be committed
git status

# Create initial commit
git commit -m "Initial commit: Copper project scaffold"

# Verify commit
git log --oneline
```

### Step 3: Create GitHub Repository

Choose one of the following methods:

#### Method A: Using GitHub CLI (Recommended)

**Prerequisites:**
- Install GitHub CLI: `sudo apt install gh` (Ubuntu) or see [gh installation](https://cli.github.com/)
- Authenticate once: `gh auth login`

**Create and push in one command:**

```bash
# Create public repository
gh repo create copper --public --source=. --remote=origin --push

# Or create private repository
gh repo create copper --private --source=. --remote=origin --push

# With description
gh repo create copper --public --description "Copper" --source=. --remote=origin --push
```

**✅ Done!** Your repository is created and pushed. Skip to "Verify Setup" section.

#### Method B: Using GitHub Web UI

1. **Go to GitHub**: Navigate to [https://github.com/new](https://github.com/new)
2. **Repository name**: `copper`
3. **Description**: Optional - "Copper"
4. **Visibility**: Choose Public or Private
5. **Important**: Do NOT initialize with README, .gitignore, or license (you already have these)
6. **Click**: "Create repository"

After creating, GitHub will show you the repository URL. Continue to Step 4.

### Step 4: Connect Local Repository to GitHub

#### Option 1: SSH (Recommended if you have SSH keys)

```bash
# Add remote origin (replace YOUR_USERNAME with your GitHub username)
git remote add origin git@github.com:YOUR_USERNAME/copper.git

# Verify remote
git remote -v

# Push code
git push -u origin master
```

#### Option 2: HTTPS

```bash
# Add remote origin (replace YOUR_USERNAME with your GitHub username)
git remote add origin https://github.com/YOUR_USERNAME/copper.git

# Verify remote
git remote -v

# Push code (will prompt for credentials)
git push -u origin master
```

### Step 5: Verify Setup

```bash
# Check remote tracking
git branch -vv

# View repository information
git remote show origin

# Verify on GitHub
# Visit: https://github.com/YOUR_USERNAME/copper
```

---

## Common Operations

### Making Changes

```bash
# Check status
git status

# Stage specific files
git add file1.py file2.py

# Or stage all changes
git add .

# Commit with message
git commit -m "Descriptive commit message"

# Push to GitHub
git push
```

### Checking History

```bash
# View commit history
git log --oneline

# View last 5 commits
git log --oneline -5

# View detailed history
git log --graph --oneline --decorate --all
```

### Working with Branches

```bash
# Create new branch
git checkout -b feature-name

# List branches
git branch -a

# Switch branches
git checkout master

# Push new branch to GitHub
git push -u origin feature-name

# Delete branch locally
git branch -d feature-name

# Delete branch on GitHub
git push origin --delete feature-name
```

---

## Appendix A: SSH Key Setup (Ubuntu/Linux)

If you don't have SSH keys set up for GitHub, follow these steps:

### 1. Generate SSH Key

```bash
# Generate new SSH key (use your GitHub email)
ssh-keygen -t ed25519 -C "your-email@example.com"

# When prompted:
# - File location: Press Enter for default (~/.ssh/id_ed25519)
# - Passphrase: Enter a secure passphrase (optional but recommended)
```

For older systems that don't support Ed25519:

```bash
ssh-keygen -t rsa -b 4096 -C "your-email@example.com"
```

### 2. Start SSH Agent

```bash
# Start the ssh-agent in the background
eval "$(ssh-agent -s)"

# Add your SSH private key to the ssh-agent
ssh-add ~/.ssh/id_ed25519

# Or for RSA key:
# ssh-add ~/.ssh/id_rsa
```

### 3. Add SSH Key to GitHub

```bash
# Copy your public key to clipboard
cat ~/.ssh/id_ed25519.pub
# Or for RSA: cat ~/.ssh/id_rsa.pub

# Select and copy the output (starts with "ssh-ed25519" or "ssh-rsa")
```

**Add to GitHub:**
1. Go to GitHub: [https://github.com/settings/keys](https://github.com/settings/keys)
2. Click "New SSH key"
3. Title: "Ubuntu Desktop" (or whatever identifies your machine)
4. Key type: Authentication Key
5. Paste your public key
6. Click "Add SSH key"

### 4. Test SSH Connection

```bash
# Test GitHub connection
ssh -T git@github.com

# You should see:
# Hi USERNAME! You've successfully authenticated, but GitHub does not provide shell access.
```

### 5. Configure SSH (Optional)

Create/edit `~/.ssh/config` for easier management:

```bash
# Create or edit SSH config
nano ~/.ssh/config
```

Add this content:

```
Host github.com
    HostName github.com
    User git
    IdentityFile ~/.ssh/id_ed25519
    AddKeysToAgent yes
```

Set correct permissions:

```bash
chmod 600 ~/.ssh/config
```

---

## Appendix B: Troubleshooting

### Issue: "remote origin already exists"

```bash
# View current remote
git remote -v

# Remove existing remote
git remote remove origin

# Add correct remote
git remote add origin git@github.com:YOUR_USERNAME/copper.git
```

### Issue: "Updates were rejected because the remote contains work"

This happens if you initialized the GitHub repo with a README.

```bash
# Option 1: Pull and merge (if safe)
git pull origin master --allow-unrelated-histories
git push -u origin master

# Option 2: Force push (⚠️ destructive - only if you're sure)
git push -u origin master --force
```

### Issue: "Permission denied (publickey)"

Your SSH key isn't set up or recognized by GitHub.

```bash
# Verify SSH key is loaded
ssh-add -l

# If empty, add your key
ssh-add ~/.ssh/id_ed25519

# Test GitHub connection
ssh -T git@github.com

# If still failing, verify key is added to GitHub
# Visit: https://github.com/settings/keys
```

### Issue: "main" vs "master" branch mismatch

If GitHub created the repo with `main` and you're using `master`:

```bash
# Option 1: Rename your local branch to main
git branch -M main
git push -u origin main

# Option 2: Push and set upstream to master
git push -u origin master

# Then on GitHub, go to Settings → Branches → Default branch
# Change it to master
```

### Issue: HTTPS authentication fails

GitHub no longer accepts password authentication for Git operations.

```bash
# Switch to SSH authentication
git remote set-url origin git@github.com:YOUR_USERNAME/copper.git

# Or create a Personal Access Token (PAT)
# Visit: https://github.com/settings/tokens
# Use the token as your password when prompted
```

---

## Appendix C: Changing Default Branch Preference

To set `master` as the default branch name for all new repositories:

```bash
# Set global default branch name
git config --global init.defaultBranch master

# Verify setting
git config --global --get init.defaultBranch
```

This affects all future `git init` commands.

---

## Additional Resources

- [GitHub CLI Documentation](https://cli.github.com/manual/)
- [GitHub SSH Key Setup](https://docs.github.com/en/authentication/connecting-to-github-with-ssh)
- [Git Documentation](https://git-scm.com/doc)
- [Pro Git Book](https://git-scm.com/book/en/v2) (free online)

---

**Quick Reference Card:**

| Task | Command |
|------|---------|
| Initialize repo | `git init -b master` |
| Stage all files | `git add .` |
| Commit | `git commit -m "message"` |
| Add remote | `git remote add origin <url>` |
| Push | `git push -u origin master` |
| Clone | `git clone <url>` |
| Check status | `git status` |
| View history | `git log --oneline` |
| Create branch | `git checkout -b branch-name` |
| Switch branch | `git checkout branch-name` |

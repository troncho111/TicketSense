#!/bin/bash
# Setup auto-push to GitHub after every commit (Linux/Mac)

echo "Setting up auto-push to GitHub..."

# Create post-commit hook
cat > .git/hooks/post-commit << 'EOF'
#!/bin/sh
echo "🚀 Auto-pushing to GitHub..."
git push origin main
EOF

# Make it executable
chmod +x .git/hooks/post-commit

echo ""
echo "✅ Auto-push configured!"
echo ""
echo "Now every time you commit, it will automatically push to GitHub."
echo "To test: git commit --allow-empty -m 'Test auto-push'"
